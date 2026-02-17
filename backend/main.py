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
from .routers import transactions, categories, budgets, import_csv, notifications, accounts, archive, investments, insights, settings
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
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])


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
    """Find the frontend/dist directory in the packaged app.

    Search order (packaged mode):
      1. PyInstaller _MEIPASS/frontend_dist  (bundled via spec datas=)
      2. PyInstaller _MEIPASS/frontend/dist
      3. Electron Resources/frontend/dist    (extraResources in package.json)
      4. Next to the executable               (fallback)
    """
    if getattr(sys, 'frozen', False):
        meipass = Path(sys._MEIPASS)
        exe_dir = Path(sys.executable).parent
        # On macOS: exe is in Contents/Resources/backend/budget-app-backend
        # So exe_dir.parent = Contents/Resources/
        resources_dir = exe_dir.parent

        candidates = [
            meipass / "frontend_dist",
            meipass / "frontend" / "dist",
            resources_dir / "frontend" / "dist",
            exe_dir / "frontend_dist",
            exe_dir / "frontend" / "dist",
            exe_dir.parent / "frontend" / "dist",
        ]

        for c in candidates:
            has_index = (c / "index.html").is_file() if c.is_dir() else False
            logger.info(f"Frontend search: {c} → dir={c.is_dir()}, index.html={has_index}")
            if c.is_dir() and has_index:
                logger.info(f"✓ Using frontend dir: {c}")
                return c

        # Log diagnostic info if nothing found
        logger.error(f"Frontend NOT FOUND in packaged mode!")
        logger.error(f"  sys._MEIPASS = {meipass}")
        logger.error(f"  sys.executable = {sys.executable}")
        logger.error(f"  exe_dir = {exe_dir}")
        logger.error(f"  resources_dir = {resources_dir}")
        if meipass.is_dir():
            logger.error(f"  _MEIPASS contents: {list(meipass.iterdir())}")
    else:
        # Development: frontend/dist relative to project root
        dev_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
        if dev_path.is_dir():
            return dev_path
    return None


# Only serve the SPA catch-all in production (packaged) mode.
# In development, Vite serves the frontend on its own port and proxies
# /api calls to this backend.  Registering a catch-all @app.get("/{path}")
# in dev mode causes Starlette to return 405 for POST/PUT/DELETE to any
# path that also matches the catch-all, breaking API endpoints.
_frontend_dir = _get_frontend_dir()
_is_packaged = getattr(sys, 'frozen', False)
if _frontend_dir and _frontend_dir.is_dir() and _is_packaged:
    # Mount static assets (JS, CSS, images)
    assets_dir = _frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    # Catch-all: serve index.html for any non-API route (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for any route not matched by API endpoints."""
        if full_path.startswith("api/") or full_path == "health":
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        file_path = _frontend_dir / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dir / "index.html"))
