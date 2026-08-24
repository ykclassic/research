from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings

PASSWORD_ITERATIONS = 600_000
SALT_BYTES = 16
TOKEN_BYTES = 32


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _db_path() -> Path:
    path = Path(settings.auth_database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0 CHECK (disabled IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
                ON sessions(token_hash);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id
                ON sessions(user_id);
            """
        )


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def hash_password(password: str) -> str:
    return _hash_password(password, secrets.token_bytes(SALT_BYTES))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def create_user(email: str, password: str) -> dict[str, str]:
    user_id = secrets.token_urlsafe(18)
    created_at = utc_now().isoformat()
    password_hash = hash_password(password)

    try:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, email, password_hash, created_at),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with that email already exists.") from exc

    return {"id": user_id, "email": email, "created_at": created_at}


def authenticate_user(email: str, password: str) -> dict[str, str] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, email, password_hash, created_at, disabled FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if row is None or row["disabled"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None

    return {
        "id": row["id"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def create_session(user_id: str) -> tuple[str, datetime]:
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    created_at = utc_now()
    expires_at = created_at + timedelta(seconds=settings.auth_session_seconds)

    with _connect() as connection:
        connection.execute(
            "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (
                secrets.token_urlsafe(18),
                user_id,
                token_hash,
                created_at.isoformat(),
                expires_at.isoformat(),
            ),
        )
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (created_at.isoformat(),))

    return raw_token, expires_at


def get_user_by_session(raw_token: str) -> dict[str, str] | None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = utc_now().isoformat()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT u.id, u.email, u.created_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
              AND u.disabled = 0
            """,
            (token_hash, now),
        ).fetchone()

    if row is None:
        return None
    return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}


def revoke_session(raw_token: str) -> None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with _connect() as connection:
        connection.execute(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (utc_now().isoformat(), token_hash),
        )
