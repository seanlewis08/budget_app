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
# Second call is a no-op for vars already set by the first.
load_dotenv(dotenv_path=Path.home() / "BudgetApp" / ".env")
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


# ── Serve React frontend in production (packaged app) ──
# When running as a PyInstaller bundle, serve the frontend static files
# so that relative /api calls work on the same origin.
def _get_frontend_dir() -> Path | None:
    """Find the frontend/dist directory in the packaged app."""
    if getattr(sys, 'frozen', False):
        # PyInstaller: look for frontend_dist next to the executable
        base = Path(sys._MEIPASS)
        candidates = [
            base / "frontend_dist",
            base / "frontend" / "dist",
        ]
        for c in candidates:
            if c.is_dir():
                return c
    else:
        # Development: frontend/dist relative to project root
        dev_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
        if dev_path.is_dir():
            return dev_path
    return None


_frontend_dir = _get_frontend_dir()
if _frontend_dir and _frontend_dir.is_dir():
    # Mount static assets (JS, CSS, images)
    assets_dir = _frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    # Catch-all: serve index.html for any non-API route (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for any route not matched by API endpoints."""
        file_path = _frontend_dir / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dir / "index.html"))
