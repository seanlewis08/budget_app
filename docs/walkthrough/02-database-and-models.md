# Part 2 — Database Models & Backend Core

In Part 1, we set up the project structure and got a minimal FastAPI server responding to health checks. Now we're going to build the real foundation — the database layer that stores everything: your accounts, transactions, categories, budgets, and application settings.

By the end of this part, you'll have a fully structured SQLite database with ten models, an automatic migration system, a seed data loader, and a complete FastAPI application that initializes everything on startup and registers all the API routes.

---

## 2.1 Why SQLite?

Before we write any code, let's talk about why we chose SQLite instead of something like PostgreSQL or MySQL.

Most database systems require you to install and run a separate server process. PostgreSQL, for instance, listens on port 5432 and requires configuration, authentication, and maintenance. For a personal finance app that runs on your own computer, that's unnecessary complexity.

SQLite stores your entire database in a single file — `~/BudgetApp/budget.db`. There's no server process. Python includes SQLite support out of the box. You can back up your data by copying one file. You can move it to a new computer by copying that same file. And for the access patterns of a personal finance app (one user, occasional writes, frequent reads), SQLite is plenty fast.

The tradeoff is that SQLite doesn't handle heavy concurrent writes well. But since our app has exactly one user and writes happen infrequently (when you sync transactions or confirm categories), this is never a problem in practice.

---

## 2.2 Database Setup (`backend/database.py`)

This module creates the database engine, configures SQLite-specific settings, and provides the session management that FastAPI uses for every request.

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

Let's walk through the important pieces.

**The database lives outside the project.** The path `~/BudgetApp/budget.db` means the database survives code updates, reinstalls, and even switching between the development version and the packaged desktop app. The `DB_DIR.mkdir(exist_ok=True)` line creates the directory automatically on first run.

**`check_same_thread=False`** is required because SQLite normally only allows the thread that created a connection to use it. FastAPI handles requests across multiple threads, so we need to disable this restriction. SQLAlchemy's connection pooling handles the safety.

**`timeout=30`** prevents "database is locked" errors. SQLite's default timeout is only 5 seconds, which isn't enough when the background sync scheduler is writing transactions at the same time you're browsing the UI. Bumping it to 30 seconds gives concurrent operations plenty of room.

**WAL mode** (Write-Ahead Logging) is the most important SQLite optimization for our use case. In the default journaling mode, a write blocks all reads. With WAL mode, readers can continue reading while a writer is active. This matters because our app has a background scheduler writing new transactions every few hours while the frontend continuously reads data for charts and tables. Without WAL mode, the UI would freeze during syncs.

**Foreign keys** are disabled by default in SQLite (for historical backwards-compatibility reasons). The `PRAGMA foreign_keys=ON` command enables them, so that deleting an account without first deleting its transactions produces an error instead of leaving orphaned records.

**`get_db()` is a generator function** — that `yield` keyword is the key. FastAPI's dependency injection system calls `next()` to get the session, passes it to your endpoint function, and then calls `next()` again after the response is sent, which triggers the `finally` block to close the session. This guarantees sessions are always cleaned up, even if your endpoint raises an exception.

---

## 2.3 The ORM Models (`backend/models.py`)

SQLAlchemy lets us define database tables as Python classes. Instead of writing raw SQL to create tables and query data, we work with objects. The ten models in our app break into four logical groups: taxonomy, financial data, categorization rules, and system tables.

### Imports and Base

```python
"""
SQLAlchemy models for the Budget App.
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .database import Base
```

Every model inherits from `Base`, which is the `declarative_base()` we created in `database.py`. When we call `Base.metadata.create_all()`, SQLAlchemy scans all classes that inherit from `Base` and creates their corresponding tables.

### Category — The Two-Level Taxonomy

The categorization system is at the heart of the app. Every transaction gets assigned to a subcategory, and every subcategory belongs to a parent category. For example, "Starbucks" → subcategory "Coffee" → parent category "Food". This two-level structure lets us show high-level spending breakdowns (how much on Food vs. Transportation?) while preserving detail (how much specifically on Coffee vs. Groceries?).

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

