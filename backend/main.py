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
from .migrations import run_migrations
from .routers import transactions, categories, budgets, import_csv, notifications, accounts, archive
from .services.seed_data import seed_categories_and_accounts
from .services.sync_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run on startup: create tables, migrate, seed data, start sync scheduler."""
    init_db()
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
        pending = db.query(Transaction).filter(Transaction.status == "pending_review").count()
        pending_save = db.query(Transaction).filter(Transaction.status == "pending_save").count()
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
