"""
Long-lived API tokens for CLI / headless agents.

Tokens are issued either via the device-code flow (agent prints a user code,
master approves in browser) or directly from the Settings UI. Tokens are
stored as SHA-256 hashes; the raw token is only returned once on creation.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2.extras

from database import get_database_manager

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "sp_"
# Crockford-ish alphabet: no 0, O, 1, I, L.
_USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_USER_CODE_LEN = 8
_DEVICE_CODE_TTL = timedelta(minutes=10)
_LAST_USED_THROTTLE = timedelta(minutes=1)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_user_code() -> str:
    return "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(_USER_CODE_LEN))


def format_user_code(code: str) -> str:
    """Insert a hyphen for display: ABCD1234 -> ABCD-1234."""
    if len(code) == 8:
        return f"{code[:4]}-{code[4:]}"
    return code


def normalize_user_code(raw: str) -> str:
    """Strip whitespace/hyphens, uppercase. Users may paste 'abcd-1234' or ' AbCd1234 '."""
    return "".join(ch for ch in raw.upper() if ch in _USER_CODE_ALPHABET)


# ----- API key CRUD -----


def create_api_key(user_id: str, name: str) -> tuple[str, str]:
    """Issue a new token. Returns (api_key_id, raw_token). Raw token is shown once."""
    raw_bytes = secrets.token_urlsafe(32)
    raw_token = f"{TOKEN_PREFIX}{raw_bytes}"
    prefix = raw_token[: len(TOKEN_PREFIX) + 4]
    token_hash = _hash_token(raw_token)
    api_key_id = str(uuid.uuid4())

    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_keys (id, user_id, name, token_hash, prefix)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (api_key_id, user_id, name[:100], token_hash, prefix),
            )
        conn.commit()
    finally:
        db._release(conn)
    return api_key_id, raw_token


def verify_token(raw_token: str) -> Optional[str]:
    """Look up a token; return user_id if valid (not revoked), else None.

    Also refreshes last_used_at at most once per minute to avoid a DB write per call.
    """
    if not raw_token or not raw_token.startswith(TOKEN_PREFIX):
        return None
    token_hash = _hash_token(raw_token)

    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, user_id, last_used_at, revoked_at
                FROM api_keys WHERE token_hash = %s
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row or row["revoked_at"] is not None:
                return None
            now = datetime.now(timezone.utc)
            last_used = row["last_used_at"]
            if last_used is None or (now - last_used) > _LAST_USED_THROTTLE:
                cur.execute(
                    "UPDATE api_keys SET last_used_at = %s WHERE id = %s",
                    (now, row["id"]),
                )
                conn.commit()
            return row["user_id"]
    finally:
        db._release(conn)


def list_api_keys(user_id: str) -> list[dict]:
    """Return non-revoked keys for this user. Never includes hash/raw token."""
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, prefix, created_at, last_used_at
                FROM api_keys
                WHERE user_id = %s AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        db._release(conn)
    # Convert timestamps to ISO strings for JSON
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "prefix": r["prefix"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            }
        )
    return out


def revoke_api_key(user_id: str, key_id: str) -> bool:
    """Mark a key revoked. Returns True if something was revoked."""
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE api_keys SET revoked_at = NOW()
                WHERE id = %s AND user_id = %s AND revoked_at IS NULL
                """,
                (key_id, user_id),
            )
            changed = cur.rowcount
        conn.commit()
    finally:
        db._release(conn)
    return changed > 0


# ----- Device-code flow -----


