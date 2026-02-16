# Part 2 — Database Models & Backend Core

This part builds the SQLite database layer, defines all ORM models, creates the migration system, and wires up the FastAPI application skeleton with lifespan management.

---

## 2.1 Database Setup (`backend/database.py`)

The database lives at `~/BudgetApp/budget.db` — outside the project directory so it survives code updates and reinstalls. We use SQLAlchemy 2.0 with SQLite.

```python
"""
Database setup and session management for SQLite.
The database file lives at ~/BudgetApp/budget.db by default,
persisting across app updates.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# Database location: ~/BudgetApp/budget.db
DB_DIR = Path.home() / "BudgetApp"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "budget.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,  # Required for SQLite + FastAPI
        "timeout": 30,  # Wait up to 30s for locks (default is 5s)
    },
    echo=False,
)


# Enable WAL mode and foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist."""
    from . import models  # noqa: F401 — import to register models
    Base.metadata.create_all(bind=engine)
```

Key design decisions:

- **WAL mode** (`PRAGMA journal_mode=WAL`): Allows concurrent reads during writes. Essential when the background sync scheduler writes transactions while the frontend reads them.
- **Foreign keys** (`PRAGMA foreign_keys=ON`): SQLite has foreign keys disabled by default. This pragma enforces referential integrity.
- **`check_same_thread=False`**: SQLite normally restricts connections to the thread that created them. FastAPI uses multiple threads, so this flag is required.
- **30-second timeout**: Prevents `database is locked` errors when multiple processes (app + sync daemon) access the same file.
- **`get_db()` as a generator**: This pattern lets FastAPI's dependency injection system automatically close the session after each request.

---

## 2.2 ORM Models (`backend/models.py`)

The app has eight models organized into three logical groups: taxonomy, financial data, and system tables.

### Category

Two-level taxonomy: parent categories (e.g., "Food") contain child subcategories (e.g., "Groceries", "Fast Food", "Restaurant"). The self-referential `parent_id` foreign key creates the hierarchy.

```python
class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    short_desc = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    color = Column(String(7), nullable=True)  # hex color for charts
    is_income = Column(Boolean, default=False)
    is_recurring = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("Category", remote_side=[id], backref="children")
    transactions = relationship("Transaction", back_populates="category",
                                foreign_keys="Transaction.category_id")
    budgets = relationship("Budget", back_populates="category")
    merchant_mappings = relationship("MerchantMapping", back_populates="category")
```

- `short_desc` is the internal key (e.g., `"groceries"`, `"fast_food"`) — unique, used for lookups
- `display_name` is the user-facing label (e.g., `"Groceries"`, `"Fast Food"`)
- `color` stores a hex color code for chart rendering
- `is_income` flags income categories so spending reports can exclude them
- `is_recurring` marks categories like rent, subscriptions, and utilities for the recurring monitor

### Account

Represents a bank account. Each account can be connected to Plaid for automatic transaction syncing, or used as a target for CSV imports.

```python
class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    institution = Column(String(50), nullable=False)      # "discover", "sofi", "wellsfargo"
    account_type = Column(String(20), nullable=False)      # "checking", "savings", "credit"
    plaid_item_id = Column(String(100), nullable=True)
    plaid_access_token = Column(Text, nullable=True)       # encrypted with Fernet
    plaid_cursor = Column(Text, nullable=True)
    plaid_account_id = Column(String(100), nullable=True)
    plaid_connection_status = Column(String(20), default="disconnected", nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_error = Column(Text, nullable=True)
    balance_current = Column(Float, nullable=True)
    balance_available = Column(Float, nullable=True)
    balance_limit = Column(Float, nullable=True)           # credit limit
    balance_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="account")
```

- `plaid_access_token` is encrypted at rest using Fernet symmetric encryption (covered in Part 3)
- `plaid_cursor` stores the Plaid transaction sync cursor for incremental updates
- `plaid_connection_status` tracks the state: `"disconnected"`, `"connected"`, or `"error"`

### Transaction

The core financial record. Every transaction belongs to an account and optionally has a confirmed category and/or a predicted category.

