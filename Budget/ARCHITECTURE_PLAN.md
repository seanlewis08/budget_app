# Personal Finance App — Architecture Plan

## Overview

A local-first desktop budgeting application that automatically pulls bank transactions via Plaid, categorizes them using a tiered AI engine, and provides interactive dashboards for reviewing spending. Everything runs on your machine — no cloud database, no subscription fees beyond pennies for API calls.

## Your Accounts

- **Discover** — credit card
- **SoFi** — checking account
- **SoFi** — savings account
- **Wells Fargo** — checking/savings

All four institutions are connected via Plaid in production mode. Wells Fargo uses OAuth-based authentication.

---

## Current Status

### What's Built and Working

- **Plaid Integration** — All 4 accounts connected in production with `days_requested=730` for 2 years of historical pull on first connection. Cursor-based incremental sync for subsequent pulls.
- **Archive Import** — One-time import of 2021–2024 historical data from Excel archives (4,631 transactions). 2025–2026 data sourced exclusively from Plaid.
- **Background Sync Daemon** — macOS LaunchAgent (`com.seanlewis.budgetapp.sync.plist`) runs Plaid sync every 12 hours automatically, with Git-based database backup after each sync.
- **Git Database Backup** — `~/BudgetApp/budget.db` pushed to private GitHub repo (`seanlewis08/budget-app-data`) after every sync.
- **Review Queue** — Home screen showing pending transactions as cards with confirm/change functionality. Bulk actions supported.
- **Data Page** — Full transaction browser with year filter, account filter, search, configurable page size (50/100/All), and pagination.
- **Categories Page** — View and manage the two-level category taxonomy.
- **Spending Page** — Charts for spending by category and monthly trends.
- **Accounts Page** — Account summary with Plaid Link for connecting/reconnecting banks.
- **Settings Page** — Configuration management.
- **Budget Page** — Budget targets and tracking (scaffold in place).

### What's Not Yet Built

- **Email/WhatsApp Notifications** — Phase 3 (categorize on the go via email reply)
- **Cloudflare Tunnel** — Not needed currently; sync daemon handles pulls without webhooks
- **Electron Packaging** — App runs in dev mode (separate backend + frontend); not yet packaged as an installer
- **AI Categorization (Tier 3)** — Claude API fallback for unknown merchants not yet wired up
- **Fine-Tuned Model (Tier 4)** — Future enhancement once enough labeled data exists
- **Self-Hosted Cloud Server** — Documented as future enhancement

---

## Tech Stack

### Architecture

```
┌─────────────────────────────────────────────────────┐
│              LOCAL DESKTOP APP                        │
│                                                       │
│  ┌──────────────┐     ┌──────────────────────────┐   │
│  │   React       │     │   Python (FastAPI)        │   │
│  │   Dashboard   │────>│   Backend                 │   │
│  │   :5173       │     │   :8000                   │   │
│  └──────────────┘     │                           │   │
│                        │  ┌─────────────────────┐ │   │
│                        │  │  SQLite Database     │ │   │
│                        │  │  ~/BudgetApp/        │ │   │
│                        │  │  budget.db           │ │   │
│                        │  └─────────────────────┘ │   │
│                        └──────────┬───────────────┘   │
│                                   │                    │
│  ┌────────────────────────────────┼──────────────┐    │
│  │  Sync Daemon (LaunchAgent)                    │    │
│  │  Runs every 12 hours:                         │    │
│  │    1. Plaid sync (cursor-based)               │    │
│  │    2. Git backup to GitHub                    │    │
│  └────────────────────────────────┼──────────────┘    │
└───────────────────────────────────┼────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │           INTERNET             │
                    │                                │
                    │  ┌─────────┐  ┌────────────┐  │
                    │  │  Plaid  │  │  GitHub     │  │
                    │  │  API    │  │  (backups)  │  │
                    │  └─────────┘  └────────────┘  │
                    │          ┌──────────┐          │
                    │          │ Claude   │          │
                    │          │ API      │          │
                    │          └──────────┘          │
                    └────────────────────────────────┘
```

