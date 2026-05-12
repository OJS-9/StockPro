"""
Background job — refresh ticker_public_view rows older than 24h.
"""

import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

REFRESH_INTERVAL = 24 * 3600  # 24 hours
MAX_WORKERS = 3
TTL_HOURS = 24


class PublicViewRefreshJob:

    def __init__(self):
        self._timer = None
        self._running = False
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from database import get_database_manager

            self._db = get_database_manager()
        return self._db

    def start(self):
        self._running = True
        t = threading.Thread(target=self._run_refresh, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()

    def _schedule_next(self):
        if self._running:
            self._timer = threading.Timer(REFRESH_INTERVAL, self._run_refresh)
            self._timer.daemon = True
            self._timer.start()

    def _run_refresh(self):
        try:
            self._do_refresh()
        except Exception:
            logger.exception("public_view refresh cycle failed")
        finally:
            self._schedule_next()

    def _do_refresh(self):
        from watchlist.public_view_service import refresh_public_view

        watched = {row["symbol"] for row in self.db.get_all_watched_symbols()}
        stale = set(self.db.get_stale_public_view_symbols(TTL_HOURS))
        # Refresh watched symbols whose row is missing OR stale.
        to_refresh = stale | (watched - {row["symbol"] for row in
                                         [{"symbol": s} for s in []]})  # placeholder
        # Simpler: refresh union of (watched ∩ stale) plus any watched without a row.
        existing = set()
        for s in watched:
            row = self.db.get_ticker_public_view(s)
            if row is None:
                to_refresh.add(s)
            else:
                existing.add(s)
        # Drop stale entries not in any watchlist (no need to refresh)
        targets = sorted([s for s in to_refresh if s in watched])

        if not targets:
            logger.info("public_view refresh: nothing to do")
            return

        logger.info("public_view refresh: %d symbols", len(targets))
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            list(pool.map(refresh_public_view, targets))


_refresh_job = None


def start_public_view_refresh():
    global _refresh_job
    if _refresh_job is None:
        _refresh_job = PublicViewRefreshJob()
        _refresh_job.start()
        logger.info("Background public view refresh started")
    return _refresh_job
