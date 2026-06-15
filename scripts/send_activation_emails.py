"""
Send the 24h post-signup activation email (issue #120).

Run hourly (e.g. via a Railway cron service). Claims eligible users atomically
(signed up 23-25h ago, no portfolio, not yet emailed), sends each a nudge to add
their researched ticker to a portfolio, and resets the flag on any send failure
so the user is retried on the next run (still inside the 23-25h window).

Usage:
    python scripts/send_activation_emails.py

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
logger = logging.getLogger("send_activation_emails")


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set")
        return 1

    from database import get_database_manager
    from email_service import send_activation_email

    db = get_database_manager()
    candidates = db.claim_activation_email_candidates()
    logger.info("Activation email: %d candidate(s) claimed", len(candidates))

    sent = 0
    failed = 0
    for c in candidates:
        ok = send_activation_email(
            email=c["email"],
            username=c["username"],
            ticker=c.get("ticker"),
            language=c.get("language", "en"),
        )
        if ok:
            sent += 1
        else:
            failed += 1
            # Reset so the next run retries this user (still within the window).
            try:
                db.reset_activation_email_flag(c["user_id"])
            except Exception:
                logger.exception("Failed to reset activation flag for a user")

    logger.info("Activation email: sent=%d failed=%d", sent, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