### Backend: Python + FastAPI

- **Python 3.10+** managed via `uv` (package manager)
- **FastAPI** with auto-generated API docs at `localhost:8000/docs`
- **SQLAlchemy 2.0** ORM with SQLite
- **Runs as**: `uv run uvicorn backend.main:app --reload --port 8000`

### Frontend: React + Vite

- **React** with Vite dev server on port 5173
- **Recharts** for spending visualizations
- **Lucide React** for icons
- **React Plaid Link** for bank connection widget
- **Runs as**: `npm run dev` from the `frontend/` directory

### Database: SQLite

- **Location**: `~/BudgetApp/budget.db`
- **WAL mode** enabled for concurrent read/write (sync daemon + app)
- **Foreign keys** enforced at connection level
- **Backed up** to `git@github.com:seanlewis08/budget-app-data.git` after every sync

### Sync Daemon: macOS LaunchAgent

- **Plist**: `com.seanlewis.budgetapp.sync.plist`
- **Schedule**: Every 12 hours + once on login (`RunAtLoad`)
- **What it does**: Syncs all connected Plaid accounts, then commits and pushes `budget.db` to GitHub
- **Logs**: `~/BudgetApp/logs/sync-stdout.log`, `sync-stderr.log`, `sync.log`
- **Install**: `cp com.seanlewis.budgetapp.sync.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist`
- **Uninstall**: `launchctl unload ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist`

---

## Project Structure

```
budget-app/
├── backend/                         # Python FastAPI application
│   ├── main.py                      # App entry point, registers routers, lifespan events
│   ├── database.py                  # SQLite connection (~/BudgetApp/budget.db), WAL mode
│   ├── models.py                    # SQLAlchemy models (7 tables)
│   ├── migrations.py                # Schema migrations
│   ├── sync_daemon.py               # Standalone sync + Git backup script
│   ├── routers/
│   │   ├── transactions.py          # Transaction CRUD, review, spending/trend endpoints
│   │   ├── categories.py            # Category management
│   │   ├── accounts.py              # Account management + Plaid Link/sync
│   │   ├── budgets.py               # Budget CRUD
│   │   ├── archive.py               # Archive import endpoints
│   │   ├── import_csv.py            # CSV import endpoint
│   │   └── notifications.py         # Email notification (scaffold)
│   └── services/
│       ├── archive_importer.py      # Excel/CSV archive import (2021–2024 formats)
│       ├── categorize.py            # Priority cascade categorization engine
│       ├── plaid_service.py         # Plaid API client with Fernet token encryption
│       ├── seed_data.py             # Category taxonomy + account seeding
│       ├── sync_scheduler.py        # APScheduler-based background sync
│       └── csv_parsers/
│           ├── discover.py
│           ├── sofi.py
│           └── wellsfargo.py
│
├── frontend/                        # React dashboard
│   ├── src/
│   │   ├── App.jsx                  # Router setup, sidebar navigation
│   │   ├── main.jsx                 # React entry point
│   │   ├── styles.css               # All app styles (dark theme)
│   │   └── pages/
│   │       ├── ReviewQueue.jsx      # Home screen — confirm/change categories
│   │       ├── Spending.jsx         # Charts + spending overview
│   │       ├── Budget.jsx           # Budget targets + progress
│   │       ├── Accounts.jsx         # Account summary + Plaid Link
│   │       ├── Data.jsx             # Transaction browser with year/account filters
│   │       ├── Categories.jsx       # Category taxonomy viewer
│   │       └── Settings.jsx         # App configuration
│   └── vite.config.js               # Vite config with API proxy to :8000
│
├── electron/                        # Electron desktop shell (future packaging)
│   ├── main.js
│   ├── preload.js
│   └── backend-manager.js
│
├── scripts/
│   ├── import_all_archives.py       # One-time bulk archive import (2021–2024)
│   └── setup-db-backup.sh           # One-time Git backup initialization
│
├── com.seanlewis.budgetapp.sync.plist  # macOS LaunchAgent for sync daemon
├── pyproject.toml                   # Python dependencies (uv)
├── .env                             # API keys (Plaid, Claude, encryption key)
└── .gitignore
```

