"""
AES-256-GCM field-level encryption for sensitive database columns.

Usage:
    from encryption import encrypt, decrypt, hmac_email

    stored = encrypt("user@example.com")   # store this in DB
    plain  = decrypt(stored)               # decrypt when reading
    hash   = hmac_email("user@example.com") # use for indexed lookup
"""

import os
import base64
import hmac
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_key_hex = os.getenv("ENCRYPTION_KEY", "").strip()
_KEY: bytes | None = bytes.fromhex(_key_hex) if _key_hex else None


def _require_key() -> bytes:
    if _KEY is None:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return _KEY


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns a base64 string (nonce + ciphertext)."""
    key = _require_key()
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, value.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(value: str) -> str:
    """Decrypt a base64 ciphertext produced by encrypt(). Falls back to plaintext if not valid ciphertext."""
    if not value:
        return value
    key = _require_key()
    try:
        data = base64.b64decode(value)
        if len(data) < 28:  # 12 nonce + 16 GCM tag minimum
            return value
        return AESGCM(key).decrypt(data[:12], data[12:], None).decode()
    except Exception:
        # Value is still plaintext (pre-migration) — return as-is
        return value


def hmac_email(email: str) -> str:
    """HMAC-SHA256 of a normalised email. Use for indexed/unique lookups in the DB."""
    key = _require_key()
    return hmac.new(key, email.strip().lower().encode(), hashlib.sha256).hexdigest()
