"""
SQLAlchemy models for the Budget App.

Tables:
- categories: Two-level taxonomy (parent Category_2 → child Short_Desc)
- accounts: Bank accounts (Discover, SoFi Checking, SoFi Savings, Wells Fargo)
- transactions: All financial transactions
- merchant_mappings: Learned merchant → category patterns (Tier 2)
- amount_rules: Amount-based disambiguation (Tier 1, e.g. Apple/Venmo)
- budgets: Monthly budget targets per category
- notification_log: Email notification tracking
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .database import Base


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

    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    transactions = relationship("Transaction", back_populates="category", foreign_keys="Transaction.category_id")
    budgets = relationship("Budget", back_populates="category")
    merchant_mappings = relationship("MerchantMapping", back_populates="category")

    def __repr__(self):
        return f"<Category {self.short_desc} ({self.display_name})>"


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    institution = Column(String(50), nullable=False)  # "discover", "sofi", "wellsfargo"
    account_type = Column(String(20), nullable=False)  # "checking", "savings", "credit"
    plaid_item_id = Column(String(100), nullable=True)
    plaid_access_token = Column(Text, nullable=True)  # encrypted with Fernet
    plaid_cursor = Column(Text, nullable=True)
    plaid_account_id = Column(String(100), nullable=True)  # Plaid's account ID
    plaid_connection_status = Column(String(20), default="disconnected", nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_error = Column(Text, nullable=True)
    balance_current = Column(Float, nullable=True)
    balance_available = Column(Float, nullable=True)
    balance_limit = Column(Float, nullable=True)  # credit limit
    balance_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    transactions = relationship("Transaction", back_populates="account")

    def __repr__(self):
        return f"<Account {self.name} ({self.institution})>"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    plaid_transaction_id = Column(String(100), nullable=True, unique=True)
    date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)  # Raw from bank
    merchant_name = Column(String(200), nullable=True)  # Cleaned
    amount = Column(Float, nullable=False)  # Positive = expense, negative = income
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    predicted_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    status = Column(String(20), default="pending_review", nullable=False)
    source = Column(String(20), default="csv_import", nullable=False)
    is_pending = Column(Boolean, default=False)
    categorization_tier = Column(String(20), nullable=True)  # "amount_rule", "merchant_map", "ai"
    prediction_confidence = Column(Float, nullable=True)  # 0.0–1.0, set by categorize_transaction()
    created_at = Column(DateTime, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_transactions_date", "date"),
        Index("idx_transactions_status", "status"),
        Index("idx_transactions_account_date", "account_id", "date"),
    )

    # Relationships
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", foreign_keys=[category_id])
    predicted_category = relationship("Category", foreign_keys=[predicted_category_id])
    notifications = relationship("NotificationLog", back_populates="transaction")

    def __repr__(self):
        return f"<Transaction {self.date} {self.description[:30]} ${self.amount}>"


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

    # Relationships
    category = relationship("Category", back_populates="merchant_mappings")

    def __repr__(self):
        return f"<MerchantMapping {self.merchant_pattern} → {self.category_id} (conf={self.confidence})>"


class AmountRule(Base):
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

    # Relationships
    category = relationship("Category")

    def __repr__(self):
        return f"<AmountRule {self.description_pattern} ${self.amount} → {self.short_desc}>"


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

    # Relationships
    category = relationship("Category", back_populates="budgets")

    def __repr__(self):
        return f"<Budget {self.month} {self.category_id} ${self.amount}>"


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    email_message_id = Column(String(200), nullable=True)  # Gmail message ID
    sent_at = Column(DateTime, default=datetime.utcnow)
    replied_at = Column(DateTime, nullable=True)
    reply_category = Column(String(100), nullable=True)

    # Relationships
    transaction = relationship("Transaction", back_populates="notifications")

    def __repr__(self):
        return f"<NotificationLog txn={self.transaction_id} sent={self.sent_at}>"
