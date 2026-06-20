"""
Send the 7-day report expiry nudge email (issue #130).

Run daily (e.g. via a Railway cron service, recommended schedule `0 14 * * *`
UTC -- about 9-10am US Eastern). Claims eligible reports atomically (created
7-14 days ago, not yet nudged, newest report for that user+ticker, user has not
turned off the 'report_expiry' notification preference) and emails each user a
nudge to regenerate. On a send failure the per-report flag is cleared so the
report is retried on the next run.

Usage:
    python scripts/send_report_expiry_nudges.py
    python scripts/send_report_expiry_nudges.py --only-user <user_id>

Pass --only-user to restrict the run to a single user. This is the SAFE way to
test against the production database: it guarantees no real user's report can be
claimed or emailed. The unscoped form (no flag) is what the production cron runs.

Requires DATABASE_URL, BREVO_API_KEY, and ALERT_FROM_SENDER in the environment.
"""

import argparse
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
logger = logging.getLogger("send_report_expiry_nudges")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send 7-day report expiry nudges (#130)")
    parser.add_argument(
        "--only-user",
        dest="only_user",
        default=None,
        help="Restrict the run to a single user_id (safe testing).",
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set")
        return 1

    from database import get_database_manager
    from email_service import send_report_expiry_email

    db = get_database_manager()

    if args.only_user:
        logger.info("Report expiry: scoped to a single user (test mode)")

    candidates = db.claim_report_expiry_candidates(only_user_id=args.only_user)
    logger.info("Report expiry: %d report(s) claimed", len(candidates))

    sent = 0
    failed = 0
    for c in candidates:
        ok = send_report_expiry_email(
            email=c["email"],
            username=c["username"],
            ticker=c["ticker"],
            language=c.get("language", "en"),
        )
        if ok:
            sent += 1
        else:
            failed += 1
            # Reset so the next run retries this report (still inside the window).
            try:
                db.reset_report_expiry_flag(c["report_id"])
            except Exception:
                logger.exception("Failed to reset report expiry flag for a report")

    logger.info("Report expiry: sent=%d failed=%d", sent, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
