"""
Background Sync Scheduler

Automatically syncs transactions from all connected Plaid accounts
every 4 hours using APScheduler.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def sync_all_accounts_job():
    """Background job: sync all connected accounts."""
    from ..database import SessionLocal
    from ..models import Account
    from .plaid_service import plaid_service

    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(
            Account.plaid_connection_status == "connected"
        ).all()

        if not accounts:
            logger.debug("No connected accounts to sync")
            return

        logger.info(f"Scheduler: syncing {len(accounts)} connected account(s)")

        for account in accounts:
            try:
                result = plaid_service.sync_transactions(account, db)
                logger.info(
                    f"  {account.name}: +{result['added']} ~{result['modified']} -{result['removed']}"
                )
            except Exception as e:
                logger.error(f"  {account.name}: sync failed — {e}")

    except Exception as e:
        logger.error(f"Scheduler job failed: {e}")
    finally:
        db.close()


def start_scheduler():
    """Start the background sync scheduler (called from main.py lifespan)."""
    if scheduler.running:
        logger.debug("Scheduler already running")
        return

    scheduler.add_job(
        sync_all_accounts_job,
        trigger=IntervalTrigger(hours=4),
        id="plaid_sync_all",
        name="Sync all Plaid accounts",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Plaid sync scheduler started (every 4 hours)")


def stop_scheduler():
    """Stop the scheduler gracefully (called from main.py lifespan)."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Plaid sync scheduler stopped")
