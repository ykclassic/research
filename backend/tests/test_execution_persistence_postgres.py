from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20261019120000_execution_approval_intent_audit.sql"
)
DATABASE_URL = os.getenv("EXECUTION_TEST_DATABASE_URL")


@pytest.fixture(scope="session", autouse=True)
def migrated_postgres() -> None:
    if not DATABASE_URL:
        pytest.skip("EXECUTION_TEST_DATABASE_URL is not set; dedicated Postgres workflow runs these tests.")
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA auth")
        connection.execute("CREATE TABLE auth.users (id uuid PRIMARY KEY)")
        connection.execute("CREATE ROLE anon NOLOGIN")
        connection.execute("CREATE ROLE authenticated NOLOGIN")
        connection.execute("CREATE ROLE service_role NOLOGIN")
        connection.execute(MIGRATION_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def db(migrated_postgres):
    with psycopg.connect(DATABASE_URL) as connection:
        yield connection
        connection.rollback()


def _future(minutes: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _new_user(db) -> str:
    user_id = str(uuid4())
    db.execute("insert into auth.users(id) values (%s)", (user_id,))
    return user_id


def _create_intent(db, user_id: str, key: str | None = None):
    key = key or f"intent-{uuid4()}"
    existing = None
    if db.execute(
        "select to_regclass('public.execution_intents')"
    ).fetchone()[0] is not None:
        existing = db.execute(
            """select request_hash, signal_snapshot, account_snapshot, market_snapshot, risk_snapshot
               from public.execution_intents where user_id=%s and idempotency_key=%s""",
            (user_id, key),
        ).fetchone()
    if existing:
        request_hash, signal, account, market, risk = existing
    else:
        signal = {"signal_id": "signal-test", "symbol": "BTC/USDT", "side": "LONG", "quantity": 1.0, "entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0, "qualified": True}
        account = {"equity": 10000, "source": "test", "account_ref": "test-account"}
        market = {"price": 100, "observed_at": datetime.now(timezone.utc).isoformat()}
        risk = {"risk_pct": 0.5, "risk_policy_version": "test-v1"}
        request_hash = db.execute(
            "select public.execution_intent_request_sha256(%s, %s, %s, %s)",
            (Jsonb(signal), Jsonb(account), Jsonb(market), Jsonb(risk)),
        ).fetchone()[0]
    rows = db.execute(
        """select intent_id, created from public.create_execution_intent(
          %s, %s, %s, %s, %s, %s, %s, %s
        )""",
        (user_id, key, request_hash, Jsonb(signal), Jsonb(account), Jsonb(market), Jsonb(risk), _future(120)),
    ).fetchone()
    return rows[0], rows[1], key


def _claim(db, user_id: str, intent_id, approval_id, *, stale: bool = False, missing_timestamp: bool = False):
    validated_at = datetime.now(timezone.utc) - timedelta(seconds=20 if stale else 0)
    proof = {
        "passed": True,
        "request_hash": db.execute("select request_hash from public.execution_intents where id=%s", (intent_id,)).fetchone()[0],
        "account_ref": "test-account",
        "symbol": "BTC/USDT",
        "side": "LONG",
        "quantity": 1.0,
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_policy_version": "test-v1",
        "validated_at": validated_at.isoformat(),
    }
    if missing_timestamp:
        proof.pop("validated_at")
    proof_hash = db.execute("select public.execution_snapshot_sha256(%s)", (Jsonb(proof),)).fetchone()[0]
    return db.execute(
        "select public.claim_execution(%s, %s, %s, %s, %s)",
        (user_id, intent_id, approval_id, Jsonb(proof), proof_hash),
    ).fetchone()[0]


def _approve(db, user_id: str, intent_id, decision: str = "APPROVE"):
    intent = db.execute(
        "select request_hash, signal_snapshot, account_snapshot, risk_snapshot from public.execution_intents where id=%s",
        (intent_id,),
    ).fetchone()
    request_hash, signal, account, risk = intent
    snapshot = {
        "intent_id": str(intent_id),
        "request_hash": request_hash,
        "account_ref": account["account_ref"],
        "symbol": signal["symbol"],
        "side": signal["side"],
        "quantity": signal["quantity"],
        "entry_price": signal["entry_price"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "risk_policy_version": risk["risk_policy_version"],
    }
    snapshot_hash = db.execute(
        "select public.execution_snapshot_sha256(%s)", (Jsonb(snapshot),)
    ).fetchone()[0]
    challenge_jti_hash = hashlib.sha256(uuid4().hex.encode("utf-8")).hexdigest()
    challenge_expiry = _future(5)
    db.execute(
        """select public.register_execution_approval_challenge(%s, %s, %s, %s, %s, %s)""",
        (user_id, intent_id, request_hash, decision, challenge_jti_hash, challenge_expiry),
    )
    return db.execute(
        """select public.record_execution_approval(%s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, intent_id, decision, user_id, Jsonb(snapshot), snapshot_hash,
         _future(60), challenge_jti_hash),
    ).fetchone()[0]


def test_intent_creation_is_idempotent_and_does_not_duplicate_events(db) -> None:
    user_id = _new_user(db)
    intent_id, created, key = _create_intent(db, user_id)
    again_id, created_again, _ = _create_intent(db, user_id, key)

    assert intent_id == again_id
    assert created is True
    assert created_again is False
    assert db.execute(
        "select count(*) from public.execution_events where intent_id=%s and event_type='INTENT_CREATED'",
        (intent_id,),
    ).fetchone()[0] == 1


def test_reusing_idempotency_key_for_different_payload_fails_closed(db) -> None:
    user_id = _new_user(db)
    _, _, key = _create_intent(db, user_id)
    with pytest.raises(psycopg.Error):
        db.execute(
            """select * from public.create_execution_intent(
              %s, %s, %s, %s, %s, %s, %s, %s
            )""",
            (
                user_id, key, "c" * 64, Jsonb({"different": True}),
                Jsonb({}), Jsonb({}), Jsonb({}), _future(120),
            ),
        )


def test_approval_is_immutable_and_single_use(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id)

    with pytest.raises(psycopg.Error, match="append-only"):
        with db.transaction():
            db.execute("update public.execution_approvals set decision='REJECT' where id=%s", (approval_id,))

    with pytest.raises(psycopg.Error, match="append-only"):
        with db.transaction():
            db.execute("delete from public.execution_approvals where id=%s", (approval_id,))
    assert db.execute("select status from public.execution_intents where id=%s", (intent_id,)).fetchone()[0] == "APPROVED"
    with pytest.raises(psycopg.Error):
        with db.transaction():
            _approve(db, user_id, intent_id)


def test_rejected_proposal_cannot_be_claimed(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id, "REJECT")

    with pytest.raises(psycopg.Error, match="execution is disabled"):
        with db.transaction():
            _claim(db, user_id, intent_id, approval_id)


def test_claim_and_result_rpc_fail_closed_while_execution_is_disabled(db) -> None:
    user_id = _new_user(db)
    intent_id, _, key = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id)

    with pytest.raises(psycopg.Error, match="execution is disabled"):
        with db.transaction():
            _claim(db, user_id, intent_id, approval_id)
    assert db.execute("select status from public.execution_intents where id=%s", (intent_id,)).fetchone()[0] == "APPROVED"
    with pytest.raises(psycopg.Error, match="execution is disabled"):
        with db.transaction():
            db.execute(
                """select public.record_execution_result(%s, %s, %s, %s, %s, %s, %s)""",
                (user_id, intent_id, approval_id, key, "FILLED", "TEST-BROKER-1", Jsonb({"fill_price": 100.1})),
            )


def test_event_log_is_append_only_and_rejected_approval_has_no_execution_record(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    _approve(db, user_id, intent_id, "REJECT")
    event_id = db.execute(
        "select event_seq from public.execution_events where intent_id=%s order by event_seq desc limit 1",
        (intent_id,),
    ).fetchone()[0]

    with pytest.raises(psycopg.Error, match="append-only"):
        with db.transaction():
            db.execute("update public.execution_events set event_type='INTENT_CREATED' where event_seq=%s", (event_id,))
    with pytest.raises(psycopg.Error, match="append-only"):
        with db.transaction():
            db.execute("delete from public.execution_events where event_seq=%s", (event_id,))
    assert db.execute("select status from public.execution_intents where id=%s", (intent_id,)).fetchone()[0] == "REJECTED"
    assert db.execute("select count(*) from public.execution_records where intent_id=%s", (intent_id,)).fetchone()[0] == 0



def test_execution_tables_are_not_granted_to_browser_roles(db) -> None:
    rows = db.execute(
        """select c.relname, c.relrowsecurity,
          has_table_privilege('anon', format('public.%I', c.relname), 'select') as anon_select,
          has_table_privilege('authenticated', format('public.%I', c.relname), 'select') as authenticated_select
        from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relname in (
          'execution_intents','execution_approvals','execution_approval_challenges','execution_records','execution_events'
        ) order by c.relname"""
    ).fetchall()
    assert len(rows) == 5
    # The service role uses only the narrow SECURITY DEFINER RPCs; it has no
    # direct table privileges. Browser roles must also have no direct access.
    assert all(row[1] is True and row[2] is False and row[3] is False for row in rows)

    rpc_privileges = db.execute(
        """select
          has_function_privilege('anon', 'public.create_execution_intent(uuid,text,text,jsonb,jsonb,jsonb,jsonb,timestamptz)'::regprocedure, 'execute'),
          has_function_privilege('authenticated', 'public.create_execution_intent(uuid,text,text,jsonb,jsonb,jsonb,jsonb,timestamptz)'::regprocedure, 'execute'),
          has_function_privilege('service_role', 'public.create_execution_intent(uuid,text,text,jsonb,jsonb,jsonb,jsonb,timestamptz)'::regprocedure, 'execute')"""
    ).fetchone()
    assert rpc_privileges == (False, False, True)



def test_stale_revalidation_cannot_bypass_disabled_claim(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id)

    with pytest.raises(psycopg.Error, match="execution is disabled"):
        with db.transaction():
            _claim(db, user_id, intent_id, approval_id, stale=True)

    assert db.execute("select status from public.execution_intents where id=%s", (intent_id,)).fetchone()[0] == "APPROVED"



def test_missing_revalidation_timestamp_cannot_bypass_disabled_claim(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id)

    with pytest.raises(psycopg.Error, match="execution is disabled"):
        with db.transaction():
            _claim(db, user_id, intent_id, approval_id, missing_timestamp=True)

    assert db.execute("select status from public.execution_intents where id=%s", (intent_id,)).fetchone()[0] == "APPROVED"


def test_canonical_hash_rejects_tampered_approval_snapshot(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    intent = db.execute(
        "select request_hash, signal_snapshot, account_snapshot, risk_snapshot from public.execution_intents where id=%s",
        (intent_id,),
    ).fetchone()
    request_hash, signal, account, risk = intent
    snapshot = {
        "intent_id": str(intent_id), "request_hash": request_hash,
        "account_ref": account["account_ref"], "symbol": signal["symbol"],
        "side": signal["side"], "quantity": signal["quantity"],
        "entry_price": signal["entry_price"], "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"], "risk_policy_version": risk["risk_policy_version"],
    }
    digest = db.execute("select public.execution_snapshot_sha256(%s)", (Jsonb(snapshot),)).fetchone()[0]
    snapshot["quantity"] = 999
    with pytest.raises(psycopg.Error, match="canonical approved intent"):
        with db.transaction():
            db.execute(
                "select public.record_execution_approval(%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, intent_id, "APPROVE", user_id, Jsonb(snapshot), digest, _future(60), "0" * 64),
            )


def test_request_hash_must_match_canonical_snapshots(db) -> None:
    user_id = _new_user(db)
    with pytest.raises(psycopg.Error, match="request hash does not match"):
        with db.transaction():
            db.execute(
                "select * from public.create_execution_intent(%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, f"intent-{uuid4()}", "a" * 64, Jsonb({"symbol":"BTC/USDT"}),
                 Jsonb({"account_ref":"test-account"}), Jsonb({"price":100}),
                 Jsonb({"risk_policy_version":"test-v1"}), _future(120)),
            )


def test_intent_payload_and_out_of_contract_transitions_are_rejected(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    with pytest.raises(psycopg.Error, match="payload is immutable"):
        with db.transaction():
            db.execute("update public.execution_intents set signal_snapshot=%s where id=%s",
                       (Jsonb({"symbol":"ETH/USDT"}), intent_id))
    with pytest.raises(psycopg.Error, match="state may only change"):
        with db.transaction():
            db.execute("update public.execution_intents set status='EXECUTING', updated_at=now() where id=%s",
                       (intent_id,))


def test_rpc_owner_and_search_path_are_hardened(db) -> None:
    rows = db.execute(
        """select p.proname, r.rolsuper, r.rolcanlogin, p.proconfig
           from pg_proc p join pg_roles r on r.oid=p.proowner
           join pg_namespace n on n.oid=p.pronamespace
           where n.nspname='public' and p.proname in
             ('create_execution_intent','get_execution_intent_approval_preview','register_execution_approval_challenge','record_execution_approval','claim_execution','record_execution_result')"""
    ).fetchall()
    assert len(rows) == 6
    assert all(row[1] is False and row[2] is False for row in rows)
    assert all(row[3] and "search_path=pg_catalog" in row[3] for row in rows)


def _canonical_approval_snapshot(db, intent_id):
    request_hash, signal, account, risk = db.execute(
        "select request_hash, signal_snapshot, account_snapshot, risk_snapshot "
        "from public.execution_intents where id=%s",
        (intent_id,),
    ).fetchone()
    return {
        "intent_id": str(intent_id),
        "request_hash": request_hash,
        "account_ref": account["account_ref"],
        "symbol": signal["symbol"],
        "side": signal["side"],
        "quantity": signal["quantity"],
        "entry_price": signal["entry_price"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "risk_policy_version": risk["risk_policy_version"],
    }


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("intent_id", str(uuid4())),
        ("request_hash", "f" * 64),
        ("account_ref", "different-account"),
        ("symbol", "ETH/USDT"),
        ("side", "SHORT"),
        ("quantity", 0.01),
        ("entry_price", 101.0),
        ("stop_loss", 98.0),
        ("take_profit", 103.0),
        ("risk_policy_version", "changed-policy"),
        ("unexpected_extra_field", "not-authoritative"),
    ],
)
def test_every_security_critical_approval_field_is_bound(db, field, replacement) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    snapshot = _canonical_approval_snapshot(db, intent_id)
    snapshot[field] = replacement
    digest = db.execute(
        "select public.execution_snapshot_sha256(%s)", (Jsonb(snapshot),)
    ).fetchone()[0]

    with pytest.raises(psycopg.Error, match="canonical approved intent"):
        with db.transaction():
            db.execute(
                "select public.record_execution_approval(%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, intent_id, "APPROVE", user_id, Jsonb(snapshot), digest, _future(10), "0" * 64),
            )


def test_canonical_jsonb_hash_is_stable_for_equivalent_object_key_order(db) -> None:
    first = {"z": 1, "nested": {"b": 2, "a": 3}, "a": "value"}
    second = {"a": "value", "nested": {"a": 3, "b": 2}, "z": 1}
    hashes = db.execute(
        "select public.execution_snapshot_sha256(%s), public.execution_snapshot_sha256(%s)",
        (Jsonb(first), Jsonb(second)),
    ).fetchone()
    assert hashes[0] == hashes[1]


def test_approval_rejects_wrong_actor_and_expiry_beyond_intent(db) -> None:
    user_id = _new_user(db)
    other_user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    snapshot = _canonical_approval_snapshot(db, intent_id)
    digest = db.execute(
        "select public.execution_snapshot_sha256(%s)", (Jsonb(snapshot),)
    ).fetchone()[0]

    with pytest.raises(psycopg.Error, match="does not own intent"):
        with db.transaction():
            db.execute(
                "select public.record_execution_approval(%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, intent_id, "APPROVE", other_user_id, Jsonb(snapshot), digest, _future(5), "0" * 64),
            )

    # The intent expires in 120 minutes; an approval cannot outlive it.
    with pytest.raises(psycopg.Error, match="expiry is invalid"):
        with db.transaction():
            db.execute(
                "select public.record_execution_approval(%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, intent_id, "APPROVE", user_id, Jsonb(snapshot), digest, _future(180), "0" * 64),
            )


def test_approval_and_intent_transition_roll_back_if_audit_insert_fails(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    db.execute("""
        create or replace function public.test_reject_approval_audit_insert()
        returns trigger language plpgsql as $test$
        begin
          if new.event_type in ('APPROVAL_ACCEPTED', 'APPROVAL_REJECTED') then
            raise exception 'forced audit insert failure';
          end if;
          return new;
        end;
        $test$
    """)
    db.execute("""
        create trigger test_reject_approval_audit_insert
        before insert on public.execution_events
        for each row execute function public.test_reject_approval_audit_insert()
    """)
    with pytest.raises(psycopg.Error, match="forced audit insert failure"):
        with db.transaction():
            _approve(db, user_id, intent_id)

    assert db.execute(
        "select status from public.execution_intents where id=%s", (intent_id,)
    ).fetchone()[0] == "AWAITING_APPROVAL"
    assert db.execute(
        "select count(*) from public.execution_approvals where intent_id=%s", (intent_id,)
    ).fetchone()[0] == 0
    assert db.execute(
        "select count(*) from public.execution_events where intent_id=%s "
        "and event_type in ('APPROVAL_ACCEPTED', 'APPROVAL_REJECTED')",
        (intent_id,),
    ).fetchone()[0] == 0


def test_all_privileged_functions_have_restricted_owner_and_execute_grants(db) -> None:
    signatures = [
        "public.execution_snapshot_sha256(jsonb)",
        "public.execution_intent_request_sha256(jsonb,jsonb,jsonb,jsonb)",
        "public.create_execution_intent(uuid,text,text,jsonb,jsonb,jsonb,jsonb,timestamptz)",
        "public.register_execution_approval_challenge(uuid,uuid,text,text,text,timestamptz)",
        "public.record_execution_approval(uuid,uuid,text,uuid,jsonb,text,timestamptz,text)",
        "public.get_execution_intent_approval_preview(uuid,uuid)",
        "public.claim_execution(uuid,uuid,uuid,jsonb,text)",
        "public.record_execution_result(uuid,uuid,uuid,text,text,text,jsonb)",
    ]
    rows = db.execute(
        """
        select p.oid::regprocedure::text, r.rolname, r.rolsuper, r.rolcanlogin,
               p.prosecdef, p.proconfig
        from pg_proc p
        join pg_roles r on r.oid = p.proowner
        where p.oid = any(%s::oid[])
        """,
        ([db.execute("select %s::regprocedure::oid", (sig,)).fetchone()[0] for sig in signatures],),
    ).fetchall()
    assert len(rows) == len(signatures)
    assert all(row[1] == "execution_persistence_owner" for row in rows)
    assert all(row[2] is False and row[3] is False and row[4] is True for row in rows)
    assert all(row[5] and "search_path=pg_catalog" in row[5] for row in rows)

    assert db.execute(
        "select has_schema_privilege('execution_persistence_owner','public','create')"
    ).fetchone()[0] is False
    assert db.execute(
        "select pg_has_role('service_role','execution_persistence_owner','member')"
    ).fetchone()[0] is False

    for signature in signatures:
        privilege = db.execute(
            "select has_function_privilege('anon', %s::regprocedure, 'execute'), "
            "has_function_privilege('authenticated', %s::regprocedure, 'execute')",
            (signature, signature),
        ).fetchone()
        assert privilege == (False, False), signature

    for signature in signatures[2:]:
        assert db.execute(
            "select has_function_privilege('service_role', %s::regprocedure, 'execute')",
            (signature,),
        ).fetchone()[0] is True

    function_oids = [
        db.execute("select %s::regprocedure::oid", (signature,)).fetchone()[0]
        for signature in signatures
    ]
    public_execute = db.execute(
        """
        select p.oid::regprocedure::text
        from pg_proc p
        cross join lateral pg_catalog.aclexplode(
          coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
        ) acl
        where p.oid = any(%s::oid[])
          and acl.grantee = 0
          and acl.privilege_type = 'EXECUTE'
        """,
        (function_oids,),
    ).fetchall()
    assert public_execute == []

    trigger_signatures = [
        "public.reject_execution_record_mutation()",
        "public.guard_execution_approval_challenge_mutation()",
        "public.guard_execution_intent_mutation()",
    ]
    for signature in trigger_signatures:
        row = db.execute(
            "select r.rolname, p.proconfig from pg_proc p "
            "join pg_roles r on r.oid=p.proowner where p.oid=%s::regprocedure",
            (signature,),
        ).fetchone()
        assert row[0] == "execution_persistence_owner"
        assert row[1] and "search_path=pg_catalog" in row[1]
        assert db.execute(
            "select has_function_privilege('anon', %s::regprocedure, 'execute'), "
            "has_function_privilege('authenticated', %s::regprocedure, 'execute'), "
            "has_function_privilege('service_role', %s::regprocedure, 'execute')",
            (signature, signature, signature),
        ).fetchone() == (False, False, False)


def test_service_role_cannot_mutate_execution_tables_directly(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute("set local role service_role")
            db.execute(
                "update public.execution_intents set status='APPROVED' where id=%s",
                (intent_id,),
            )
    assert db.execute(
        "select status from public.execution_intents where id=%s", (intent_id,)
    ).fetchone()[0] == "AWAITING_APPROVAL"


def test_expired_approval_window_is_rejected(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    snapshot = _canonical_approval_snapshot(db, intent_id)
    digest = db.execute(
        "select public.execution_snapshot_sha256(%s)", (Jsonb(snapshot),)
    ).fetchone()[0]
    with pytest.raises(psycopg.Error, match="expiry is invalid"):
        with db.transaction():
            db.execute(
                "select public.record_execution_approval(%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, intent_id, "APPROVE", user_id, Jsonb(snapshot), digest,
                 datetime.now(timezone.utc) - timedelta(seconds=1), "0" * 64),
            )

def test_concurrent_intent_creation_is_idempotent_across_sessions(db) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user_id = _new_user(db)
    db.commit()  # Make the fixture user visible to independent PostgreSQL sessions.
    key = f"race-{uuid4()}-idempotency"
    signal = {"signal_id": "signal-race", "symbol": "BTC/USDT", "side": "LONG",
              "quantity": 1.0, "entry_price": 100.0, "stop_loss": 99.0,
              "take_profit": 102.0, "qualified": True}
    account = {"equity": 10000, "source": "test", "account_ref": "test-account"}
    market = {"price": 100, "observed_at": datetime.now(timezone.utc).isoformat()}
    risk = {"risk_pct": 0.5, "risk_policy_version": "test-v1"}
    request_hash = db.execute(
        "select public.execution_intent_request_sha256(%s,%s,%s,%s)",
        (Jsonb(signal), Jsonb(account), Jsonb(market), Jsonb(risk)),
    ).fetchone()[0]
    db.commit()
    barrier = Barrier(2)

    def create():
        with psycopg.connect(DATABASE_URL) as connection:
            barrier.wait(timeout=10)
            return connection.execute(
                "select intent_id, created from public.create_execution_intent(%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, key, request_hash, Jsonb(signal), Jsonb(account), Jsonb(market),
                 Jsonb(risk), _future(120)),
            ).fetchone()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))

    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    assert db.execute(
        "select count(*) from public.execution_intents where user_id=%s and idempotency_key=%s",
        (user_id, key),
    ).fetchone()[0] == 1
    assert db.execute(
        "select count(*) from public.execution_events where intent_id=%s and event_type='INTENT_CREATED'",
        (results[0][0],),
    ).fetchone()[0] == 1


def test_concurrent_approval_race_allows_exactly_one_decision(db) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    db.commit()  # Make user and intent visible to independent PostgreSQL sessions.
    barrier = Barrier(2)

    def approve(decision: str):
        with psycopg.connect(DATABASE_URL) as connection:
            barrier.wait(timeout=10)
            try:
                approval_id = _approve(connection, user_id, intent_id, decision)
                connection.commit()
                return ("ok", approval_id)
            except psycopg.Error as exc:
                connection.rollback()
                return ("rejected", exc.sqlstate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, ("APPROVE", "REJECT")))

    assert sorted(result[0] for result in results) == ["ok", "rejected"]
    assert db.execute(
        "select count(*) from public.execution_approvals where intent_id=%s", (intent_id,)
    ).fetchone()[0] == 1
    assert db.execute(
        "select status from public.execution_intents where id=%s", (intent_id,)
    ).fetchone()[0] in {"APPROVED", "REJECTED"}
    assert db.execute(
        "select count(*) from public.execution_events where intent_id=%s "
        "and event_type in ('APPROVAL_ACCEPTED','APPROVAL_REJECTED')", (intent_id,)
    ).fetchone()[0] == 1

def test_effective_privileges_cover_every_protected_object_and_sequence(db) -> None:
    protected_tables = (
        "execution_intents", "execution_approvals", "execution_approval_challenges", "execution_records", "execution_events"
    )
    mutations = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
    for table in protected_tables:
        qualified = f"public.{table}"
        for role in ("anon", "authenticated", "service_role"):
            assert db.execute(
                "select has_table_privilege(%s, %s, 'SELECT')", (role, qualified)
            ).fetchone()[0] is False, f"{role} unexpectedly has SELECT on {qualified}"
            for privilege in mutations:
                assert db.execute(
                    "select has_table_privilege(%s, %s, %s)",
                    (role, qualified, privilege),
                ).fetchone()[0] is False, f"{role} unexpectedly has {privilege} on {qualified}"

    sequence = "public.execution_events_event_seq_seq"
    for role in ("anon", "authenticated", "service_role"):
        for privilege in ("USAGE", "SELECT", "UPDATE"):
            assert db.execute(
                "select has_sequence_privilege(%s, %s, %s)",
                (role, sequence, privilege),
            ).fetchone()[0] is False, f"{role} unexpectedly has {privilege} on {sequence}"

    for role in ("anon", "authenticated", "service_role", "execution_persistence_owner"):
        assert db.execute(
            "select has_schema_privilege(%s, 'public', 'CREATE')", (role,)
        ).fetchone()[0] is False, f"{role} can create objects in public"

    assert db.execute(
        "select pg_has_role('service_role','execution_persistence_owner','member')"
    ).fetchone()[0] is False
    assert db.execute(
        "select rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, rolinherit "
        "from pg_roles where rolname='execution_persistence_owner'"
    ).fetchone() == (False, False, False, False, False)



def test_concurrent_duplicate_claims_and_conflicting_results_remain_fail_closed(db) -> None:
    """Racing callers cannot turn the disabled claim/result RPCs into execution."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user_id = _new_user(db)
    intent_id, _, key = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id)
    db.commit()
    claim_barrier = Barrier(2)

    def claim():
        with psycopg.connect(DATABASE_URL) as connection:
            claim_barrier.wait(timeout=10)
            try:
                _claim(connection, user_id, intent_id, approval_id)
                connection.commit()
                return ("unexpected-success", None)
            except psycopg.Error as exc:
                connection.rollback()
                return ("denied", exc.sqlstate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claim_results = list(pool.map(lambda _: claim(), range(2)))

    assert all(result[0] == "denied" for result in claim_results)
    assert db.execute(
        "select status from public.execution_intents where id=%s", (intent_id,)
    ).fetchone()[0] == "APPROVED"
    assert db.execute(
        "select count(*) from public.execution_records where intent_id=%s", (intent_id,)
    ).fetchone()[0] == 0

    result_barrier = Barrier(2)

    def record(status: str):
        with psycopg.connect(DATABASE_URL) as connection:
            result_barrier.wait(timeout=10)
            try:
                connection.execute(
                    "select public.record_execution_result(%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, intent_id, approval_id, key, status, None,
                     Jsonb({"source": "adversarial-test", "status": status})),
                )
                connection.commit()
                return ("unexpected-success", None)
            except psycopg.Error as exc:
                connection.rollback()
                return ("denied", exc.sqlstate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        result_results = list(pool.map(record, ("FILLED", "FAILED")))

    assert all(result[0] == "denied" for result in result_results)
    assert db.execute(
        "select count(*) from public.execution_records where intent_id=%s", (intent_id,)
    ).fetchone()[0] == 0
    assert db.execute(
        "select count(*) from public.execution_events where intent_id=%s "
        "and event_type in ('EXECUTION_CLAIMED','EXECUTION_RECORDED','EXECUTION_UNKNOWN')",
        (intent_id,),
    ).fetchone()[0] == 0


def test_effective_privileges_include_inherited_membership_and_default_grants(db) -> None:
    """Check effective grants and default ACLs, not only direct GRANT statements."""
    protected_tables = (
        "execution_intents", "execution_approvals", "execution_approval_challenges", "execution_records", "execution_events"
    )
    untrusted_roles = ("anon", "authenticated", "service_role")
    for role in untrusted_roles:
        assert db.execute(
            "select pg_has_role(%s, 'execution_persistence_owner', 'member')", (role,)
        ).fetchone()[0] is False
        for schema in ("public", "extensions"):
            assert db.execute(
                "select has_schema_privilege(%s, %s, 'CREATE')", (role, schema)
            ).fetchone()[0] is False

    default_grants = db.execute(
        """
        select d.defaclrole::regrole::text, d.defaclnamespace::regnamespace::text,
               d.defaclobjtype, x.grantee, x.privilege_type
        from pg_default_acl d
        cross join lateral aclexplode(d.defaclacl) x
        where (
          x.grantee = 0
          or x.grantee in (select oid from pg_roles where rolname = any(%s))
        )
          and x.privilege_type in (
            'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','USAGE'
          )
        """,
        (list(untrusted_roles),),
    ).fetchall()
    assert default_grants == []

    for role in untrusted_roles:
        for table in protected_tables:
            assert db.execute(
                "select has_table_privilege(%s, %s, 'SELECT')", (role, f"public.{table}")
            ).fetchone()[0] is False
            for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                assert db.execute(
                    "select has_table_privilege(%s, %s, %s)",
                    (role, f"public.{table}", privilege),
                ).fetchone()[0] is False


def test_approval_preview_is_owner_scoped_and_only_returns_pending_intents(db) -> None:
    user_id = _new_user(db)
    other_user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)

    preview = db.execute(
        "select public.get_execution_intent_approval_preview(%s, %s)",
        (user_id, intent_id),
    ).fetchone()[0]
    assert preview["intent_id"] == str(intent_id)
    assert preview["symbol"] == "BTC/USDT"
    assert preview["request_hash"]
    assert preview["risk_policy_version"] == "test-v1"

    with pytest.raises(psycopg.Error, match="missing, expired, not owned"):
        with db.transaction():
            db.execute(
                "select public.get_execution_intent_approval_preview(%s, %s)",
                (other_user_id, intent_id),
            )

    _approve(db, user_id, intent_id)
    with pytest.raises(psycopg.Error, match="missing, expired, not owned"):
        with db.transaction():
            db.execute(
                "select public.get_execution_intent_approval_preview(%s, %s)",
                (user_id, intent_id),
            )


def test_approval_preview_rpc_is_not_executable_by_browser_roles(db) -> None:
    signature = "public.get_execution_intent_approval_preview(uuid,uuid)"
    assert db.execute(
        "select has_function_privilege('anon', %s::regprocedure, 'execute'), "
        "has_function_privilege('authenticated', %s::regprocedure, 'execute'), "
        "has_function_privilege('service_role', %s::regprocedure, 'execute')",
        (signature, signature, signature),
    ).fetchone() == (False, False, True)


def test_same_approval_challenge_is_consumed_once_under_concurrent_replay(db) -> None:
    """Two database sessions racing one signed nonce can commit only one decision."""
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    snapshot = _canonical_approval_snapshot(db, intent_id)
    snapshot_hash = db.execute(
        "select public.execution_snapshot_sha256(%s)", (Jsonb(snapshot),)
    ).fetchone()[0]
    jti_hash = hashlib.sha256(uuid4().hex.encode("utf-8")).hexdigest()
    challenge_expiry = _future(5)
    approval_expiry = _future(60)
    request_hash = snapshot["request_hash"]
    db.execute(
        "select public.register_execution_approval_challenge(%s,%s,%s,%s,%s,%s)",
        (user_id, intent_id, request_hash, "APPROVE", jti_hash, challenge_expiry),
    )
    db.commit()
    barrier = Barrier(2)

    def submit():
        with psycopg.connect(DATABASE_URL) as connection:
            barrier.wait(timeout=10)
            try:
                row = connection.execute(
                    "select public.record_execution_approval(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, intent_id, "APPROVE", user_id, Jsonb(snapshot),
                     snapshot_hash, approval_expiry, jti_hash),
                ).fetchone()
                connection.commit()
                return ("accepted", str(row[0]))
            except psycopg.Error as exc:
                connection.rollback()
                return ("rejected", exc.sqlstate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: submit(), range(2)))

    assert sum(outcome[0] == "accepted" for outcome in outcomes) == 1
    assert sum(outcome[0] == "rejected" for outcome in outcomes) == 1
    assert db.execute(
        "select count(*) from public.execution_approvals where intent_id=%s", (intent_id,)
    ).fetchone()[0] == 1
    assert db.execute(
        "select consumed_at is not null from public.execution_approval_challenges where challenge_jti_hash=%s",
        (jti_hash,),
    ).fetchone()[0] is True
    assert db.execute(
        "select count(*) from public.execution_events where intent_id=%s "
        "and event_type in ('APPROVAL_ACCEPTED','APPROVAL_REJECTED')",
        (intent_id,),
    ).fetchone()[0] == 1


def test_authenticated_api_to_postgres_enforces_owner_and_consumes_challenge(
    db, monkeypatch
) -> None:
    """Exercise the real API and SQL RPCs; only session verification is injected."""
    from fastapi.testclient import TestClient

    from app.api import execution as execution_api
    from app.api.auth import UserResponse
    from app.main import app
    from app.services import execution_persistence
    from app.services.supabase_data import DataRequestError

    owner_id = _new_user(db)
    foreign_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, owner_id)
    db.commit()

    class RpcResponse:
        def __init__(self, value):
            self.value = value

        def json(self):
            return self.value

    def postgres_rpc(method, path, **kwargs):
        assert method == "POST"
        name = path.removeprefix("rpc/")
        payload = kwargs["json"]
        if name == "execution_snapshot_sha256":
            statement, params = (
                "select public.execution_snapshot_sha256(%s)",
                (Jsonb(payload["p_snapshot"]),),
            )
        elif name == "get_execution_intent_approval_preview":
            statement, params = (
                "select public.get_execution_intent_approval_preview(%s,%s)",
                (payload["p_user_id"], payload["p_intent_id"]),
            )
        elif name == "register_execution_approval_challenge":
            statement, params = (
                "select public.register_execution_approval_challenge(%s,%s,%s,%s,%s,%s)",
                (payload["p_user_id"], payload["p_intent_id"], payload["p_request_hash"],
                 payload["p_decision"], payload["p_challenge_jti_hash"], payload["p_expires_at"]),
            )
        elif name == "record_execution_approval":
            statement, params = (
                "select public.record_execution_approval(%s,%s,%s,%s,%s,%s,%s,%s)",
                (payload["p_user_id"], payload["p_intent_id"], payload["p_decision"],
                 payload["p_actor_user_id"], Jsonb(payload["p_approval_snapshot"]),
                 payload["p_snapshot_hash"], payload["p_expires_at"],
                 payload["p_challenge_jti_hash"]),
            )
        else:
            raise AssertionError(f"unexpected RPC: {name}")
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                value = connection.execute(statement, params).fetchone()[0]
        except psycopg.Error as exc:
            raise DataRequestError("PostgreSQL RPC denied the operation.") from exc
        if name == "record_execution_approval":
            value = str(value)
        return RpcResponse(value)

    monkeypatch.setattr(execution_persistence, "service_request", postgres_rpc)
    app.dependency_overrides[execution_api._require_csrf] = lambda: None
    app.dependency_overrides[execution_api.get_current_user] = lambda: UserResponse(
        id=owner_id, email="owner@example.com", account_status="active"
    )
    try:
        with TestClient(app) as client:
            preview_response = client.get(f"/api/execution/intents/{intent_id}/approval-preview")
            assert preview_response.status_code == 200
            preview = preview_response.json()
            challenge_response = client.post(
                f"/api/execution/intents/{intent_id}/approval-challenge",
                json={"decision": "APPROVE", "request_hash": preview["request_hash"]},
            )
            assert challenge_response.status_code == 200
            challenge = challenge_response.json()["challenge"]
            approval_response = client.post(
                f"/api/execution/intents/{intent_id}/approval",
                json={"decision": "APPROVE", "request_hash": preview["request_hash"],
                      "challenge": challenge},
            )
            assert approval_response.status_code == 200
            replay_response = client.post(
                f"/api/execution/intents/{intent_id}/approval",
                json={"decision": "APPROVE", "request_hash": preview["request_hash"],
                      "challenge": challenge},
            )
            assert replay_response.status_code == 409

            app.dependency_overrides[execution_api.get_current_user] = lambda: UserResponse(
                id=foreign_id, email="foreign@example.com", account_status="active"
            )
            foreign_preview = client.get(f"/api/execution/intents/{intent_id}/approval-preview")
            foreign_challenge = client.post(
                f"/api/execution/intents/{intent_id}/approval-challenge",
                json={"decision": "APPROVE", "request_hash": preview["request_hash"]},
            )
            assert foreign_preview.status_code == 404
            assert foreign_challenge.status_code == 404
    finally:
        app.dependency_overrides.clear()

    assert db.execute(
        "select status from public.execution_intents where id=%s", (intent_id,)
    ).fetchone()[0] == "APPROVED"
    assert db.execute(
        "select count(*) from public.execution_approvals where intent_id=%s", (intent_id,)
    ).fetchone()[0] == 1
    assert db.execute(
        "select count(*) from public.execution_events where intent_id=%s "
        "and event_type='APPROVAL_ACCEPTED'", (intent_id,)
    ).fetchone()[0] == 1
    assert db.execute(
        "select consumed_at is not null from public.execution_approval_challenges "
        "where intent_id=%s", (intent_id,)
    ).fetchone()[0] is True


def test_concurrent_conflicting_idempotency_requests_cannot_both_win(db) -> None:
    """Same owner/key with different payloads must produce one winner and one denial."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user_id = _new_user(db)
    key = f"conflict-key-{uuid4().hex}"
    db.commit()
    barrier = Barrier(2)

    def create(symbol: str):
        signal = {
            "signal_id": "concurrent-conflict",
            "symbol": symbol,
            "side": "LONG",
            "quantity": 1.0,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
            "qualified": True,
        }
        account = {"equity": 10000, "source": "test", "account_ref": "test-account"}
        market = {"price": 100, "observed_at": datetime.now(timezone.utc).isoformat()}
        risk = {"risk_pct": 0.5, "risk_policy_version": "test-v1"}
        with psycopg.connect(DATABASE_URL) as connection:
            request_hash = connection.execute(
                "select public.execution_intent_request_sha256(%s,%s,%s,%s)",
                (Jsonb(signal), Jsonb(account), Jsonb(market), Jsonb(risk)),
            ).fetchone()[0]
            barrier.wait(timeout=10)
            try:
                row = connection.execute(
                    "select intent_id, created from public.create_execution_intent(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, key, request_hash, Jsonb(signal), Jsonb(account),
                     Jsonb(market), Jsonb(risk), _future(120)),
                ).fetchone()
                connection.commit()
                return ("created" if row[1] else "existing", str(row[0]))
            except psycopg.Error as exc:
                connection.rollback()
                return ("rejected", exc.sqlstate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, ("BTC/USDT", "ETH/USDT")))

    assert sum(outcome[0] in {"created", "existing"} for outcome in outcomes) == 1
    assert sum(outcome[0] == "rejected" for outcome in outcomes) == 1
    assert db.execute(
        "select count(*) from public.execution_intents where user_id=%s and idempotency_key=%s",
        (user_id, key),
    ).fetchone()[0] == 1
    assert db.execute(
        "select count(*) from public.execution_events e join public.execution_intents i on i.id=e.intent_id "
        "where i.user_id=%s and i.idempotency_key=%s and e.event_type='INTENT_CREATED'",
        (user_id, key),
    ).fetchone()[0] == 1


def test_expired_approval_challenge_cannot_be_consumed(db) -> None:
    import hashlib

    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    snapshot = _canonical_approval_snapshot(db, intent_id)
    snapshot_hash = db.execute(
        "select public.execution_snapshot_sha256(%s)", (Jsonb(snapshot),)
    ).fetchone()[0]
    jti_hash = hashlib.sha256(uuid4().hex.encode("utf-8")).hexdigest()
    db.execute(
        """
        insert into public.execution_approval_challenges(
          challenge_jti_hash, intent_id, user_id, request_hash, decision,
          expires_at, created_at
        ) values (%s,%s,%s,%s,'APPROVE',now()-interval '1 minute',now()-interval '10 minutes')
        """,
        (jti_hash, intent_id, user_id, snapshot["request_hash"]),
    )
    with pytest.raises(psycopg.Error, match="missing, expired, mismatched, or already consumed"):
        with db.transaction():
            db.execute(
                "select public.record_execution_approval(%s,%s,'APPROVE',%s,%s,%s,%s,%s)",
                (user_id, intent_id, user_id, Jsonb(snapshot), snapshot_hash, _future(60), jti_hash),
            )
    assert db.execute(
        "select status from public.execution_intents where id=%s", (intent_id,)
    ).fetchone()[0] == "AWAITING_APPROVAL"
    assert db.execute(
        "select count(*) from public.execution_approvals where intent_id=%s", (intent_id,)
    ).fetchone()[0] == 0
