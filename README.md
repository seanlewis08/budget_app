# Budget App

A privacy-first, AI-powered personal finance tracker that runs entirely on your local machine. Budget App connects to your bank accounts via Plaid, automatically categorizes transactions using a three-tier priority cascade engine, and packages everything into a cross-platform Electron desktop application. Your financial data never leaves your computer.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Screenshots](#screenshots)
- [System Requirements](#system-requirements)
- [Installation (Download)](#installation-download)
- [Development Setup](#development-setup)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [Plaid Bank Syncing](#plaid-bank-syncing)
- [AI Categorization Engine](#ai-categorization-engine)
- [Background Sync Daemon](#background-sync-daemon)
- [Database Git Backup](#database-git-backup)
- [Investment Portfolio Tracking](#investment-portfolio-tracking)
- [CSV Import](#csv-import)
- [Historical Archive Import](#historical-archive-import)
- [Building from Source](#building-from-source)
- [CI/CD Pipeline](#cicd-pipeline)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Tech Stack](#tech-stack)
- [Troubleshooting](#troubleshooting)
- [Future Enhancements](#future-enhancements)

---

## Overview

Budget App was born from years of tracking personal finances in Excel spreadsheets. The core insight was that most transactions come from the same merchants month after month, so a system that learns your patterns can automate 90%+ of categorization work. The remaining edge cases are handled by Claude AI, and anything uncertain goes into a human review queue.

The app is organized as three cooperating processes:

1. **FastAPI Backend** (Python) — REST API, database, categorization engine, Plaid integration, background sync
2. **React Frontend** (Vite) — 13-page single-page application with charts, tables, and a review workflow
3. **Electron Shell** — Desktop wrapper that bundles both into a native `.dmg` (macOS) or `.exe` (Windows) installer

All data is stored locally in SQLite at `~/BudgetApp/budget.db`. No cloud services are required beyond the Plaid API (for bank connections) and the Anthropic API (for AI categorization of unknown merchants).

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Electron Shell                        │
│   (main.js → BrowserWindow → backend-manager.js)        │
├─────────────────────────┬───────────────────────────────┤
│     React Frontend      │       FastAPI Backend          │
│                         │                                │
│  13 Pages:              │  Routers:                      │
│  · Review Queue         │  · /api/transactions           │
│  · Spending Analysis    │  · /api/accounts               │
│  · Cash Flow            │  · /api/categories             │
│  · Recurring Monitor    │  · /api/budgets                │
│  · Budget Tracker       │  · /api/import-csv             │
│  · Accounts             │  · /api/archive                │
│  · Data Browser         │  · /api/investments            │
│  · Categories Editor    │  · /api/insights               │
│  · Investments          │  · /api/settings               │
│  · AI Insights          │  · /api/notifications          │
│  · Settings             │                                │
│  · Deleted Transactions │  Services:                     │
│  · Sync History         │  · Priority Cascade Engine     │
│                         │  · Plaid Service (encrypted)   │
│  Vite · React Router    │  · Financial Advisor (Claude)  │
│  Recharts · Lucide      │  · APScheduler Background Jobs │
│                         │  · Price Fetcher (yfinance)    │
├─────────────────────────┴───────────────────────────────┤
│                    Data Layer                             │
│                                                          │
│  ~/BudgetApp/budget.db        (transactions, budgets)    │
│  ~/BudgetApp/investments.db   (holdings, securities)     │
│  ~/BudgetApp/logs/sync.log    (daemon logs)              │
├─────────────────────────────────────────────────────────┤
│                  External Services                        │
│                                                          │
│  Plaid API ─── bank connections, transaction sync        │
│  Anthropic API ─── Claude Haiku (categorization)         │
│                    Claude Sonnet (financial insights)     │
│  yfinance ─── live stock prices, market data             │
└─────────────────────────────────────────────────────────┘
```

---

## Features

### Transaction Management
- **AI-Powered Categorization**: Three-tier priority cascade — amount rules, merchant mappings, then Claude API fallback. Once a transaction matches at any tier, processing stops. No overwrites.
- **Review Queue**: Uncertain predictions land in a review queue. Confirm or change categories with one click. Batch operations with shift-click selection.
- **Two-Phase Commit**: Stage changes first (`pending_save`), then save all at once. Prevents accidental partial saves.
- **Soft Delete with Audit Trail**: Deleted transactions are preserved in a separate table for recovery.

### Bank Integration
- **Plaid Production Sync**: Connect Discover, SoFi (Checking + Savings), Wells Fargo, and any Plaid-supported bank.
- **Cursor-Based Incremental Sync**: Only fetches new/modified transactions since last sync. Efficient and fast.
- **Fernet-Encrypted Access Tokens**: Plaid access tokens are encrypted at rest using the `cryptography` library.
- **OAuth Support**: Handles bank-initiated OAuth redirects for institutions that require it.
- **Auto-Linking Sibling Accounts**: When you connect one account at an institution, the app automatically discovers and links other accounts (e.g., checking + savings at the same bank).

### Analytics & Visualization
- **Spending Dashboard**: Monthly breakdown by category with pie charts, bar charts, and trend lines (Recharts).
- **Cash Flow Analysis**: Biweekly income vs. expense stacked area charts with drill-down by category.
- **Recurring Transaction Monitor**: Multi-month grid view of subscription charges for detecting price changes.
- **Budget Tracking**: Set monthly targets per category, with color-coded progress bars showing real-time spending.
- **Data Browser**: Full transaction table with date range filters, category filters, sorting, and pagination.

### AI Financial Insights
- **Streaming AI Analysis**: Claude Sonnet generates detailed financial analysis from a snapshot of your data, streamed via Server-Sent Events (SSE).
- **Follow-Up Chat**: Ask Claude Haiku follow-up questions about your finances after the initial analysis.
- **Prompt Caching**: Reuses the financial snapshot across follow-up messages for ~90% cost reduction.

### Investment Portfolio
- **Separate Database**: Investment data lives in `investments.db`, isolated from the main budget database.
- **Plaid Investment Sync**: Pull holdings and transactions from brokerage accounts.
- **Live Prices**: yfinance fetches current stock/ETF prices every 30 minutes during market hours.
- **Asset Allocation**: Breakdown by security type and sector with visualization.
- **Performance Tracking**: Time-series charts with SPY benchmark comparison.

### Desktop App
- **Cross-Platform**: macOS `.dmg` (Intel + Apple Silicon) and Windows `.exe` (NSIS installer).
- **PyInstaller Backend**: The Python backend is bundled into a single executable, embedded inside the Electron app.
- **In-App Settings**: Configure Plaid credentials and Anthropic API key from the Settings page — no `.env` editing required.
- **Background Sync**: APScheduler runs bank sync every 4 hours, investment sync every 6 hours, and price refresh every 30 minutes.

### Data Management
- **CSV Import**: Upload bank CSV exports from Discover, SoFi, and Wells Fargo. Auto-detects format.
- **Historical Archive Import**: Batch-import years of Excel/CSV archives (2021-2024) with deduplication.
- **Category Taxonomy Editor**: Create, rename, merge, and color-code categories. Two-level hierarchy (parent → child).
- **Database Git Backup**: The sync daemon can automatically commit `budget.db` to a private Git repo after each sync.

---

## System Requirements

### For Running the Installer
- **macOS**: 10.15 (Catalina) or later, Intel or Apple Silicon
- **Windows**: Windows 10 or later, 64-bit

### For Development
- Python 3.10 or later
- Node.js 20 or later
- npm 10 or later
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)
- Git

### External API Keys (Optional)
- **Plaid** — Required for bank account connections. [Sign up at plaid.com](https://dashboard.plaid.com/signup)
- **Anthropic** — Required for AI categorization and insights. [Get an API key](https://console.anthropic.com/)

---

## Installation (Download)

### macOS

1. Download the latest `.dmg` from [GitHub Releases](https://github.com/seanlewis08/budget_app/releases)
   - **Apple Silicon** (M1/M2/M3): `Budget-App-X.X.X-arm64.dmg`
   - **Intel**: `Budget-App-X.X.X.dmg`
2. Open the `.dmg` and drag **Budget App** to your Applications folder
3. On first launch, macOS will block the unsigned app. Run this once:
   ```bash
   xattr -cr "/Applications/Budget App.app"
   ```
   This removes the quarantine flag. It's required because the app is not signed with an Apple Developer certificate ($99/year). Your data is safe — the app runs entirely locally.
4. Launch Budget App from your Applications folder

### Windows

1. Download `Budget-App-Setup-X.X.X.exe` from [GitHub Releases](https://github.com/seanlewis08/budget_app/releases)
2. Run the installer — you can choose the installation directory
3. Launch **Budget App** from the Start menu or desktop shortcut

### First Launch

On first launch, the app:
1. Creates `~/BudgetApp/` directory and `budget.db` database
2. Seeds 17 parent categories, 80+ subcategories, 4 default bank accounts, and 50+ merchant mappings
3. Starts the FastAPI backend on port 8000
4. Opens the React dashboard

To connect your bank accounts, go to **Settings** and enter your Plaid credentials, then go to **Accounts** to link your banks via Plaid.

---

## Development Setup

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/seanlewis08/budget_app.git
cd budget_app

# Install Python dependencies (creates .venv automatically)
uv sync

# Install Node.js dependencies (also installs frontend deps via postinstall)
npm install

# Create environment file
cp .env.example .env
# Edit .env and add your API keys (or configure later via Settings page)
```

### Start Development Servers

```bash
# Start everything (backend + frontend + Electron)
./start.sh

# Or start individually:
npm run dev:backend    # FastAPI at http://localhost:8000
npm run dev:frontend   # React at http://localhost:5173
npm run dev:electron   # Electron window (after backend/frontend are running)

# Or backend + frontend together (no Electron window):
npm run dev
```

### Key URLs in Development

| URL | Description |
|-----|-------------|
| `http://localhost:5173` | React dashboard (Vite dev server with hot reload) |
| `http://localhost:8000/docs` | FastAPI interactive API documentation (Swagger UI) |
| `http://localhost:8000/redoc` | Alternative API docs (ReDoc) |
| `http://localhost:8000/health` | Health check endpoint |

The Vite dev server proxies `/api/*` requests to the FastAPI backend, so the frontend works seamlessly in development.

---

## Configuration

### Environment Variables (`.env`)

```bash
# ── Plaid (bank connections) ──
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_sandbox_secret
PLAID_PRODUCTION_SECRET=your_production_secret
PLAID_ENV=production              # "sandbox", "development", or "production"
PLAID_RECOVERY_CODE=              # Optional: backup recovery code
PLAID_TOKEN_ENCRYPTION_KEY=       # Auto-generated on first use if blank

# ── Anthropic (AI categorization + insights) ──
ANTHROPIC_API_KEY=sk-ant-...

# ── Auto-Confirm Threshold ──
AUTO_CONFIRM_THRESHOLD=3          # Merchant mapping confidence needed to skip review

# ── Email Notifications (Phase 3 — not yet implemented) ──
# EMAIL_ADDRESS=
# EMAIL_APP_PASSWORD=
```

### In-App Settings

You can also configure API keys from the **Settings** page inside the app. Settings saved through the UI are stored in the database and take priority over `.env` file values. This means you don't need to edit `.env` if you prefer the GUI.

### Data Directory

All persistent data lives at `~/BudgetApp/`:

```
~/BudgetApp/
├── budget.db             # Main database (transactions, categories, budgets)
├── investments.db        # Investment portfolio database
└── logs/
    └── sync.log          # Background sync daemon logs
```

This directory survives app updates and reinstalls.

---

## Usage Guide

### Typical Workflow

1. **Connect your banks** — Go to Accounts → Add Account → Connect via Plaid
2. **Sync transactions** — The app syncs automatically every 4 hours, or click "Sync All" manually
3. **Review categorizations** — Go to Review Queue to confirm or fix AI predictions
4. **Track spending** — View Spending, Cash Flow, and Budget pages for analysis
5. **Get AI insights** — Visit the Insights page for Claude-powered financial analysis

### Review Queue

The Review Queue is the primary interaction point. New transactions arrive with predicted categories:
- **Green badge** = Amount Rule match (high confidence, auto-confirmed)
- **Blue badge** = Merchant Mapping match (medium confidence, may need review)
- **Purple badge** = AI prediction (always needs review)

Click a transaction to change its category, then "Save" to commit all changes. When you confirm a categorization, the app learns — it creates or updates a merchant mapping so future transactions from the same merchant are auto-categorized.

### Keyboard Shortcuts

In the Review Queue:
- **Click** a transaction to select it
- **Shift+Click** to select a range for batch operations
- **Enter** to confirm selected transactions

---

## Plaid Bank Syncing

### How It Works

The Plaid integration follows a 7-step flow:

1. **Create Link Token** — Backend calls Plaid's `/link/token/create` with the account ID
2. **Open Plaid Link** — Frontend opens Plaid's embedded widget using the link token
3. **User Authenticates** — User logs into their bank through Plaid's secure UI
4. **Exchange Public Token** — Backend exchanges the temporary public token for a persistent access token
5. **Encrypt & Store** — Access token is encrypted with Fernet and stored in the database
6. **Sync Transactions** — Backend calls Plaid's `/transactions/sync` using cursor-based pagination
7. **Auto-Categorize** — Each new transaction is run through the Priority Cascade Engine

### Cursor-Based Sync

Plaid's sync endpoint uses a cursor to track where you left off. On each sync:
- Send the cursor from the last sync
- Receive only new/modified/removed transactions since then
- Update the cursor for next time

This is much more efficient than re-downloading all transactions each time.

### Deduplication

Every Plaid transaction has a unique `plaid_transaction_id`. The app checks this before inserting, preventing duplicate transactions even if you sync multiple times.

### Supported Banks

Any bank supported by Plaid will work. The app has been tested with:
- Discover (credit card)
- SoFi (checking + savings)
- Wells Fargo (checking)

### Sync Schedule

| Trigger | Frequency | Source |
|---------|-----------|--------|
| APScheduler (in-app) | Every 4 hours | `services/sync_scheduler.py` |
| LaunchAgent daemon | Every 12 hours + on wake/login | `sync_daemon.py` |
| Manual | On demand | Accounts page "Sync All" button |

---

## AI Categorization Engine

### Three-Tier Priority Cascade

The categorization engine processes each transaction through three tiers in order. Once a match is found at any tier, processing stops immediately.

#### Tier 1: Amount Rules

Amount rules handle ambiguous merchants like Apple (could be iCloud, Apple Music, or an App Store purchase) and Venmo (could be rent, dinner, or anything). They match on both the merchant name AND the exact dollar amount.

Example: "APPLE.COM/BILL" + $0.99 → iCloud Storage, "APPLE.COM/BILL" + $6.99 → Apple TV+

Amount rules always auto-confirm with 100% confidence.

#### Tier 2: Merchant Mappings

Merchant mappings are regex patterns learned from your transaction history. There are 50+ seeded at startup, and the app creates new ones whenever you confirm a categorization in the Review Queue.

Mappings have a confidence score (integer). When confidence ≥ 3 (the `AUTO_CONFIRM_THRESHOLD`), transactions are auto-confirmed without human review. New mappings start at confidence 1 and increase each time you confirm a matching transaction.

Example: `NETFLIX` → Entertainment/Streaming (confidence: 5, auto-confirmed)

#### Tier 3: Claude AI Fallback

For unknown merchants with no matching rules or mappings, the app calls Claude Haiku with:
- The full list of valid category names
- The 50 most recent confirmed transactions as few-shot examples
- The new transaction's description and amount

AI predictions always land in the Review Queue (never auto-confirmed) with a confidence of 0.7.

### Learning Loop

When you confirm a transaction in the Review Queue:
1. If no merchant mapping exists for this merchant → one is created (confidence: 1)
2. If a mapping already exists → its confidence is incremented
3. Once confidence reaches 3 → future transactions auto-confirm

This creates a virtuous cycle: the more you use the app, the fewer transactions need manual review.

---

## Background Sync Daemon

A standalone Python script (`backend/sync_daemon.py`) that runs independently of the desktop app. It connects to Plaid, pulls new transactions, categorizes them, and writes directly to `~/BudgetApp/budget.db`.

### How It Works

The daemon can run in two modes:
1. **One-shot**: Sync once and exit (default for LaunchAgent)
2. **Loop mode**: Sync continuously every N hours (for server deployment)

### macOS LaunchAgent Setup

```bash
# Create the logs directory
mkdir -p ~/BudgetApp/logs

# Copy the plist to LaunchAgents
cp com.seanlewis.budgetapp.sync.plist ~/Library/LaunchAgents/

# Load (activate) the daemon
launchctl load ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist
```

The daemon triggers on every login/wake plus every 12 hours. Logs go to `~/BudgetApp/logs/sync.log`.

### Daemon Commands

```bash
# Check if the daemon is running
launchctl list | grep budgetapp

# View sync logs
cat ~/BudgetApp/logs/sync.log

# Run a manual sync (outside the daemon)
cd ~/DataspellProjects/budget-app
uv run python3 -m backend.sync_daemon

# Stop the daemon
launchctl unload ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist

# Restart after editing the plist
launchctl unload ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist
launchctl load ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist
```

---

## Database Git Backup

The sync daemon can automatically commit `budget.db` to a private Git repository after each sync, giving you a full version history of your financial data.

### Setup (One-Time)

1. Create a **private** repo on GitHub (e.g., `budget-app-data`)
2. Run the setup script:

```bash
bash scripts/setup-db-backup.sh
```

Or manually:

```bash
cd ~/BudgetApp
git init
echo "logs/" > .gitignore
git remote add origin git@github.com:yourusername/budget-app-data.git
git add .gitignore budget.db
git commit -m "Initial database backup"
git branch -M main
git push -u origin main
```

After setup, every sync automatically commits and pushes with a descriptive message:
`Backup 2026-02-15 09:00 — 1,247 transactions, 4.2 MB`

### Disable Backup

```bash
uv run python3 -m backend.sync_daemon --no-backup
```

---

## Investment Portfolio Tracking

Budget App includes a separate investment tracking system with its own database (`~/BudgetApp/investments.db`).

### Features

- **Manual or Plaid-Connected Accounts**: Add brokerage accounts manually or link via Plaid
- **Holding Snapshots**: Daily snapshots for time-series charting
- **Live Prices**: yfinance fetches current prices every 30 minutes during US market hours (9:30 AM – 4:00 PM Eastern, weekdays)
- **Asset Allocation**: Breakdown by security type (stock, ETF, bond, etc.) and sector
- **Performance Charts**: Time-series with SPY benchmark overlay
- **Automatic Sync**: APScheduler syncs investment holdings every 6 hours

### Investment Models

The investment database has 4 tables:
- `investment_accounts` — Brokerage accounts (name, institution, Plaid connection)
- `securities` — Individual securities (ticker, name, type, sector, close price)
- `holdings` — Current and historical positions (shares, cost basis, value)
- `investment_transactions` — Buy/sell/dividend transactions

---

## CSV Import

For banks not yet connected via Plaid, or for historical data, you can upload CSV files from the Accounts page.

### Supported Formats

| Bank | Expected Columns |
|------|-----------------|
| Discover | Trans. Date, Post Date, Description, Amount, Category |
| SoFi | Date, Description, Amount, Type |
| Wells Fargo | Date, Amount, *, *, Description |

The app auto-detects the bank format from the CSV column headers. Each imported transaction is run through the full categorization engine.

---

## Historical Archive Import

If you have years of financial data in Excel spreadsheets (as many people do), the archive import system can batch-import them.

### How It Works

1. Place your Excel/CSV files in the `Budget/Archive/` directory, organized by year
2. Go to the **Data** page → **Archive** tab
3. The app scans for files and shows what data is available
4. Click "Import" to load historical transactions with deduplication

### Supported Archive Formats

The importer handles multi-sheet Excel workbooks with varying column layouts. It auto-creates missing subcategories during import.

---

## Building from Source

### Prerequisites

- Python 3.10+ with PyInstaller
- Node.js 20+ with npm
- [uv](https://docs.astral.sh/uv/) for Python dependency management

### Build Commands

```bash
# Build everything (frontend + Electron app)
npm run build

# Or step by step:
npm run build:frontend      # Build React → frontend/dist/
npm run build:backend       # PyInstaller → backend/dist/budget-app-backend
npx electron-builder --mac  # Package → dist/*.dmg
npx electron-builder --win  # Package → dist/*.exe
```

### Build Output

```
dist/
├── Budget-App-X.X.X-arm64.dmg      # macOS Apple Silicon
├── Budget-App-X.X.X.dmg             # macOS Intel
└── Budget-App-Setup-X.X.X.exe       # Windows x64
```

### macOS Unsigned App Note

Since the app is not code-signed, users must run `xattr -cr "/Applications/Budget App.app"` after installation. This removes the macOS quarantine flag that blocks unsigned applications.

---

## CI/CD Pipeline

The project uses GitHub Actions for automated builds. The workflow is defined in `.github/workflows/build-release.yml`.

### How It Works

1. Push a version tag (e.g., `git tag v0.1.3 && git push origin v0.1.3`)
2. GitHub Actions spins up two runners in parallel:
   - **macOS runner**: Builds PyInstaller backend + Electron `.dmg` (Intel + ARM)
   - **Windows runner**: Builds PyInstaller backend + Electron `.exe` (x64)
3. Both artifacts are uploaded to a GitHub Release

### Manual Trigger

You can also trigger builds manually from the GitHub Actions tab → "Run workflow" button.

### Build Pipeline Steps

Each runner executes:
1. Checkout code
2. Setup Python 3.11 + Node.js 20
3. `pip install pyinstaller && pip install .`
4. `npm install && cd frontend && npm install`
5. `npm run build:frontend`
6. `cd backend && pyinstaller budget-app.spec`
7. `npx electron-builder --mac` (or `--win`)
8. Upload artifacts → Create GitHub Release

---

## Project Structure

```
budget-app/
├── backend/                           # Python FastAPI backend
│   ├── main.py                        # App entry point, router registration, lifespan
│   ├── database.py                    # SQLite engine, WAL mode, session management
│   ├── investments_database.py        # Separate SQLite for investments
│   ├── models.py                      # 10 SQLAlchemy models (Category, Transaction, etc.)
│   ├── models_investments.py          # 4 investment models (Security, Holding, etc.)
│   ├── migrations.py                  # Lightweight column-addition migrations
│   ├── run_app.py                     # PyInstaller entry point
│   ├── sync_daemon.py                 # Standalone background sync script
│   ├── budget-app.spec                # PyInstaller build specification
│   │
│   ├── routers/                       # FastAPI API endpoints
│   │   ├── transactions.py            # CRUD + review workflow + analysis endpoints
│   │   ├── accounts.py                # Bank accounts + Plaid Link + sync triggers
│   │   ├── categories.py              # Taxonomy CRUD + merchant mappings + amount rules
│   │   ├── budgets.py                 # Monthly budget targets
│   │   ├── import_csv.py              # CSV upload + auto-detection
│   │   ├── archive.py                 # Historical Excel archive import
│   │   ├── investments.py             # Investment portfolio endpoints
│   │   ├── insights.py                # AI financial analysis (SSE streaming)
│   │   ├── settings.py                # API key management (DB-backed)
│   │   └── notifications.py           # Email notifications (placeholder)
│   │
│   ├── services/                      # Business logic
│   │   ├── categorize.py              # 3-tier Priority Cascade Engine
│   │   ├── plaid_service.py           # Plaid API wrapper + Fernet encryption
│   │   ├── seed_data.py               # Initial categories, accounts, mappings
│   │   ├── financial_advisor.py       # Data aggregation for AI insights
│   │   ├── sync_scheduler.py          # APScheduler background jobs
│   │   ├── price_fetcher.py           # yfinance stock price updates
│   │   ├── archive_importer.py        # Excel/CSV archive import logic
│   │   └── csv_parsers/               # Bank-specific CSV parsers
│   │       ├── discover.py
│   │       ├── sofi.py
│   │       └── wellsfargo.py
│   │
│   └── scripts/                       # Maintenance & migration scripts
│       ├── migrate_categories.py
│       ├── fix_care_credit.py
│       ├── fix_care_credit_signs.py
│       ├── rollback_care_credit.py
│       ├── fix_discover_payments.py
│       ├── fix_categories.py
│       ├── inspect_account.py
│       ├── inspect_roundups.py
│       ├── income_audit.py
│       └── count_transactions.py
│
├── frontend/                          # React SPA (Vite)
│   ├── src/
│   │   ├── main.jsx                   # React DOM mount
│   │   ├── App.jsx                    # Router, sidebar, Plaid Link
│   │   ├── styles.css                 # 1500+ lines, dark theme, design system
│   │   ├── components/
│   │   │   └── CategoryPicker.jsx     # Reusable hierarchical category selector
│   │   └── pages/
│   │       ├── ReviewQueue.jsx        # Transaction review + batch confirm
│   │       ├── Spending.jsx           # Monthly category breakdown charts
│   │       ├── CashFlow.jsx           # Income vs. expense analysis
│   │       ├── RecurringMonitor.jsx   # Subscription tracking grid
│   │       ├── Budget.jsx             # Monthly targets + progress bars
│   │       ├── Accounts.jsx           # Bank connections + CSV import
│   │       ├── Data.jsx               # Full transaction table browser
│   │       ├── Categories.jsx         # Taxonomy editor
│   │       ├── Investments.jsx        # Portfolio dashboard
│   │       ├── Insights.jsx           # AI financial advisor chat
│   │       ├── Settings.jsx           # API key configuration
│   │       ├── DeletedTransactions.jsx # Soft-delete recovery
│   │       └── SyncHistory.jsx        # Plaid sync audit log
│   ├── index.html
│   ├── package.json
│   └── vite.config.js                 # Proxy /api → localhost:8000
│
├── electron/                          # Electron desktop wrapper
│   ├── main.js                        # Window creation, startup sequence
│   ├── backend-manager.js             # Python process lifecycle
│   ├── preload.js                     # Secure IPC bridge
│   └── icons/
│       ├── icon.png                   # Source icon (2048x2048)
│       ├── icon.icns                  # macOS icon
│       └── icon.ico                   # Windows icon
│
├── scripts/                           # Project-level scripts
│   ├── setup-db-backup.sh             # One-time Git backup setup
│   ├── backfill_sync_logs.py          # Parse log files → SyncLog table
│   └── import_all_archives.py         # Batch archive import
│
├── website/                           # Static marketing site + docs
│   ├── index.html                     # Landing page
│   ├── styles.css
│   └── docs/                          # 7-part build walkthrough
│       ├── 01-project-setup.html
│       ├── 02-database-and-models.html
│       ├── 03-plaid-integration.html
│       ├── 04-categorization-engine.html
│       ├── 05-frontend-react.html
│       ├── 06-advanced-features.html
│       └── 07-electron-and-deployment.html
│
├── docs/walkthrough/                  # Markdown source for docs
│   ├── 01-project-setup.md
│   ├── 02-database-and-models.md
│   ├── 03-plaid-integration.md
│   ├── 04-categorization-engine.md
│   ├── 05-frontend-react.md
│   ├── 06-advanced-features.md
│   └── 07-electron-and-deployment.md
│
├── Budget/                            # Historical financial data (Excel/CSV)
│   ├── Archive/                       # 2021–2024 yearly archives
│   └── YTD_downloads/                 # Current year bank exports
│
├── .github/workflows/
│   └── build-release.yml              # CI/CD: build + release on tag push
├── com.seanlewis.budgetapp.sync.plist # macOS LaunchAgent for sync daemon
├── package.json                       # Electron + electron-builder config
├── pyproject.toml                     # Python project config (uv)
├── start.sh                           # Development launcher script
└── .env.example                       # Environment variable template
```

---

## API Reference

The FastAPI backend exposes 57+ endpoints. Full interactive documentation is available at `http://localhost:8000/docs` when the backend is running.

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/transactions` | List transactions (filterable by status, date, account, category) |
| POST | `/api/transactions/{id}/confirm` | Confirm a transaction's category |
| POST | `/api/transactions/{id}/stage` | Stage a category change (two-phase commit) |
| POST | `/api/transactions/save-staged` | Commit all staged changes |
| DELETE | `/api/transactions/{id}` | Soft-delete a transaction |
| GET | `/api/transactions/spending-by-category` | Spending breakdown for charts |
| GET | `/api/transactions/monthly-trends` | Month-over-month trend data |
| GET | `/api/transactions/cash-flow` | Income vs. expense by period |
| GET | `/api/transactions/recurring` | Recurring transaction detection |

### Accounts & Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/accounts` | List all accounts with stats |
| POST | `/api/accounts` | Create a new account |
| POST | `/api/accounts/link/token` | Generate Plaid Link token |
| POST | `/api/accounts/link/exchange` | Exchange public token for access token |
| POST | `/api/accounts/{id}/sync` | Sync a single account via Plaid |
| POST | `/api/accounts/sync-all` | Sync all connected accounts |
| POST | `/api/accounts/{id}/balances` | Refresh account balances |
| POST | `/api/accounts/{id}/disconnect` | Disconnect a Plaid-linked account |

### Categories & Rules

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/categories` | Full category tree |
| POST | `/api/categories` | Create category |
| PUT | `/api/categories/{id}` | Update category |
| DELETE | `/api/categories/{id}` | Delete category |
| GET | `/api/categories/merchant-mappings` | List all merchant mappings |
| POST | `/api/categories/merchant-mappings` | Create merchant mapping |
| GET | `/api/categories/amount-rules` | List all amount rules |
| POST | `/api/categories/amount-rules` | Create amount rule |

### Settings & Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Get all settings (masked secrets) |
| POST | `/api/settings` | Save settings to database |

### AI Insights

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/insights/analyze` | Stream AI financial analysis (SSE) |
| POST | `/api/insights/chat` | Follow-up chat with AI |
| GET | `/api/insights/snapshot` | Get raw financial data snapshot |

### Investments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/investments/accounts` | List investment accounts |
| GET | `/api/investments/holdings` | Current portfolio holdings |
| GET | `/api/investments/performance` | Time-series performance data |
| POST | `/api/investments/sync` | Sync investment data via Plaid |
| POST | `/api/investments/prices/refresh` | Force price update via yfinance |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.10+, FastAPI | REST API, business logic |
| **ORM** | SQLAlchemy 2.0 | Database models, queries |
| **Database** | SQLite (WAL mode) | Local data storage |
| **Frontend** | React 18, Vite | Single-page application |
| **Charts** | Recharts | Data visualization |
| **Icons** | Lucide React | UI iconography |
| **Desktop** | Electron 33 | Native app wrapper |
| **Packaging** | electron-builder | Cross-platform installers |
| **Bundling** | PyInstaller | Python → standalone executable |
| **AI** | Anthropic Claude API | Categorization (Haiku), insights (Sonnet) |
| **Banking** | Plaid API | Account connections, transaction sync |
| **Market Data** | yfinance | Live stock/ETF prices |
| **Encryption** | Fernet (cryptography) | Access token encryption at rest |
| **Scheduling** | APScheduler | Background sync jobs |
| **CI/CD** | GitHub Actions | Automated cross-platform builds |

---

## Troubleshooting

### macOS: "Budget App is damaged and can't be opened"

This happens because the app is unsigned. Fix it with:
```bash
xattr -cr "/Applications/Budget App.app"
```

### Port 8000 Already in Use

A previous backend process is still running. Kill it:
```bash
lsof -ti:8000 | xargs kill -9
```

### "Could not connect to backend" in the UI

The FastAPI backend hasn't started yet or crashed. Check:
1. Is port 8000 available? (`lsof -i :8000`)
2. Check the terminal/console for Python errors
3. Make sure `~/BudgetApp/` directory exists and is writable

### Settings Won't Save (405 Method Not Allowed)

This was a known issue in versions before 0.1.2. The SPA catch-all route was interfering with POST requests. Update to the latest version.

### Plaid Link Won't Open

Make sure you've entered your Plaid credentials in Settings and clicked Save. The link token requires a valid Plaid client ID.

### Transactions Not Auto-Categorizing

Check that:
1. The Anthropic API key is configured in Settings (for AI categorization)
2. Merchant mappings exist for the merchant (Categories → Merchant Mappings tab)
3. The categorization engine logs are visible in the terminal: `Tier 1 match:`, `Tier 2 match:`, `Tier 3 AI:`

---

## Future Enhancements

- **Self-Hosted Cloud Server**: Deploy the backend to a personal Linux server for 24/7 syncing and multi-machine access (PostgreSQL, VPN tunneling)
- **Plaid Webhooks**: Real-time transaction notifications via Cloudflare Tunnel instead of polling
- **Email Notifications**: Daily/weekly spending summaries sent to your inbox
- **Mobile Access**: Connect your phone to the self-hosted API for on-the-go checking
- **Local LLM Support**: Option to use Ollama or similar for categorization without an API key
- **Apple Developer Signing**: Code-sign the macOS app to eliminate the `xattr` workaround
- **Auto-Updates**: electron-updater checks for new versions on launch

---

## License

MIT License — see [LICENSE](LICENSE) for details.

## Author

Built by [Sean Lewis](https://github.com/seanlewis08).

---

*For a comprehensive 7-part build walkthrough documenting how to build the entire app from scratch, visit the [documentation site](https://seanlewis08.github.io/budget_app/docs/).*