The hierarchy is created by the self-referential `parent_id` foreign key. Parent categories (Food, Housing, Transportation) have `parent_id=None`. Subcategories (Groceries, Rent, Gas Station) have `parent_id` pointing to their parent. The `relationship("Category", remote_side=[id], backref="children")` line tells SQLAlchemy how to navigate the hierarchy — `category.parent` goes up, `category.children` goes down.

Here's what the other columns do:

- **`short_desc`** is the internal identifier, like `"groceries"` or `"fast_food"`. It's unique and indexed for fast lookups. The categorization engine uses this to reference categories.
- **`display_name`** is what the user sees: `"Groceries"`, `"Fast Food"`. It can have spaces, mixed case, and special characters.
- **`color`** is a hex color code (like `"#FF6B6B"`) used in charts and pie graphs so each category has a consistent visual identity.
- **`is_income`** flags income categories so spending reports can exclude them. Without this flag, your paycheck would show up as "spending."
- **`is_recurring`** marks categories like rent, subscriptions, and utilities. The app uses this to build a recurring expenses monitor and to predict next month's fixed costs.

### Account — Bank Accounts

Each account represents one bank account — a checking account, savings account, or credit card. It can be connected to Plaid for automatic syncing, or used purely for CSV imports.

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

The Plaid-related columns deserve some explanation:

- **`plaid_access_token`** is the key that lets us pull data from the bank. It's encrypted using Fernet symmetric encryption before storage (covered in Part 3). Even if someone gets your database file, they can't access your bank without the encryption key.
- **`plaid_item_id`** identifies the Plaid "item" (a single bank login). One item can have multiple accounts — logging into SoFi once gives access to both Checking and Savings.
- **`plaid_cursor`** enables incremental syncing. Instead of re-downloading all transactions every time, we tell Plaid "give me everything since this cursor." Plaid returns only new/modified/removed transactions, and a new cursor for next time.
- **`plaid_connection_status`** tracks the state: `"disconnected"` (no Plaid connection), `"connected"` (working), or `"error"` (credentials expired or other issue).

The balance columns (`balance_current`, `balance_available`, `balance_limit`) are updated whenever we sync with Plaid. They let the UI show real-time account balances without an extra API call.

### Transaction — The Core Financial Record

This is the most important model in the app. Every dollar in, every dollar out — they're all Transaction rows.

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

There's a lot going on here, so let's break down the key design decisions.

**The sign convention** follows Plaid's standard: positive amounts are expenses (money leaving your account), negative amounts are income (money arriving). So a $50 grocery run is `50.0`, and a $3000 paycheck is `-3000.0`. This might feel backwards, but it means spending totals are always positive numbers — no confusing negatives in your charts.

**Two category columns** (`category_id` and `predicted_category_id`) separate the AI's guess from the user's decision. When a transaction comes in, the categorization engine writes its prediction to `predicted_category_id`. The user then reviews it in the Review Queue and can confirm or change it. Once confirmed, the value gets copied to `category_id`. This design means you can always see what the AI suggested versus what the user actually chose — useful for improving accuracy over time.

**The status lifecycle** tracks where a transaction is in the review process:
1. `"pending_review"` — just imported, needs human review
2. `"pending_save"` — user has staged a category choice but hasn't saved yet (batch workflow)
3. `"confirmed"` — user explicitly confirmed the category
4. `"auto_confirmed"` — the categorization engine was confident enough to auto-confirm (high-confidence merchant maps and amount rules)

**The source column** records where the transaction came from: `"csv_import"` for manual CSV uploads, `"plaid"` for automatic bank syncing, or `"archive"` for historical data imports.

**The categorization tier** tells you which part of the 3-tier engine matched: `"amount_rule"` (Tier 1, exact amount match), `"merchant_map"` (Tier 2, merchant name pattern), or `"ai"` (Tier 3, Claude AI fallback). This is valuable for debugging — if transactions are being miscategorized, you can see which tier is responsible.

**The prediction confidence** is a 0.0–1.0 score. Amount rules (exact matches) get 1.0. Merchant maps get a confidence level based on how many times they've been confirmed. AI predictions get 0.7. The app uses this score to decide whether to auto-confirm a prediction or send it to the review queue.

