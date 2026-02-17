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
#
# In production, Electron ships the built React app as an extraResource
# and passes its location via BUDGET_APP_FRONTEND_DIR.  The backend
# mounts it as static files and registers a catch-all to support SPA
# routing (all non-API GET requests → index.html).
#
# In development, Vite serves the frontend on :5173 and proxies /api
# to this backend, so we do NOT register the catch-all (it would cause
# 405 errors for POST/PUT/DELETE).

def _get_frontend_dir() -> Path | None:
    """Locate the React frontend build directory.

    Production: Electron sets BUDGET_APP_FRONTEND_DIR pointing to the
    extraResources copy of frontend/dist.  Fallback searches common
    paths relative to the PyInstaller binary.

    Development: looks for frontend/dist relative to the project root.
    """
    is_frozen = getattr(sys, 'frozen', False)

    # Print diagnostics — these go to stdout which Electron captures
    # as [backend] lines, making them visible for debugging.
    print(f"[frontend-discovery] frozen={is_frozen}", flush=True)

    # ── Priority 1: env var set by Electron (most reliable) ──
    env_dir = os.environ.get("BUDGET_APP_FRONTEND_DIR")
    if env_dir:
        p = Path(env_dir)
        has_index = p.is_dir() and (p / "index.html").is_file()
        print(f"[frontend-discovery] BUDGET_APP_FRONTEND_DIR={env_dir}  "
              f"is_dir={p.is_dir()}  has_index={has_index}", flush=True)
        if has_index:
            return p

    # ── Priority 2: search relative to the binary (frozen mode) ──
    if is_frozen:
        exe = Path(sys.executable)
        exe_dir = exe.parent              # e.g. .app/Contents/Resources/backend/
        resources_dir = exe_dir.parent    # e.g. .app/Contents/Resources/

        candidates = [
            resources_dir / "frontend" / "dist",
            exe_dir.parent / "frontend" / "dist",
            exe_dir / "frontend" / "dist",
        ]

        for c in candidates:
            has_index = c.is_dir() and (c / "index.html").is_file()
            print(f"[frontend-discovery] checking {c}  "
                  f"is_dir={c.is_dir()}  has_index={has_index}", flush=True)
            if has_index:
                return c

        # Nothing found — dump diagnostics
        print(f"[frontend-discovery] FAILED — frontend not found!", flush=True)
        print(f"[frontend-discovery]   executable = {exe}", flush=True)
        print(f"[frontend-discovery]   exe_dir    = {exe_dir}", flush=True)
        print(f"[frontend-discovery]   resources  = {resources_dir}", flush=True)
        try:
            print(f"[frontend-discovery]   resources contents = "
                  f"{list(resources_dir.iterdir())}", flush=True)
        except Exception:
            pass
        return None

    # ── Development: frontend/dist next to the project root ──
    dev_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dev_path.is_dir():
        return dev_path
    return None


def _setup_frontend_serving(app: FastAPI) -> None:
    """Mount the React SPA on the FastAPI app (production only)."""
    is_packaged = getattr(sys, 'frozen', False)
    frontend_dir = _get_frontend_dir()

    print(f"[frontend-serving] is_packaged={is_packaged}  "
          f"frontend_dir={frontend_dir}", flush=True)

    if not frontend_dir or not is_packaged:
        if is_packaged:
            print("[frontend-serving] WARNING: packaged mode but no frontend "
                  "directory found — app will show JSON 404", flush=True)
        return

    # Mount /assets for JS, CSS, images (Vite puts them here)
    assets_dir = frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)),
                  name="static-assets")
        print(f"[frontend-serving] mounted /assets → {assets_dir}", flush=True)

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

    print(f"[frontend-serving] SPA catch-all registered → {frontend_dir}",
          flush=True)


_setup_frontend_serving(app)
