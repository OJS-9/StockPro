"""
WebSocket: JSON request/response snapshots from `price_cache` (authenticated users).

Client sends: {"symbols": ["AAPL", "MSFT"]} (max N per STOCKPRO_WS_MAX_SYMBOLS, default 50).
Server replies: {"type": "prices", "data": { "AAPL": { ... } | null, ... }}.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from flask import session

logger = logging.getLogger(__name__)


def _max_symbols() -> int:
    try:
        return max(1, min(200, int(os.getenv("STOCKPRO_WS_MAX_SYMBOLS", "50"))))
    except ValueError:
        return 50


def normalize_symbols(raw: Any, max_n: int) -> List[str]:
    """Uppercase, dedupe, cap length, strip; max_n symbols."""
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        u = item.strip().upper()[:32]
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= max_n:
            break
    return out


def parse_symbols_message(data: str) -> Optional[List[str]]:
    """Parse JSON body; expect object with `symbols` list. Returns None if invalid."""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    sym = obj.get("symbols")
    if not isinstance(sym, list):
        return None
    return normalize_symbols(sym, _max_symbols())


def _row_to_dict(row: Any) -> Dict[str, Any]:
    lu = row.get("last_updated")
    return {
        "symbol": row["symbol"],
        "asset_type": row.get("asset_type"),
        "price": float(row["price"]) if row.get("price") is not None else None,
        "change_percent": (
            float(row["change_percent"])
            if row.get("change_percent") is not None
            else None
        ),
        "display_name": row.get("display_name"),
        "last_updated": lu.isoformat() if lu is not None else None,
    }


def fetch_prices_snapshot(symbols: List[str]) -> Dict[str, Any]:
    """Load `price_cache` rows for symbols; missing symbols map to None."""
    if not symbols:
        return {}
    from database import get_database_manager

    db = get_database_manager()
    rows = db.get_cached_prices(symbols)
    return {s: _row_to_dict(rows[s]) if s in rows else None for s in symbols}


def register_ws_routes(app) -> None:
    from flask_sock import Sock

    sock = Sock(app)

    @sock.route("/ws/prices")
    def prices_ws(ws):
        if not session.get("user_id"):
            try:
                ws.close(reason=1008)
            except Exception:
                pass
            return

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                symbols = parse_symbols_message(raw)
                if symbols is None:
                    ws.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": 'Expected JSON: {"symbols": ["AAPL", ...]}',
                            }
                        )
                    )
                    continue
                payload = fetch_prices_snapshot(symbols)
                ws.send(json.dumps({"type": "prices", "data": payload}))
        except Exception as e:
            logger.warning("ws /ws/prices closed: %s", e)
            try:
                ws.close()
            except Exception:
                pass