**The database indexes** are critical for performance. The `idx_transactions_date` index makes date-range queries fast (for monthly spending reports). The `idx_transactions_status` index speeds up the Review Queue (which queries for `status = 'pending_review'`). The compound `idx_transactions_account_date` index accelerates per-account date-range queries (for the Accounts page).

### DeletedTransaction — Soft Delete Audit Log

When you delete a transaction, we don't just remove it — we copy its key fields into a separate audit table first. This enables undo and provides an audit trail.

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
```

Notice that we store `account_name` and `category_name` as plain strings rather than foreign keys. This is intentional — if you delete an account and then look at the deletion history, those foreign keys would be broken. Storing the names directly means the audit log is always readable.

### MerchantMapping — Learned Merchant Patterns (Tier 2)

The categorization engine learns from your confirmations. When you confirm that "STARBUCKS #12345" is "Coffee," the system creates a merchant mapping so that all future Starbucks transactions are automatically categorized.

```python
class MerchantMapping(Base):
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
```

The `confidence` column counts how many times this mapping has been confirmed. Each time a user confirms a transaction matching this pattern, the confidence increases. When the confidence reaches a threshold (default: 3), future matches are auto-confirmed instead of going to the review queue. This means the system gradually learns to handle more transactions without human intervention.

The `merchant_pattern` is the normalized merchant name — uppercase, trimmed, with common bank-specific suffixes removed. The `UniqueConstraint` prevents duplicate patterns.

### AmountRule — Amount-Based Disambiguation (Tier 1)

Some merchants are ambiguous. "APPLE.COM/BILL" could be your Apple TV+ subscription ($5.29), your Spotify subscription via Apple ($11.99), or your HBO subscription via Apple ($15.89). The description is identical — only the amount differs.

Amount rules solve this by matching on both the description pattern AND the exact dollar amount:

```python
class AmountRule(Base):
    __tablename__ = "amount_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    description_pattern = Column(String(100), nullable=False)
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
```

The `tolerance` column allows for small price fluctuations (like tax adjustments). If you set `amount=15.89` with `tolerance=0.50`, it matches any amount between $15.39 and $16.39. This is checked before merchant mappings (Tier 2) and AI (Tier 3), so exact-amount rules always take priority.

### Budget — Monthly Spending Targets

```python
class Budget(Base):
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
```

Each budget row says "for this category, in this month, the spending limit is this amount." The month is stored as a string like `"2025-01"` rather than a date, because budgets are always monthly. The `UniqueConstraint` prevents accidentally creating two budgets for the same category in the same month.

### NotificationLog — Email Tracking

```python
class NotificationLog(Base):
    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    email_message_id = Column(String(200), nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    replied_at = Column(DateTime, nullable=True)
    reply_category = Column(String(100), nullable=True)

    transaction = relationship("Transaction", back_populates="notifications")
```

This tracks email notifications sent for transactions that need review. If you build out the email notification feature, this table prevents duplicate emails and records when/how the user responded.

### AppSetting — Key-Value Configuration Store

```python
class AppSetting(Base):
    """Key-value settings stored in the database (e.g. API keys, preferences).
    Values here override .env file values at runtime."""
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

This is a simple key-value store for application settings. The Settings page in the UI writes API keys (Plaid credentials, Anthropic API key) here instead of to a `.env` file. This is important for the packaged desktop app — users shouldn't need to find and edit a hidden `.env` file.

The `key` column is the primary key (no separate `id`), which makes lookups by key instantaneous. The `onupdate=datetime.utcnow` on `updated_at` automatically tracks when a setting was last changed.

### SyncLog — Sync Audit Trail

```python
class SyncLog(Base):
    """Log of every sync attempt — success or failure — for audit trail."""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    trigger = Column(String(20), nullable=False)    # "scheduled", "manual", "initial"
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

Every time the app syncs with Plaid — whether automatically via the scheduler, manually via the Sync button, or during the initial account connection — it records a log entry. This gives you visibility into what happened: how many transactions were added, modified, or removed, how long it took, and whether there were errors.

The `trigger` column tells you why the sync happened (`"scheduled"`, `"manual"`, or `"initial"`). The `status` tells you how it went (`"success"`, `"error"`, or `"partial"` for syncs that partially succeeded). The compound index on `(account_id, started_at)` makes it fast to query the sync history for a specific account in chronological order.

---

## 2.4 The Investments Database

Investment data lives in a completely separate database (`~/BudgetApp/investments.db`) with its own engine, session factory, and models. The setup is nearly identical to the main database:

```python
"""
Database setup for the investments SQLite database.
Separate from the main budget.db to isolate investment data.
Lives at ~/BudgetApp/investments.db.
"""

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DB_DIR = Path.home() / "BudgetApp"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "investments.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_investments_db():
    """FastAPI dependency that provides an investments database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_investments_db():
    """Create all investment tables if they don't exist."""
    from . import models_investments  # noqa: F401
    Base.metadata.create_all(bind=engine)
```

Why a separate database? The budgeting features (transactions, categories, budgets) and the investment tracking features (holdings, securities, prices) have completely different data patterns and access frequencies. Keeping them separate means you could use budgeting without investments or vice versa. It also keeps the main database smaller and faster — the investment database gets updated frequently during market hours with price data, and you don't want that write load touching the main database.

### Investment Models

The investments database has four models:

```python
class InvestmentAccount(Base):
    """An investment account linked via Plaid (e.g., Fidelity brokerage)."""
    __tablename__ = "investment_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plaid_item_id = Column(String(100), nullable=True, index=True)
    plaid_account_id = Column(String(100), nullable=True, unique=True)
    account_name = Column(String(200), nullable=False)
    account_type = Column(String(50), default="taxable")  # taxable, roth, traditional_ira, 401k
    institution_name = Column(String(200), nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_error = Column(Text, nullable=True)
    connection_status = Column(String(20), default="connected")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    holdings = relationship("Holding", back_populates="account", cascade="all, delete-orphan")
    transactions = relationship("InvestmentTransaction", back_populates="account",
                                cascade="all, delete-orphan")
```

**`InvestmentAccount`** is similar to the main `Account` model, but specific to brokerage/retirement accounts. The `cascade="all, delete-orphan"` on the relationships means deleting an investment account automatically deletes all its holdings and transactions — no orphaned records.

```python
class Security(Base):
    """A financial security (stock, ETF, mutual fund, crypto, etc.)."""
    __tablename__ = "securities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plaid_security_id = Column(String(100), nullable=True, unique=True, index=True)
    ticker = Column(String(20), nullable=True, index=True)
    name = Column(String(300), nullable=False)
    security_type = Column(String(50), nullable=False)  # stock, etf, mutual_fund, etc.
    sector = Column(String(100), nullable=True)
    isin = Column(String(20), nullable=True)
    close_price = Column(Float, nullable=True)
    close_price_as_of = Column(DateTime, nullable=True)
    price_source = Column(String(20), nullable=True)  # plaid, yfinance, manual
    created_at = Column(DateTime, default=datetime.utcnow)

    holdings = relationship("Holding", back_populates="security")
    transactions = relationship("InvestmentTransaction", back_populates="security")
```

**`Security`** represents a single financial instrument — Apple stock, a Vanguard ETF, a mutual fund. The `ticker` is nullable because some securities (like certain mutual funds) don't have standard ticker symbols. The `price_source` tracks where the latest price came from — Plaid (initial sync), yfinance (ongoing updates via Yahoo Finance), or manual (user-entered).

```python
class Holding(Base):
    """A position in a security within an investment account."""
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    cost_basis = Column(Float, nullable=True)
    cost_basis_per_unit = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)  # quantity * close_price at snapshot time
    as_of_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("InvestmentAccount", back_populates="holdings")
    security = relationship("Security", back_populates="holdings")

    __table_args__ = (
        UniqueConstraint("investment_account_id", "security_id", "as_of_date",
                         name="uq_holding_snapshot"),
        Index("ix_holding_account_date", "investment_account_id", "as_of_date"),
        Index("ix_holding_security", "security_id"),
    )
```

**`Holding`** tracks portfolio positions as daily snapshots — one row per account, per security, per date. The `UniqueConstraint` on `(account_id, security_id, as_of_date)` ensures exactly one snapshot per day. Storing snapshots over time (rather than just the current state) enables portfolio performance charts — you can see how your total value changed week by week or month by month.

```python
class InvestmentTransaction(Base):
    """A buy, sell, dividend, or other investment transaction."""
    __tablename__ = "investment_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id"), nullable=True)
    plaid_investment_transaction_id = Column(String(100), nullable=True, unique=True, index=True)
    date = Column(Date, nullable=False)
    type = Column(String(50), nullable=False)  # buy, sell, dividend, transfer, fee, etc.
    quantity = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    amount = Column(Float, nullable=False)
    fees = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("InvestmentAccount", back_populates="transactions")
    security = relationship("Security", back_populates="transactions")

    __table_args__ = (
        Index("ix_inv_txn_account_date", "investment_account_id", "date"),
        Index("ix_inv_txn_security_date", "security_id", "date"),
    )