---

## Data Model

### Tables

```
categories
├── id (PK, auto-increment)
├── short_desc (unique, indexed — e.g., "groceries", "fast_food")
├── display_name ("Groceries", "Fast Food")
├── parent_id (FK → categories, nullable — null = parent category)
├── color (hex, for charts)
├── is_income (boolean)
├── is_recurring (boolean)
└── created_at

accounts
├── id (PK, auto-increment)
├── name ("SoFi Checking", "Discover Card")
├── institution ("sofi", "discover", "wellsfargo")
├── account_type ("checking", "savings", "credit")
├── plaid_item_id
├── plaid_access_token (Fernet-encrypted)
├── plaid_account_id
├── plaid_cursor (for incremental transaction sync)
├── plaid_connection_status ("connected", "disconnected", "error")
├── last_synced_at
├── last_sync_error
├── balance_current / balance_available / balance_limit
├── balance_updated_at
└── created_at

transactions
├── id (PK, auto-increment)
├── account_id (FK → accounts)
├── plaid_transaction_id (unique, for deduplication)
├── date
├── description (raw from bank)
├── merchant_name (cleaned)
├── amount (positive = expense, negative = income)
├── category_id (FK → categories, nullable — assigned category)
├── predicted_category_id (FK → categories, nullable — AI suggestion)
├── status ("pending_review", "confirmed", "auto_confirmed")
├── source ("plaid_sync", "archive_import", "csv_import")
├── is_pending (boolean, for pending credit card charges)
├── categorization_tier ("amount_rule", "merchant_map", "ai")
├── created_at
└── Indexes: date, status, (account_id + date)

merchant_mappings
├── id (PK, auto-increment)
├── merchant_pattern (unique — e.g., "SAFEWAY", "CHEVRON")
├── category_id (FK → categories)
├── confidence (int — auto-confirms when ≥ 3)
└── created_at

amount_rules
├── id (PK, auto-increment)
├── description_pattern ("apple", "venmo")
├── amount (15.89, 10.59)
├── tolerance (0.01)
├── short_desc ("hbo", "netflix")
├── category_id (FK → categories)
├── notes
└── created_at

budgets
├── id (PK, auto-increment)
├── category_id (FK → categories)
├── month ("2025-01")
├── amount
└── created_at
    Unique: (category_id, month)

notification_log
├── id (PK, auto-increment)
├── transaction_id (FK → transactions)
├── email_message_id
├── sent_at
├── replied_at
└── reply_category
```

### Key Design Decisions

- **`short_desc` is unique across ALL categories** (parents and children). This is the canonical identifier used everywhere.
- **`predicted_category_id` vs `category_id`**: Separation lets you track what the AI suggested vs. what you confirmed. Useful for improving accuracy.
- **Three status values**: `pending_review` (needs input), `confirmed` (manually reviewed), `auto_confirmed` (merchant mapping or amount rule handled it).
- **`plaid_cursor`**: Plaid's transaction sync uses cursor-based pagination. Subsequent syncs only fetch new/changed transactions — not the full history.
- **Fernet encryption**: Plaid access tokens are encrypted at rest in SQLite using a key from `.env`.

---

## Categorization Engine (Priority Cascade)

Each tier is checked in order. Once a match is found, processing stops — no overwrites.