```python
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    plaid_transaction_id = Column(String(100), nullable=True, unique=True)
    date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)          # Raw from bank
    merchant_name = Column(String(200), nullable=True)  # Cleaned
    amount = Column(Float, nullable=False)              # Positive = expense, negative = income
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    predicted_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    status = Column(String(20), default="pending_review", nullable=False)
    source = Column(String(20), default="csv_import", nullable=False)
    is_pending = Column(Boolean, default=False)
    categorization_tier = Column(String(20), nullable=True)
    prediction_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_transactions_date", "date"),
        Index("idx_transactions_status", "status"),
        Index("idx_transactions_account_date", "account_id", "date"),
    )

    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", foreign_keys=[category_id])
    predicted_category = relationship("Category", foreign_keys=[predicted_category_id])
    notifications = relationship("NotificationLog", back_populates="transaction")
```

Important columns:

- **`amount`**: Sign convention is positive = expense, negative = income (Plaid's convention)
- **`category_id`** vs **`predicted_category_id`**: The categorization engine writes to `predicted_category_id`. When the user confirms (or it's auto-confirmed), the value is copied to `category_id`.
- **`status`**: Lifecycle is `"pending_review"` → `"pending_save"` (staged) → `"confirmed"` or `"auto_confirmed"`
- **`source`**: Either `"csv_import"`, `"plaid"`, or `"archive"`
- **`categorization_tier`**: Records which tier matched: `"amount_rule"`, `"merchant_map"`, or `"ai"`
- **`prediction_confidence`**: 0.0–1.0 score. Amount rules get 1.0, merchant maps get their confidence level, AI gets 0.7.

### Supporting Models

```python
class DeletedTransaction(Base):
    """Audit log of deleted transactions — enables undo."""
    __tablename__ = "deleted_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    original_id = Column(Integer, nullable=False)
    account_id = Column(Integer, nullable=True)
    account_name = Column(String(200), nullable=True)
    date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    merchant_name = Column(String(200), nullable=True)
    amount = Column(Float, nullable=False)
    category_name = Column(String(100), nullable=True)
    status = Column(String(20), nullable=True)
    source = Column(String(20), nullable=True)
    deleted_at = Column(DateTime, default=datetime.utcnow)


class MerchantMapping(Base):
    """Tier 2 categorization: learned merchant → category patterns."""
    __tablename__ = "merchant_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_pattern = Column(String(200), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    confidence = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("merchant_pattern", name="uq_merchant_pattern"),
    )

    category = relationship("Category", back_populates="merchant_mappings")


class AmountRule(Base):
    """Tier 1 categorization: amount-based disambiguation for ambiguous merchants."""
    __tablename__ = "amount_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    description_pattern = Column(String(100), nullable=False)  # e.g., "apple", "venmo"
    amount = Column(Float, nullable=False)
    tolerance = Column(Float, default=0.01)
    short_desc = Column(String(100), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_amount_rules_pattern", "description_pattern"),
    )

    category = relationship("Category")


class Budget(Base):
    """Monthly budget targets per category."""
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    month = Column(String(7), nullable=False)  # "2025-01"
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("category_id", "month", name="uq_budget_category_month"),
    )

    category = relationship("Category", back_populates="budgets")


class NotificationLog(Base):
    """Email notification tracking."""
    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    email_message_id = Column(String(200), nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    replied_at = Column(DateTime, nullable=True)
    reply_category = Column(String(100), nullable=True)

    transaction = relationship("Transaction", back_populates="notifications")


class SyncLog(Base):
    """Log of every sync attempt for audit trail."""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    trigger = Column(String(20), nullable=False)    # "scheduled", "manual", "retry"
    status = Column(String(20), nullable=False)     # "success", "error", "partial"
    added = Column(Integer, default=0)
    modified = Column(Integer, default=0)
    removed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_synclog_account_started", "account_id", "started_at"),
    )

    account = relationship("Account")
```

---

## 2.3 Schema Migrations (`backend/migrations.py`)

Since we use SQLite (no Alembic), we handle schema changes with a lightweight migration function that inspects existing columns and adds missing ones:

```python
"""
Lightweight SQLite schema migrations.
Runs on every startup — checks for missing columns and adds them.
"""

import logging
from sqlalchemy import inspect, text
from .database import engine, SessionLocal

logger = logging.getLogger(__name__)


def run_migrations():
    """Add any missing columns to existing tables."""
    inspector = inspect(engine)

    # Accounts table migrations
    account_columns = {col["name"] for col in inspector.get_columns("accounts")}
    migrations = {
        "plaid_account_id": "VARCHAR(100)",
        "plaid_connection_status": "VARCHAR(20) DEFAULT 'disconnected'",
        "last_synced_at": "DATETIME",
        "last_sync_error": "TEXT",
        "balance_current": "REAL",
        "balance_available": "REAL",
        "balance_limit": "REAL",
        "balance_updated_at": "DATETIME",
    }

    with engine.connect() as conn:
        for col_name, col_type in migrations.items():
            if col_name not in account_columns:
                conn.execute(text(
                    f"ALTER TABLE accounts ADD COLUMN {col_name} {col_type}"
                ))
                logger.info(f"Added column accounts.{col_name}")
        conn.commit()

    # Transactions table migrations
    txn_columns = {col["name"] for col in inspector.get_columns("transactions")}
    if "prediction_confidence" not in txn_columns:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE transactions ADD COLUMN prediction_confidence REAL"
            ))
            conn.commit()
            logger.info("Added column transactions.prediction_confidence")

        # Backfill confidence values based on categorization tier
        db = SessionLocal()
        try:
            db.execute(text(
                "UPDATE transactions SET prediction_confidence = 0.7 "
                "WHERE categorization_tier = 'ai' AND prediction_confidence IS NULL"
            ))
            db.execute(text(
                "UPDATE transactions SET prediction_confidence = 1.0 "
                "WHERE categorization_tier = 'amount_rule' AND prediction_confidence IS NULL"
            ))
            db.execute(text(
                "UPDATE transactions SET prediction_confidence = 0.8 "
                "WHERE categorization_tier = 'merchant_map' AND prediction_confidence IS NULL"
            ))
            db.execute(text(
                "UPDATE transactions SET prediction_confidence = 1.0 "
                "WHERE prediction_confidence > 1.0"
            ))
            db.commit()
            logger.info("Backfilled prediction_confidence values")
        finally:
            db.close()
```

This approach:

- Runs automatically on every startup (idempotent — checks before adding)
- No migration files to track or apply manually
- Works well for a single-developer app where you control the schema

---

## 2.4 FastAPI Application (`backend/main.py`)

The full application wires together the database, migrations, seed data, background scheduler, and all API routers:

```python
"""
Budget App — FastAPI Backend
Main entry point. Registers all routers and initializes the database.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from .database import init_db
from .investments_database import init_investments_db
from .migrations import run_migrations
from .routers import transactions, categories, budgets, import_csv, notifications, accounts, archive, investments, insights
from .services.seed_data import seed_categories_and_accounts
from .services.sync_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run on startup: create tables, migrate, seed data, start sync scheduler."""
    init_db()
    init_investments_db()
    run_migrations()
    seed_categories_and_accounts()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Budget App",
    description="Personal finance tracker with AI-powered categorization",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Electron renderer (React) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(transactions.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(categories.router, prefix="/api/categories", tags=["Categories"])
app.include_router(budgets.router, prefix="/api/budgets", tags=["Budgets"])
app.include_router(import_csv.router, prefix="/api/import", tags=["CSV Import"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["Accounts"])
app.include_router(archive.router, prefix="/api/archive", tags=["Archive Import"])
app.include_router(investments.router, prefix="/api/investments", tags=["Investments"])
app.include_router(insights.router, prefix="/api/insights", tags=["Financial Insights"])


@app.get("/health")
def health_check():
    """Health check endpoint used by Electron to verify backend is ready."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/stats")
def get_stats():
    """Quick stats for the sidebar badge."""
    from .database import SessionLocal
    from .models import Transaction

    db = SessionLocal()
    try:
        total = db.query(Transaction).count()
        pending = db.query(Transaction).filter(
            Transaction.status == "pending_review"
        ).count()
        pending_save = db.query(Transaction).filter(
            Transaction.status == "pending_save"
        ).count()
        confirmed = db.query(Transaction).filter(
            Transaction.status.in_(["confirmed", "auto_confirmed"])
        ).count()
        return {
            "total_transactions": total,
            "pending_review": pending,
            "pending_save": pending_save,
            "confirmed": confirmed,
        }
    finally:
        db.close()
```

The startup sequence is:

1. `init_db()` — creates all main database tables if they don't exist
2. `init_investments_db()` — creates investment database tables
3. `run_migrations()` — adds any missing columns to existing tables
4. `seed_categories_and_accounts()` — inserts default categories, accounts, merchant mappings, and amount rules (idempotent)
5. `start_scheduler()` — starts APScheduler background jobs for automatic syncing and price fetching

On shutdown, `stop_scheduler()` gracefully stops background jobs.

---

## What's Next

With the database layer and FastAPI skeleton in place, Part 3 covers Plaid integration: connecting bank accounts, encrypting access tokens, and syncing transactions automatically.

→ [Part 3: Plaid Integration & Account Management](03-plaid-integration.md)
