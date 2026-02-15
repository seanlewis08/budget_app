#!/usr/bin/env python3
"""
Budget App Sync Daemon

Standalone script that syncs all connected Plaid accounts and optionally
backs up the database to a private Git repository.

Designed to run as a macOS LaunchAgent (or cron job) independently
of the main Electron/FastAPI app.

Writes to the same ~/BudgetApp/budget.db database, so new transactions
are available the next time you open the desktop app.

Usage:
    python3 -m backend.sync_daemon              # Sync + backup
    python3 -m backend.sync_daemon --no-backup  # Sync only, skip Git backup
    python3 -m backend.sync_daemon --loop       # Run continuously (every 12 hours)

Git Backup Setup (one-time):
    cd ~/BudgetApp
    git init
    git remote add origin git@github.com:seanlewis08/budget-app-data.git
    echo "logs/" > .gitignore
    git add .gitignore budget.db
    git commit -m "Initial database backup"
    git branch -M main
    git push -u origin main
"""

import os
import sys
import time
import logging
import argparse
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

# Ensure project root is on the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from backend.database import SessionLocal, init_db
from backend.models import Account
from backend.services.plaid_service import PlaidService

# Paths
BUDGET_DIR = Path.home() / "BudgetApp"
DB_PATH = BUDGET_DIR / "budget.db"
LOG_DIR = BUDGET_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "sync.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

SYNC_INTERVAL_HOURS = 12


# ── Plaid Sync ──

def sync_all():
    """Sync all connected Plaid accounts once."""
    logger.info("Starting Plaid sync...")
    init_db()

    db = SessionLocal()
    plaid = PlaidService()
    results = {}

    try:
        accounts = (
            db.query(Account)
            .filter(Account.plaid_connection_status == "connected")
            .all()
        )

        if not accounts:
            logger.info("No connected accounts found.")
            return results

        logger.info(f"Syncing {len(accounts)} connected account(s)...")

        for account in accounts:
            try:
                result = plaid.sync_transactions(account, db)
                results[account.name] = result
                logger.info(
                    f"  {account.name}: +{result['added']} new, "
                    f"{result['modified']} updated, {result['removed']} removed"
                )
            except Exception as e:
                results[account.name] = {"error": str(e)}
                logger.error(f"  {account.name}: FAILED — {e}")

    except Exception as e:
        logger.error(f"Sync failed: {e}")
    finally:
        db.close()

    logger.info("Sync complete.")
    return results


# ── Git Backup ──

def backup_database():
    """
    Commit and push budget.db to a private Git repository.

    The Git repo must be initialized first (see module docstring).
    If the repo isn't set up yet, this logs a warning and skips gracefully.
    """
    if not DB_PATH.exists():
        logger.warning("Database not found, skipping backup.")
        return False

    git_dir = BUDGET_DIR / ".git"
    if not git_dir.exists():
        logger.warning(
            "Git backup not configured. To enable, run:\n"
            "  cd ~/BudgetApp && git init && "
            "git remote add origin git@github.com:YOUR_USER/budget-app-data.git"
        )
        return False

    try:
        # Get database size for the commit message
        db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)

        # Get a quick transaction count for context
        txn_count = _get_transaction_count()

        # Stage the database file
        _run_git("add", "budget.db")

        # Check if there are actual changes to commit
        status = _run_git("status", "--porcelain", "budget.db")
        if not status.strip():
            logger.info("No database changes to back up.")
            return True

        # Build a descriptive commit message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = (
            f"Backup {timestamp} — "
            f"{txn_count} transactions, "
            f"{db_size_mb:.1f} MB"
        )

        _run_git("commit", "-m", msg)
        logger.info(f"Git commit: {msg}")

        # Push if a remote is configured
        remote_check = _run_git("remote", "-v")
        if "origin" in remote_check:
            _run_git("push", "origin", "main")
            logger.info("Pushed to remote.")
        else:
            logger.info("No remote configured — local commit only.")

        return True

    except Exception as e:
        logger.error(f"Git backup failed: {e}")
        return False


def _run_git(*args) -> str:
    """Run a git command in the BudgetApp directory."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=str(BUDGET_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 and "nothing to commit" not in result.stdout:
        # Don't raise on "nothing to commit" — that's fine
        if "nothing to commit" not in result.stderr:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _get_transaction_count() -> int:
    """Quick count of transactions in the database."""
    try:
        db = SessionLocal()
        from backend.models import Transaction
        count = db.query(Transaction).count()
        db.close()
        return count
    except Exception:
        return 0


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="Budget App Plaid Sync Daemon")
    parser.add_argument(
        "--loop", action="store_true",
        help=f"Run continuously, syncing every {SYNC_INTERVAL_HOURS} hours",
    )
    parser.add_argument(
        "--interval", type=int, default=SYNC_INTERVAL_HOURS,
        help="Sync interval in hours (default: 12)",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Skip Git backup after sync",
    )
    args = parser.parse_args()

    if args.loop:
        interval = args.interval
        logger.info(f"Running in loop mode — syncing every {interval} hours")
        while True:
            sync_all()
            if not args.no_backup:
                backup_database()
            logger.info(f"Next sync in {interval} hours...")
            time.sleep(interval * 3600)
    else:
        sync_all()
        if not args.no_backup:
            backup_database()


if __name__ == "__main__":
    main()
