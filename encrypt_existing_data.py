"""
One-time migration: encrypt existing plaintext email and telegram_chat_id values in the users table.

Run once after setting ENCRYPTION_KEY in your .env:
    python encrypt_existing_data.py
"""

import sys
import os
from pathlib import Path

# Allow imports from src/
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from encryption import encrypt, hmac_email, decrypt

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set in .env")
    sys.exit(1)

if not os.getenv("ENCRYPTION_KEY"):
    print("ERROR: ENCRYPTION_KEY is not set in .env")
    print('Generate one with: python -c "import secrets; print(secrets.token_hex(32))"')
    sys.exit(1)


def looks_encrypted(value: str) -> bool:
    """Quick check: base64-encoded AES-GCM output is always longer than a raw email."""
    import base64
    try:
        data = base64.b64decode(value)
        return len(data) >= 28  # 12 nonce + 16 GCM tag minimum
    except Exception:
        return False


def main():
    conn = psycopg2.connect(DATABASE_URL)

    # Add email_hash column if it doesn't exist yet
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS email_hash VARCHAR(64)
        """)
    conn.commit()

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT user_id, email, telegram_chat_id FROM users")
    users = cur.fetchall()

    migrated = 0
    for user in users:
        user_id = user["user_id"]
        email = user["email"]
        tg = user["telegram_chat_id"]

        new_email = email if looks_encrypted(email) else encrypt(email)
        new_hash = hmac_email(decrypt(new_email))  # always recompute from plaintext
        new_tg = tg if (tg is None or looks_encrypted(tg)) else encrypt(tg)

        with conn.cursor() as update_cur:
            update_cur.execute(
                "UPDATE users SET email = %s, email_hash = %s, telegram_chat_id = %s WHERE user_id = %s",
                (new_email, new_hash, new_tg, user_id),
            )
        migrated += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. {migrated} user(s) migrated.")


if __name__ == "__main__":
    main()
