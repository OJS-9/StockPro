"""
Send the weekly portfolio digest email (issue #129).

Run Monday morning (e.g. via a Railway cron service, recommended schedule
`0 13 * * 1` UTC -- about 9am US Eastern). Claims eligible users atomically
(at least one holding, weekly_summary notification not turned off, not sent in
the last 6 days), computes each user's week-over-week performance, and emails a
digest. On a send failure the dedupe flag is cleared so the user is retried on
the next run.

Usage:
    python scripts/send_weekly_digest.py

Requires DATABASE_URL, BREVO_API_KEY, and ALERT_FROM_SENDER in the environment.
"""

import logging
import os
import sys

from dotenv import load_dotenv

# Make src/ importable whether run from the project root or elsewhere.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

try:
    load_dotenv()
except Exception as e:  # pragma: no cover - .env is optional in prod
    print(f"Warning: could not load .env file: {e}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("send_weekly_digest")


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set")
        return 1

    from database import get_database_manager
    from email_service import send_weekly_digest_email
    from portfolio.portfolio_service import get_portfolio_service

    db = get_database_manager()
    portfolio_service = get_portfolio_service()

    candidates = db.claim_weekly_digest_candidates()
    logger.info("Weekly digest: %d candidate(s) claimed", len(candidates))

    sent = 0
    skipped = 0
    failed = 0
    for c in candidates:
        try:
            data = portfolio_service.get_weekly_performance(c["user_id"])
        except Exception:
            logger.exception("Failed to compute weekly performance for a user")
            data = None

        if not data:
            # Nothing worth emailing (e.g. holdings sold since the claim). Clear
            # the flag so the user is reconsidered next week.
            skipped += 1
            try:
                db.reset_weekly_digest_flag(c["user_id"])
            except Exception:
                logger.exception("Failed to reset weekly digest flag for a user")
            continue

        ok = send_weekly_digest_email(
            email=c["email"],
            username=c["username"],
            data=data,
            language=c.get("language", "en"),
        )
        if ok:
            sent += 1
        else:
            failed += 1
            # Reset so the next run retries this user.
            try:
                db.reset_weekly_digest_flag(c["user_id"])
            except Exception:
                logger.exception("Failed to reset weekly digest flag for a user")

    logger.info("Weekly digest: sent=%d skipped=%d failed=%d", sent, skipped, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
