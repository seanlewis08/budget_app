#!/usr/bin/env python3
"""
Import all historical archives into the budget database.

Run from project root:
    uv run python3 scripts/import_all_archives.py

Import order (oldest first, curated Excel only):
1. 2021 Budget 2021 Final.xlsx (WF + Discover, different taxonomy)
2. 2022 Budget 2022_Final.xlsx (multi-sheet: Discover, WF, CareCredit, BestBuy, AMEX)
3. 2023 Curated_Bills.xlsx (Discover only)
4. 2024 All_Bills.xlsx (all accounts, already has Short_Desc + Category_2)

2025–2026 data comes from Plaid (reconnect accounts with days_requested=730).
"""

import sys
import logging
from pathlib import Path

# Ensure project root on path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from backend.database import SessionLocal, init_db
from backend.models import Transaction, Account
from backend.services.archive_importer import import_archive_excel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

BUDGET_DIR = project_root / "Budget"


def main():
    init_db()
    db = SessionLocal()

    all_results = {}

    def safe_import_excel(label, path, **kwargs):
        """Import with error recovery — rollback on failure, continue."""
        if not path.exists():
            logger.warning(f"Not found: {path}")
            return
        logger.info("\n" + "=" * 60)
        logger.info(f"IMPORTING: {label}")
        logger.info("=" * 60)
        try:
            result = import_archive_excel(str(path), db, **kwargs)
            all_results[label] = result
        except Exception as e:
            logger.error(f"  FAILED: {label} — {e}")
            db.rollback()

    try:
        # ── 0. Clear existing transactions ──
        # One-time reset so archives + Plaid reconnect start from a clean slate.
        # Keeps accounts, categories, merchant mappings, and amount rules intact.
        existing_count = db.query(Transaction).count()
        if existing_count > 0:
            logger.info(f"Clearing {existing_count} existing transactions...")
            db.query(Transaction).delete()
            # Also reset Plaid cursors so reconnect does a full initial pull
            db.query(Account).update({Account.plaid_cursor: None})
            db.commit()
            logger.info("Transactions cleared. Plaid cursors reset.")

        # ── 1. 2021 ──
        safe_import_excel(
            "2021 Budget 2021 Final.xlsx",
            BUDGET_DIR / "Archive" / "2021" / "Budget 2021 Final.xlsx",
        )

        # ── 2. 2022 ──
        safe_import_excel(
            "2022 Budget 2022_Final.xlsx",
            BUDGET_DIR / "Archive" / "2022" / "Budget 2022_Final.xlsx",
        )

        # ── 3. 2023 Curated ──
        safe_import_excel(
            "2023 Curated_Bills.xlsx (Discover)",
            BUDGET_DIR / "Archive" / "2023" / "Curated_Bills.xlsx",
            default_account="discover",
        )

        # ── 4. 2024 All_Bills ──
        safe_import_excel(
            "2024 All_Bills.xlsx (all accounts)",
            BUDGET_DIR / "Archive" / "2024" / "All_Bills.xlsx",
        )

        # ── NOTE: 2025–2026 data comes from Plaid ──
        # Reconnect accounts in the app to pull up to 2 years via days_requested=730

        # ── Summary ──
        logger.info("\n" + "=" * 60)
        logger.info("IMPORT SUMMARY")
        logger.info("=" * 60)

        total_imported = 0
        total_dupes = 0
        total_uncat = 0
        total_errors = 0

        for name, result in all_results.items():
            imported = result.get("imported", 0)
            dupes = result.get("skipped_duplicates", 0)
            uncat = result.get("uncategorized", 0)
            errors = result.get("errors", 0)
            bal = result.get("skipped_balance", 0)
            total_imported += imported
            total_dupes += dupes
            total_uncat += uncat
            total_errors += errors
            logger.info(f"  {name}: {imported} imported, {dupes} dupes, {uncat} uncategorized, {errors} errors, {bal} balance skipped")

        logger.info(f"\n  TOTAL: {total_imported} transactions imported")
        logger.info(f"  TOTAL: {total_dupes} duplicates skipped")
        logger.info(f"  TOTAL: {total_uncat} uncategorized (pending review)")
        logger.info(f"  TOTAL: {total_errors} errors")

        # Show final DB state
        from sqlalchemy import func

        logger.info("\n" + "=" * 60)
        logger.info("DATABASE STATE")
        logger.info("=" * 60)
        for name, inst, mn, mx, cnt in (
            db.query(
                Account.name, Account.institution,
                func.min(Transaction.date), func.max(Transaction.date),
                func.count(Transaction.id),
            )
            .join(Transaction)
            .group_by(Account.id)
            .all()
        ):
            logger.info(f"  {name} ({inst}): {mn} to {mx} — {cnt} transactions")

        total = db.query(Transaction).count()
        logger.info(f"\n  Grand total: {total} transactions in database")

    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
