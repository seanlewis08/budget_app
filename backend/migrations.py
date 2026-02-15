"""
Lightweight database migrations for SQLite.

SQLAlchemy's create_all() only creates missing tables, not missing columns.
This module adds any new columns that don't exist yet, so the app can
evolve without requiring users to delete their database.
"""

import logging
from sqlalchemy import text, inspect
from .database import engine

logger = logging.getLogger(__name__)


def run_migrations():
    """Check for and apply any pending column additions."""
    inspector = inspect(engine)

    # Get existing columns for accounts table
    if "accounts" in inspector.get_table_names():
        existing_cols = {col["name"] for col in inspector.get_columns("accounts")}

        new_columns = [
            ("plaid_account_id", "VARCHAR(100)"),
            ("plaid_connection_status", "VARCHAR(20) NOT NULL DEFAULT 'disconnected'"),
            ("last_synced_at", "DATETIME"),
            ("last_sync_error", "TEXT"),
            ("balance_current", "FLOAT"),
            ("balance_available", "FLOAT"),
            ("balance_limit", "FLOAT"),
            ("balance_updated_at", "DATETIME"),
        ]

        with engine.begin() as conn:
            for col_name, col_type in new_columns:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(
                            f"ALTER TABLE accounts ADD COLUMN {col_name} {col_type}"
                        ))
                        logger.info(f"Migration: added accounts.{col_name}")
                    except Exception as e:
                        logger.warning(f"Migration skip: accounts.{col_name} — {e}")

    # --- Transactions table migrations ---
    if "transactions" in inspector.get_table_names():
        txn_cols = {col["name"] for col in inspector.get_columns("transactions")}

        txn_new_columns = [
            ("prediction_confidence", "REAL"),
        ]

        with engine.begin() as conn:
            for col_name, col_type in txn_new_columns:
                if col_name not in txn_cols:
                    try:
                        conn.execute(text(
                            f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}"
                        ))
                        logger.info(f"Migration: added transactions.{col_name}")
                    except Exception as e:
                        logger.warning(f"Migration skip: transactions.{col_name} — {e}")

    # --- Backfill prediction_confidence for existing categorized transactions ---
    with engine.begin() as conn:
        # AI tier always returns 0.7 confidence
        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 0.7 "
            "WHERE categorization_tier = 'ai' AND prediction_confidence IS NULL"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: backfilled prediction_confidence for {result.rowcount} AI-categorized transactions")

        # Amount rules are exact matches → 1.0 confidence
        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 1.0 "
            "WHERE categorization_tier = 'amount_rule' AND prediction_confidence IS NULL"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: backfilled prediction_confidence for {result.rowcount} amount-rule transactions")

        # Merchant mappings — set 0.8 as reasonable default for existing
        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 0.8 "
            "WHERE categorization_tier = 'merchant_map' AND prediction_confidence IS NULL"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: backfilled prediction_confidence for {result.rowcount} merchant-map transactions")

        # Fix any merchant_map confidence values > 1.0 (stored as raw integer counts)
        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 1.0 "
            "WHERE prediction_confidence > 1.0"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: capped {result.rowcount} oversized prediction_confidence values to 1.0")

    logger.debug("Migrations complete")
