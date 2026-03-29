"""
Alpaca Markets REST client (paper trading by default).

Uses env vars from `.env.example`: APCA_API_KEY_ID, APCA_API_SECRET_KEY, ALPACA_BASE_URL.
See https://docs.alpaca.markets/docs/authentication
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

DEFAULT_PAPER_BASE = "https://paper-api.alpaca.markets"


class AlpacaConfigError(RuntimeError):
    """Raised when required Alpaca credentials are missing."""


class AlpacaClient:
    """Thin wrapper around Alpaca REST v2 (account snapshot first; orders later)."""

    def __init__(self, key_id: str, secret_key: str, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
        }

    @classmethod
    def from_env(cls) -> AlpacaClient:
        key_id = (os.getenv("APCA_API_KEY_ID") or "").strip()
        secret = (os.getenv("APCA_API_SECRET_KEY") or "").strip()
        base = (os.getenv("ALPACA_BASE_URL") or DEFAULT_PAPER_BASE).strip()
        if not key_id or not secret:
            raise AlpacaConfigError(
                "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY (see .env.example)"
            )
        return cls(key_id, secret, base)

    @classmethod
    def from_env_optional(cls) -> Optional[AlpacaClient]:
        """Return a client if keys are set; otherwise None (no exception)."""
        try:
            return cls.from_env()
        except AlpacaConfigError:
            return None

    def get_account(self) -> Dict[str, Any]:
        """GET /v2/account — returns Alpaca JSON (id, status, equity, ...)."""
        url = f"{self._base}/v2/account"
        resp = requests.get(url, headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
