"""
OAuth Transaction & Handoff Ticket Cleanup Utility

Removes expired OAuth state transactions and consumed/expired handoff tickets
from the database. Can be run periodically (e.g., via cron or background job).

Usage:
    python -m app.scripts.cleanup_oauth_state
"""

import logging
import sys

from app.db.session import SessionLocal
from app.services.google_auth_service import cleanup_expired_oauth_transactions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ccms.cleanup_oauth_state")


def run_cleanup() -> int:
    db = SessionLocal()
    try:
        deleted = cleanup_expired_oauth_transactions(db)
        logger.info("Successfully cleaned up %d expired OAuth records.", deleted)
        return deleted
    except Exception as e:
        logger.error("Failed to clean up expired OAuth records: %s", str(e))
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        count = run_cleanup()
        sys.exit(0)
    except Exception:
        sys.exit(1)