```
New transaction arrives (Plaid sync or archive import)
        │
        ▼
  ┌─────────────────────────┐
  │  TIER 1: Amount Rules   │   description pattern + exact amount
  │  (Apple/Venmo)          │   "APPLE" + $15.89 → hbo
  └──────────┬──────────────┘
             │
        Match? ──YES──→ auto_confirmed
             │
             NO
             │
  ┌─────────────────────────┐
  │  TIER 2: Merchant Map   │   description against merchant_patterns
  │  (200+ patterns)        │   "SAFEWAY" → groceries
  └──────────┬──────────────┘
             │
        Match? ──YES──→ confidence ≥ 3? → auto_confirmed
             │                          → pending_review
             NO
             │
  ┌─────────────────────────┐
  │  TIER 3: Claude API     │   Few-shot with cached examples
  │  (not yet active)       │   from categorization history
  └──────────┬──────────────┘
             │
             ▼
      predicted_category set
      status = "pending_review"
```

### Learning Loop

Every time you confirm a category in the Review Queue, the merchant_mapping confidence increments. After 3 confirmations, that merchant is auto-categorized forever. AI costs converge toward zero as the system learns your patterns.

---

## Category Taxonomy

Two-level hierarchy: parent categories (Category_2) with child subcategories (Short_Desc).

**Parent categories**: Housing, Transportation, Food, Insurance, Utilities, Medical, Government, Savings, Personal_Spending, Recreation_Entertainment, Travel, Misc, People, Payment_and_Interest, Income, Balance

**Example subcategories**:
- Food → groceries, fast_food, restaurant, coffee, work_lunch, food_delivery
- Recreation_Entertainment → spotify, netflix, hulu, concerts, live_nba, movies, tennis
- People → don, jayelin, tahjei, sharon, vincent, family
- Travel → Hawaii, GT_China, Kentucky, Sydney, air_travel, airport

---

## Archive Import

Historical data (2021–2024) was imported from Excel archives using `scripts/import_all_archives.py`. This was a one-time operation.

### Source Files (in `Budget/Archive/`)

| Year | File | Format | Notes |
|------|------|--------|-------|
| 2021 | `Budget 2021 Final.xlsx` | Multi-sheet (per account) | Different taxonomy: "Specific Category" / "Secondary Category" instead of Short_Desc / Category_2. Mapped via `LEGACY_CATEGORY_MAP` and `LEGACY_SHORT_DESC_MAP`. |
| 2022 | `Budget 2022_Final.xlsx` | Multi-sheet (per account) | Standard taxonomy. Includes Discover, Wells Fargo, Care Credit, Best Buy. |
| 2023 | `Curated_Bills.xlsx` | Single sheet (Discover) | Standard taxonomy. Discover only. |
| 2024 | `All_Bills.xlsx` | Single sheet with Account column | Standard taxonomy. All 4 accounts. |

### Data Split

- **2021–2024**: Sourced from Excel archives (4,631 transactions)
- **2025–2026**: Sourced exclusively from Plaid (`days_requested=730` on initial connection)
- No overlap — archive import clears transactions and resets Plaid cursors before importing

---

## Plaid Integration

### Connection Flow

1. User clicks "Connect" on the Accounts page
2. React Plaid Link widget opens with OAuth support
3. User authenticates with their bank
4. Plaid returns a public token → backend exchanges it for an access token
5. Access token is Fernet-encrypted and stored in SQLite
6. Initial sync pulls up to 2 years of history (`days_requested=730`)
7. Subsequent syncs use cursor-based pagination (only new/changed transactions)

### Sync Modes

- **In-app**: APScheduler runs sync every 60 minutes while the backend is running
- **Daemon**: LaunchAgent runs `backend.sync_daemon` every 12 hours independently of the app
- **Manual**: Click "Sync Now" on the Accounts page

### Handling Plaid Quirks

- **Re-authentication**: Banks occasionally require re-auth. The app detects this and shows a reconnect banner.
- **Pending charges**: Tracked with `is_pending` flag and updated when they post.
- **OAuth (Wells Fargo)**: Supported via redirect flow in Plaid Link.
- **Deduplication**: `plaid_transaction_id` is unique — prevents double-imports even if the same webhook fires twice.

