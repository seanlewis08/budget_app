"""
Background Sync Scheduler

Automatically syncs transactions and investment data from all connected
Plaid accounts using APScheduler.

Jobs:
- plaid_sync_all: Sync bank transactions every 4 hours
- investment_sync: Sync investment holdings + transactions every 6 hours
- price_refresh: Refresh stock prices every 30 minutes during market hours
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def sync_all_accounts_job():
    """Background job: sync all connected bank accounts."""
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
                result = plaid_service.sync_transactions(account, db, trigger="scheduled")
                logger.info(
                    f"  {account.name}: +{result['added']} ~{result['modified']} -{result['removed']}"
                )
            except Exception as e:
                logger.error(f"  {account.name}: sync failed — {e}")

    except Exception as e:
        logger.error(f"Scheduler job failed: {e}")
    finally:
        db.close()


def sync_investments_job():
    """Background job: sync all investment accounts (holdings + transactions)."""
    from ..investments_database import SessionLocal as InvSessionLocal
    from ..models_investments import InvestmentAccount
    from ..database import SessionLocal
    from ..models import Account
    from .plaid_service import plaid_service

    inv_db = InvSessionLocal()
    budget_db = SessionLocal()
    try:
        inv_accounts = inv_db.query(InvestmentAccount).filter(
            InvestmentAccount.connection_status == "connected"
        ).all()

        if not inv_accounts:
            logger.debug("No investment accounts to sync")
            return

        logger.info(f"Scheduler: syncing {len(inv_accounts)} investment account(s)")

        for inv_account in inv_accounts:
            try:
                # Find the corresponding budget Account to get the encrypted access token
                budget_account = budget_db.query(Account).filter(
                    Account.plaid_item_id == inv_account.plaid_item_id
                ).first()

                if not budget_account or not budget_account.plaid_access_token:
                    logger.warning(f"  {inv_account.account_name}: no access token found")
                    continue

                # Sync holdings
                h_result = plaid_service.sync_investment_holdings(
                    budget_account.plaid_access_token, inv_account, inv_db
                )
                logger.info(
                    f"  {inv_account.account_name} holdings: "
                    f"{h_result['securities_upserted']} securities, "
                    f"{h_result['holdings_upserted']} holdings"
                )

                # Sync transactions
                t_result = plaid_service.sync_investment_transactions(
                    budget_account.plaid_access_token, inv_account, inv_db
                )
                logger.info(
                    f"  {inv_account.account_name} transactions: "
                    f"+{t_result['added']} skipped={t_result['skipped']}"
                )
            except Exception as e:
                logger.error(f"  {inv_account.account_name}: sync failed — {e}")
                inv_account.last_sync_error = str(e)[:500]
                inv_db.commit()

    except Exception as e:
        logger.error(f"Investment sync job failed: {e}")
    finally:
        inv_db.close()
        budget_db.close()


def fetch_prices_job():
    """Background job: refresh stock prices via yfinance (only during market hours)."""
    from .price_fetcher import is_market_open, fetch_all_prices
    from ..investments_database import SessionLocal as InvSessionLocal

    if not is_market_open():
        logger.debug("Market closed — skipping price refresh")
        return

    inv_db = InvSessionLocal()
    try:
        result = fetch_all_prices(inv_db)
        if result["updated"] > 0 or result["failed"] > 0:
            logger.info(
                f"Price refresh: {result['updated']} updated, {result['failed']} failed"
            )
    except Exception as e:
        logger.error(f"Price refresh job failed: {e}")
    finally:
        inv_db.close()


def start_scheduler():
    """Start the background sync scheduler (called from main.py lifespan)."""
    if scheduler.running:
        logger.debug("Scheduler already running")
        return

    # Bank transaction sync — every 4 hours
    scheduler.add_job(
        sync_all_accounts_job,
        trigger=IntervalTrigger(hours=4),
        id="plaid_sync_all",
        name="Sync all Plaid accounts",
        replace_existing=True,
    )

    # Investment holdings + transactions sync — every 6 hours
    scheduler.add_job(
        sync_investments_job,
        trigger=IntervalTrigger(hours=6),
        id="investment_sync",
        name="Sync investment accounts",
        replace_existing=True,
    )

    # Stock price refresh — every 30 minutes, weekdays 9:30-16:30 ET
    scheduler.add_job(
        fetch_prices_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-16",
            minute="0,30",
            timezone="US/Eastern",
        ),
        id="price_refresh",
        name="Refresh stock prices",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: bank sync (4h), investment sync (6h), "
        "price refresh (30min during market hours)"
    )


def stop_scheduler():
    """Stop the scheduler gracefully (called from main.py lifespan)."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