def create_device_code() -> dict:
    """Register a pending device authorization. Returns flow parameters (no secrets for other users)."""
    device_code = secrets.token_urlsafe(48)
    # Retry to avoid collisions on the short user_code
    for _ in range(5):
        user_code = _generate_user_code()
        try:
            db = get_database_manager()
            conn = db.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO device_codes (device_code, user_code, expires_at)
                        VALUES (%s, %s, NOW() + INTERVAL '10 minutes')
                        """,
                        (device_code, user_code),
                    )
                conn.commit()
                break
            finally:
                db._release(conn)
        except psycopg2.IntegrityError:
            # user_code collision, try another
            continue
    else:
        raise RuntimeError("Could not generate a unique user code")

    return {
        "device_code": device_code,
        "user_code": format_user_code(user_code),
        "expires_in": int(_DEVICE_CODE_TTL.total_seconds()),
        "interval": 5,
    }


def poll_device_code(device_code: str) -> dict:
    """Return one of:
      {"status": "pending"}
      {"status": "expired"}
      {"status": "approved", "access_token": "sp_..."}  <-- only once, row is deleted after
      {"status": "unknown"}  <-- device_code not found
    """
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, api_key_id, expires_at, approved_at FROM device_codes WHERE device_code = %s",
                (device_code,),
            )
            row = cur.fetchone()
            if not row:
                return {"status": "unknown"}

            now = datetime.now(timezone.utc)
            expires_at = row["expires_at"]
            if expires_at and expires_at < now:
                cur.execute("DELETE FROM device_codes WHERE device_code = %s", (device_code,))
                conn.commit()
                return {"status": "expired"}

            if row["approved_at"] is None:
                return {"status": "pending"}

            # Approved: issue the raw token once and delete the row.
            # The raw token was never stored — we need to regenerate via a fresh api_key.
            # To avoid this, the approve step stores the raw token transiently on the device_codes row.
            # Simplest implementation: keep a plaintext column for 10 minutes max.
            # We'll add a small column `access_token` below in approve flow.
            # (See approve_device_code — it stashes the raw token on the row.)
            cur.execute(
                "SELECT access_token FROM device_codes WHERE device_code = %s",
                (device_code,),
            )
            token_row = cur.fetchone()
            cur.execute("DELETE FROM device_codes WHERE device_code = %s", (device_code,))
            conn.commit()
            return {
                "status": "approved",
                "access_token": token_row["access_token"] if token_row else None,
            }
    finally:
        db._release(conn)


def approve_device_code(user_id: str, user_code: str) -> dict:
    """Approve a user_code for a user. Issues an api_key and stashes the raw token on the device_codes row
    so the next poll can hand it back. Returns {status, token_name} or {error}.

    Uses a single connection for the whole flow -- avoids nesting pool.getconn() calls
    which was contributing to pool exhaustion under load.
    """
    code = normalize_user_code(user_code)
    if len(code) != _USER_CODE_LEN:
        return {"error": "invalid_code"}

    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT device_code, expires_at, approved_at FROM device_codes WHERE user_code = %s",
                (code,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": "unknown_code"}

            now = datetime.now(timezone.utc)
            if row["expires_at"] and row["expires_at"] < now:
                return {"error": "expired"}
            if row["approved_at"] is not None:
                return {"error": "already_approved"}

            # Issue token on THIS connection (don't nest get_connection).
            raw_bytes = secrets.token_urlsafe(32)
            raw_token = f"{TOKEN_PREFIX}{raw_bytes}"
            prefix = raw_token[: len(TOKEN_PREFIX) + 4]
            token_hash = _hash_token(raw_token)
            api_key_id = str(uuid.uuid4())
            name = f"CLI device ({code[:4]})"

            cur.execute(
                """
                INSERT INTO api_keys (id, user_id, name, token_hash, prefix)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (api_key_id, user_id, name[:100], token_hash, prefix),
            )

            cur.execute(
                """
                UPDATE device_codes
                SET user_id = %s, api_key_id = %s, approved_at = NOW(), access_token = %s
                WHERE device_code = %s
                """,
                (user_id, api_key_id, raw_token, row["device_code"]),
            )
        conn.commit()
        return {"status": "approved", "token_name": name}
    finally:
        db._release(conn)