---

## Git Database Backup

### Setup (One-Time)

```bash
# Run the setup script (repo already created at github.com/seanlewis08/budget-app-data)
bash scripts/setup-db-backup.sh
```

This initializes a Git repo at `~/BudgetApp/`, commits `budget.db`, and pushes to the private GitHub repo.

### Automatic Backups

After every Plaid sync (both in-app and daemon), the sync daemon:
1. Stages `budget.db`
2. Creates a commit with a timestamp, transaction count, and file size
3. Pushes to `origin/main`

### Manual Backup

```bash
cd ~/BudgetApp && git add budget.db && git commit -m "manual backup" && git push
```

---

## API Endpoints

All endpoints are documented at `http://localhost:8000/docs` (Swagger UI).

### Key Routes

| Prefix | Router | Purpose |
|--------|--------|---------|
| `/api/transactions/` | transactions.py | CRUD, filtering by year/account/status/search, review, bulk review, spending-by-category, monthly-trend, available years |
| `/api/categories/` | categories.py | Category taxonomy CRUD |
| `/api/accounts/` | accounts.py | Account management, Plaid Link token, token exchange, sync trigger, balance fetch |
| `/api/budgets/` | budgets.py | Budget target CRUD |
| `/api/import/` | import_csv.py | CSV file upload and import |
| `/api/archive/` | archive.py | Archive Excel import |
| `/api/notifications/` | notifications.py | Email notification scaffold |
| `/health` | main.py | Health check (used by Electron) |
| `/api/stats` | main.py | Quick dashboard stats (total, pending, confirmed) |

---

## Running the App

### Prerequisites

- Python 3.10+ (managed via `uv`)
- Node.js 18+
- Plaid API keys in `.env`
- Claude API key in `.env` (for future Tier 3 categorization)
- Fernet encryption key in `.env`

### Development

```bash
# Backend (from project root)
uv run uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm run dev

# Open http://localhost:5173 in browser
```

### Environment Variables (`.env`)

```
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_ENV=development        # "sandbox" or "development" (production uses development)
ANTHROPIC_API_KEY=...
ENCRYPTION_KEY=...           # Fernet key for Plaid token encryption
```

### Sync Daemon (LaunchAgent)

```bash
# Create logs directory
mkdir -p ~/BudgetApp/logs

# Install the LaunchAgent
cp com.seanlewis.budgetapp.sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist

# Check logs
cat ~/BudgetApp/logs/sync-stdout.log

# Uninstall
launchctl unload ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist
```

### Manual Sync

```bash
# Sync all accounts + backup
uv run python3 -m backend.sync_daemon

# Sync without Git backup
uv run python3 -m backend.sync_daemon --no-backup

# Run continuously (every 12 hours)
uv run python3 -m backend.sync_daemon --loop
```

---

## Cost Summary

| Service | Monthly Cost |
|---------|-------------|
| Everything runs locally | Free |
| Plaid (bank connections) | Free tier / ~$5 |
| Claude API (Tier 3 categorization) | ~$0.02 |
| GitHub (private repo for backups) | Free |
| **Total** | **~$0–5/month** |

---

## Future Enhancements

1. **Email Notifications** — Categorize transactions via email reply without opening the dashboard
2. **Claude AI Tier 3** — Wire up few-shot categorization for unknown merchants
3. **Fine-Tuned Model (Tier 4)** — Train a custom model once 3,000+ labeled examples exist
4. **Electron Packaging** — Bundle as `.dmg`/`.exe` installer with PyInstaller
5. **Cloudflare Tunnel** — Real-time webhook delivery from Plaid (currently using polling)
6. **WhatsApp Notifications** — Snappier mobile categorization experience
7. **Self-Hosted Cloud Server** — Run the app on a personal server for remote access
