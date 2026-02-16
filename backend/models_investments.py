"""
SQLAlchemy models for the investments database (investments.db).
Separate from the main budget models to keep investment data isolated.
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from .investments_database import Base


class InvestmentAccount(Base):
    """An investment account linked via Plaid (e.g., Fidelity brokerage)."""
    __tablename__ = "investment_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plaid_item_id = Column(String(100), nullable=True, index=True)
    plaid_account_id = Column(String(100), nullable=True, unique=True)
    account_name = Column(String(200), nullable=False)
    account_type = Column(String(50), default="taxable")  # taxable, roth, traditional_ira, 401k, other
    institution_name = Column(String(200), nullable=True)

    # Sync metadata
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_error = Column(Text, nullable=True)
    connection_status = Column(String(20), default="connected")  # connected, disconnected, error

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    holdings = relationship("Holding", back_populates="account", cascade="all, delete-orphan")
    transactions = relationship("InvestmentTransaction", back_populates="account", cascade="all, delete-orphan")


class Security(Base):
    """A financial security (stock, ETF, mutual fund, crypto, etc.)."""
    __tablename__ = "securities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plaid_security_id = Column(String(100), nullable=True, unique=True, index=True)
    ticker = Column(String(20), nullable=True, index=True)  # Nullable: some mutual funds lack tickers
    name = Column(String(300), nullable=False)
    security_type = Column(String(50), nullable=False)  # stock, etf, mutual_fund, cryptocurrency, cash_equivalent, fixed_income, derivative
    sector = Column(String(100), nullable=True)
    isin = Column(String(20), nullable=True)

    # Price data
    close_price = Column(Float, nullable=True)
    close_price_as_of = Column(DateTime, nullable=True)
    price_source = Column(String(20), nullable=True)  # plaid, yfinance, manual

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    holdings = relationship("Holding", back_populates="security")
    transactions = relationship("InvestmentTransaction", back_populates="security")


class Holding(Base):
    """A position in a security within an investment account.

    Daily snapshots are stored (one row per account+security+date) to enable
    portfolio performance charting over time.
    """
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id"), nullable=False)

    quantity = Column(Float, nullable=False)
    cost_basis = Column(Float, nullable=True)  # Total cost basis (can be null for legacy/unknown)
    cost_basis_per_unit = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)  # quantity * close_price at snapshot time

    as_of_date = Column(Date, nullable=False)  # Date of this snapshot
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship("InvestmentAccount", back_populates="holdings")
    security = relationship("Security", back_populates="holdings")

    __table_args__ = (
        UniqueConstraint("investment_account_id", "security_id", "as_of_date", name="uq_holding_snapshot"),
        Index("ix_holding_account_date", "investment_account_id", "as_of_date"),
        Index("ix_holding_security", "security_id"),
    )


class InvestmentTransaction(Base):
    """A buy, sell, dividend, or other investment transaction."""
    __tablename__ = "investment_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id"), nullable=True)  # Null for cash transfers

    plaid_investment_transaction_id = Column(String(100), nullable=True, unique=True, index=True)

    date = Column(Date, nullable=False)
    type = Column(String(50), nullable=False)  # buy, sell, dividend, dividend_reinvestment, transfer, capital_gain, cash, fee
    quantity = Column(Float, nullable=True)  # Null for dividends paid as cash, transfers
    price = Column(Float, nullable=True)  # Price per unit at time of transaction
    amount = Column(Float, nullable=False)  # Total transaction value (positive = inflow, negative = outflow)
    fees = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship("InvestmentAccount", back_populates="transactions")
    security = relationship("Security", back_populates="transactions")

    __table_args__ = (
        Index("ix_inv_txn_account_date", "investment_account_id", "date"),
        Index("ix_inv_txn_security_date", "security_id", "date"),
    )