```

**`InvestmentTransaction`** records individual buy/sell/dividend events. The `security_id` is nullable because some transactions (like cash transfers into the account) don't involve a specific security. The `plaid_investment_transaction_id` column enables deduplication when syncing — Plaid gives each transaction a unique ID, and the `unique=True` constraint prevents importing the same transaction twice.

---

## 2.5 Schema Migrations (`backend/migrations.py`)

Here's a common problem: you ship version 1.0 of your app. Users create their database and start importing transactions. Then in version 1.1, you need to add a new column to the `accounts` table. SQLAlchemy's `create_all()` will create tables that don't exist, but it won't add columns to tables that already exist. You need a migration system.

Full-featured tools like Alembic handle this by generating migration scripts that you track in version control. That's great for team projects, but overkill for a single-user desktop app. Instead, we use a lightweight approach: on every startup, check which columns exist and add any that are missing.

```python
"""
Lightweight database migrations for SQLite.
Runs on every startup — checks for missing columns and adds them.
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
        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 0.7 "
            "WHERE categorization_tier = 'ai' AND prediction_confidence IS NULL"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: backfilled {result.rowcount} AI predictions")

        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 1.0 "
            "WHERE categorization_tier = 'amount_rule' AND prediction_confidence IS NULL"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: backfilled {result.rowcount} amount rules")

        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 0.8 "
            "WHERE categorization_tier = 'merchant_map' AND prediction_confidence IS NULL"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: backfilled {result.rowcount} merchant maps")

        result = conn.execute(text(
            "UPDATE transactions SET prediction_confidence = 1.0 "
            "WHERE prediction_confidence > 1.0"
        ))
        if result.rowcount > 0:
            logger.info(f"Migration: capped {result.rowcount} oversized confidence values")

    logger.debug("Migrations complete")
```

The pattern is straightforward:

1. Use `inspect(engine)` to get the list of existing columns for each table
2. Compare against the columns that should exist
3. Use `ALTER TABLE ADD COLUMN` for any that are missing
4. Backfill any data that the new columns need

This is idempotent — running it twice does nothing the second time, because the columns already exist and the backfill queries only affect rows where the value is `NULL`. The `try/except` around each `ALTER TABLE` prevents the app from crashing if a migration partially completed before.

The backfill section is an important pattern. When we added the `prediction_confidence` column, existing transactions already had `categorization_tier` set but no confidence value. The migration sets appropriate defaults: 1.0 for amount rules (exact matches), 0.8 for merchant mappings, and 0.7 for AI predictions. It also caps any values over 1.0 (from an earlier bug where raw confirmation counts were accidentally stored as confidence).

---

## 2.6 Seed Data (`backend/services/seed_data.py`)

When the app runs for the first time, the database is empty — no categories, no accounts, nothing. The seed data function populates the initial taxonomy and default accounts:

```python
"""
Seed data for initial database setup.
Contains the full category taxonomy and account definitions.
"""

import logging
from ..database import SessionLocal
from ..models import Category, Account, AmountRule, MerchantMapping

logger = logging.getLogger(__name__)


def seed_categories_and_accounts():
    """Seed the database with categories, accounts, and initial merchant mappings."""
    db = SessionLocal()
    try:
        # Only seed if categories table is empty
        if db.query(Category).count() > 0:
            return

        logger.info("Seeding database with initial data...")

        # ── Parent Categories ──
        PARENT_CATEGORIES = {
            "Food": {"color": "#FF6B6B", "is_income": False},
            "Housing": {"color": "#4ECDC4", "is_income": False},
            "Transportation": {"color": "#45B7D1", "is_income": False},
            "Insurance": {"color": "#96CEB4", "is_income": False},
            "Utilities": {"color": "#FFEAA7", "is_income": False},
            "Medical": {"color": "#DDA0DD", "is_income": False},
            "Government": {"color": "#98D8C8", "is_income": False},
            "Savings": {"color": "#87CEEB", "is_income": False},
            "Personal_Spending": {"color": "#F7DC6F", "is_income": False},
            "Recreation_Entertainment": {"color": "#BB8FCE", "is_income": False},
            "Streaming_Services": {"color": "#E74C3C", "is_income": False},
            "Education": {"color": "#5DADE2", "is_income": False},
            "Travel": {"color": "#F1948A", "is_income": False},
            "Misc": {"color": "#AEB6BF", "is_income": False},
            "People": {"color": "#73C6B6", "is_income": False},
            "Payment_and_Interest": {"color": "#F0B27A", "is_income": False},
            "Income": {"color": "#58D68D", "is_income": True},
            "Balance": {"color": "#85C1E9", "is_income": False},
        }

        parent_map = {}
        for name, props in PARENT_CATEGORIES.items():
            cat = Category(
                short_desc=name.lower(),
                display_name=name.replace("_", " "),
                parent_id=None,
                color=props["color"],
                is_income=props["is_income"],
            )
            db.add(cat)
            db.flush()
            parent_map[name] = cat.id
```

The function is designed to be idempotent — the `if db.query(Category).count() > 0: return` check at the top means it only runs once. After the initial seed, subsequent startups skip it entirely.

The seeding creates four layers of data:

**Parent categories** (18 of them): Food, Housing, Transportation, Insurance, Utilities, Medical, Government, Savings, Personal Spending, Recreation & Entertainment, Streaming Services, Education, Travel, Misc, People, Payment & Interest, Income, and Balance. Each gets a hex color for charts and an `is_income` flag.

**Subcategories** (~75 of them): Each parent has multiple children. Food has Groceries, Fast Food, Restaurant, Coffee, Work Lunch, Food Delivery, Boba, and Bar. Streaming Services has Spotify, Netflix, Hulu, HBO, Apple TV, YouTube Premium, and Disney+. And so on. Each subcategory also has an `is_recurring` flag — rent, insurance, cell phone, and streaming subscriptions are all marked as recurring.

**Amount rules** (Tier 1 seeds): Pre-configured rules for ambiguous merchants like Apple billing (which handles multiple streaming subscriptions at different price points) and Venmo (which handles rent payments vs. personal transfers at different amounts).

**Merchant mappings** (Tier 2 seeds): Common merchant patterns pre-loaded with high confidence. Things like SAFEWAY → Groceries, STARBUCKS → Coffee, CHEVRON → Gas Station, PAYROLL → Payroll. These are seeded with `confidence=10`, well above the auto-confirm threshold of 3, so they work immediately without any user training.

You should customize these seeds for your own financial life. The category taxonomy, the accounts, the amount rules, and the merchant mappings should all reflect your actual banks, spending patterns, and preferences.

---

## 2.7 The Settings System

The Settings page (covered in detail in Part 5) lets users enter API keys through the UI instead of editing a `.env` file. But there's a subtle coordination problem: the Settings page writes to the `app_settings` database table, while services like PlaidService read from `os.getenv()`. If the user sets their Plaid API key in Settings and then restarts the app, the key is in the database but not in the environment — so Plaid stops working.

The fix lives in `backend/main.py`. A startup function reads all settings from the database and loads them into `os.environ`:

```python
def _load_db_settings_into_env():
    """
    Load all settings from the app_settings DB table into os.environ.

    The Settings page saves API keys to the database,
    but services like PlaidService read from os.getenv(). Without this step,
    credentials are lost on restart because they were never written to .env.
    """
    from .database import SessionLocal
    from .models import AppSetting
    from .routers.settings import SETTING_ENV_MAP

    db = SessionLocal()
    try:
        rows = db.query(AppSetting).all()
        loaded = []
        for row in rows:
            if row.value and row.key in SETTING_ENV_MAP:
                env_var = SETTING_ENV_MAP[row.key]
                os.environ[env_var] = row.value
                loaded.append(row.key)

        if loaded:
            logger.info(f"Loaded {len(loaded)} setting(s) from DB into env: {', '.join(loaded)}")
    except Exception as e:
        logger.warning(f"Could not load DB settings: {e}")
    finally:
        db.close()
```

The `SETTING_ENV_MAP` (defined in `backend/routers/settings.py`) maps database keys to environment variable names:

```python
SETTING_ENV_MAP = {
    "plaid_client_id": "PLAID_CLIENT_ID",
    "plaid_secret": "PLAID_SECRET",
    "plaid_production_secret": "PLAID_PRODUCTION_SECRET",
    "plaid_env": "PLAID_ENV",
    "plaid_recovery_code": "PLAID_RECOVERY_CODE",
    "plaid_token_encryption_key": "PLAID_TOKEN_ENCRYPTION_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "auto_confirm_threshold": "AUTO_CONFIRM_THRESHOLD",
}
```

This bridge function is critical for the packaged desktop app. Users configure everything through the Settings UI. On restart, this function restores those settings into the environment where all the services expect them.

---

## 2.8 The Full FastAPI Application (`backend/main.py`)

Now let's put everything together. The `main.py` file is the application's entry point — it wires together the database, migrations, seed data, background scheduler, frontend serving, and all the API routes.

```python
"""
Budget App — FastAPI Backend
Main entry point. Registers all routers and initializes the database.
"""

import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from ~/BudgetApp/.env first (works when running as packaged app),
# then fall back to CWD/.env (works during development).
load_dotenv(dotenv_path=Path.home() / "BudgetApp" / ".env")
load_dotenv()
```

The double `load_dotenv()` call is deliberate. The first loads `~/BudgetApp/.env`, which is the right location when the app is installed and running from `/Applications/` or `Program Files/`. The second loads `.env` from the current working directory, which works during development when you're running from the project root. The second call is a no-op for any variables already set by the first — so there's no conflict.

### The Startup Sequence

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run on startup: create tables, migrate, seed data, start sync scheduler."""
    init_db()
    init_investments_db()
    run_migrations()
    _load_db_settings_into_env()
    seed_categories_and_accounts()
    start_scheduler()
    yield
    stop_scheduler()
