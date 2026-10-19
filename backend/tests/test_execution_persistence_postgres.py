from __future__ import annotations

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
    rows = db.execute(
        """select intent_id, created from public.create_execution_intent(
          %s, %s, %s, %s, %s, %s, %s, %s
        )""",
        (
            user_id,
            key,
            "a" * 64,
            Jsonb({"signal_id": "signal-test", "qualified": True}),
            Jsonb({"equity": 10000, "source": "test"}),
            Jsonb({"price": 100, "observed_at": datetime.now(timezone.utc).isoformat()}),
            Jsonb({"risk_pct": 0.5, "policy_version": "test-v1"}),
            _future(120),
        ),
    ).fetchone()
    return rows[0], rows[1], key


def _approve(db, user_id: str, intent_id, decision: str = "APPROVE"):
    return db.execute(
        """select public.record_execution_approval(%s, %s, %s, %s, %s, %s, %s)""",
        (
            user_id,
            intent_id,
            decision,
            user_id,
            Jsonb({"intent_id": str(intent_id), "human_confirmed": True}),
            "b" * 64,
            _future(60),
        ),
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

    assert db.execute("select status from public.execution_intents where id=%s", (intent_id,)).fetchone()[0] == "APPROVED"
    with pytest.raises(psycopg.Error):
        with db.transaction():
            _approve(db, user_id, intent_id)


def test_rejected_proposal_cannot_be_claimed(db) -> None:
    user_id = _new_user(db)
    intent_id, _, _ = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id, "REJECT")

    with pytest.raises(psycopg.Error, match="not executable"):
        with db.transaction():
            db.execute("select public.claim_execution(%s, %s, %s)", (user_id, intent_id, approval_id))


def test_claim_is_atomic_single_use_and_execution_record_is_immutable(db) -> None:
    user_id = _new_user(db)
    intent_id, _, key = _create_intent(db, user_id)
    approval_id = _approve(db, user_id, intent_id)

    assert db.execute("select public.claim_execution(%s, %s, %s)", (user_id, intent_id, approval_id)).fetchone()[0] is True
    with pytest.raises(psycopg.Error, match="not executable"):
        with db.transaction():
            db.execute("select public.claim_execution(%s, %s, %s)", (user_id, intent_id, approval_id))

    # The second claim did not corrupt the already-committed-in-transaction state.
    assert db.execute("select status from public.execution_intents where id=%s", (intent_id,)).fetchone()[0] == "APPROVED"
    with db.transaction():
        db.execute("select public.claim_execution(%s, %s, %s)", (user_id, intent_id, approval_id))
    record_id = db.execute(
        """select public.record_execution_result(%s, %s, %s, %s, %s, %s, %s)""",
        (user_id, intent_id, approval_id, f"execution-{uuid4()}", "FILLED", "TEST-BROKER-1", Jsonb({"fill_price": 100.1})),
    ).fetchone()[0]
    with pytest.raises(psycopg.Error, match="append-only"):
        with db.transaction():
            db.execute("delete from public.execution_records where id=%s", (record_id,))


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
          'execution_intents','execution_approvals','execution_records','execution_events'
        ) order by c.relname"""
    ).fetchall()
    assert len(rows) == 4
    assert all(row[1] is True and row[2] is False and row[3] is False for row in rows)