```

FastAPI's `lifespan` context manager runs code when the server starts (before `yield`) and when it shuts down (after `yield`). The startup sequence runs in this exact order for a reason:

1. **`init_db()`** — Creates all main database tables if they don't exist. On a fresh install, this creates the entire schema. On subsequent startups, it's a no-op.
2. **`init_investments_db()`** — Same thing for the investments database.
3. **`run_migrations()`** — Adds any new columns that weren't in the original schema. Must run after `init_db()` because it needs the tables to exist.
4. **`_load_db_settings_into_env()`** — Loads API keys from the `app_settings` table into `os.environ`. Must run after `run_migrations()` because the `app_settings` table might be new.
5. **`seed_categories_and_accounts()`** — Populates the initial taxonomy and accounts if the database is empty. Must run after `init_db()` and `run_migrations()` so all tables and columns exist.
6. **`start_scheduler()`** — Starts the background job scheduler for automatic syncing. Must run last because it needs Plaid credentials (loaded in step 4) and accounts (created in step 5).

On shutdown, `stop_scheduler()` gracefully stops background jobs so they don't continue running after the server exits.

### Registering Routes

```python
app = FastAPI(
    title="Budget App",
    description="Personal finance tracker with AI-powered categorization",
    version="0.1.0",
    lifespan=lifespan,
)

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
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
```

Each router is a separate Python file in `backend/routers/` that defines a set of related endpoints. The `prefix` determines the URL path, and the `tags` group endpoints in FastAPI's auto-generated documentation at `/docs`. We'll build each of these routers in subsequent parts.

### Core Endpoints

```python
@app.get("/health")
def health_check():
    """Health check endpoint used by Electron to verify backend is ready."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/stats")
def get_stats():
    """Quick stats for the dashboard header."""
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

The `/health` endpoint is used by Electron to know when the backend is ready (it polls this during startup). The `/api/stats` endpoint provides counts for the dashboard header badges — total transactions, how many need review, how many are staged, and how many are confirmed.

### Serving the Frontend in Production

The final piece of `main.py` handles serving the React frontend in production mode. During development, Vite serves the frontend on port 5173 and proxies API calls to the backend. But in the packaged desktop app, there's no Vite server — the backend needs to serve the built React files directly.

```python
def _get_frontend_dir() -> Path | None:
    """Locate the React frontend build directory."""
    is_frozen = getattr(sys, 'frozen', False)

    # Priority 1: env var set by Electron
    env_dir = os.environ.get("BUDGET_APP_FRONTEND_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir() and (p / "index.html").is_file():
            return p

    # Priority 2: search relative to binary (frozen mode)
    if is_frozen:
        exe = Path(sys.executable)
        candidates = [
            exe.parent.parent / "frontend" / "dist",
            exe.parent / "frontend" / "dist",
        ]
        for c in candidates:
            if c.is_dir() and (c / "index.html").is_file():
                return c
        return None

    # Development: frontend/dist next to project root
    dev_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dev_path.is_dir():
        return dev_path
    return None


def _setup_frontend_serving(app: FastAPI) -> None:
    """Mount the React SPA on the FastAPI app (production only)."""
    is_packaged = getattr(sys, 'frozen', False)
    frontend_dir = _get_frontend_dir()

    if not frontend_dir or not is_packaged:
        return

    # Mount /assets for JS, CSS, images
    assets_dir = frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)),
                  name="static-assets")

    # Catch-all: serve index.html for any non-API GET route (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        file_path = frontend_dir / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))


_setup_frontend_serving(app)
```

This is only active in the packaged (PyInstaller) build. The function mounts the compiled React assets as static files and registers a catch-all route that serves `index.html` for any URL that isn't an API endpoint. This is necessary because React Router handles client-side navigation — when the user navigates to `/spending`, the browser requests that path from the server, and the server needs to return `index.html` so React can render the correct page.

The `_get_frontend_dir()` function searches multiple locations for the built frontend files, prioritizing the Electron-provided environment variable, then searching relative to the binary. This flexibility means the frontend discovery works whether you're running in development, in a PyInstaller bundle, or in an Electron shell.

---

## 2.9 Testing the Database Layer

At this point, you can verify everything works:

```bash
# Start the backend
uv run uvicorn backend.main:app --port 8000 --reload

# In another terminal, check the health endpoint
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0"}

# Check that stats work (should be all zeros on a fresh database)
curl http://localhost:8000/api/stats
# → {"total_transactions":0,"pending_review":0,"pending_save":0,"confirmed":0}

# Check that categories were seeded
curl http://localhost:8000/api/categories
# → [{"id":1,"short_desc":"food","display_name":"Food",...}, ...]
```

You can also open `http://localhost:8000/docs` in your browser to see the auto-generated API documentation. FastAPI builds this from your endpoint definitions and Pydantic models — it's an interactive reference where you can try out each endpoint directly.

If you look in `~/BudgetApp/`, you should see two database files:

```bash
ls -la ~/BudgetApp/
# budget.db        — Main database (transactions, accounts, categories, budgets)
# investments.db   — Investment portfolio database
```

---

## What's Next

With the database fully defined and the FastAPI application wired up, we have a solid foundation. Part 3 dives into Plaid integration — how to connect real bank accounts, encrypt access tokens, sync transactions automatically, and handle the various states and errors that come with live bank connections.

→ [Part 3: Plaid Integration & Account Management](03-plaid-integration.md)
