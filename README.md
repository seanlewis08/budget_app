# Budget App

Personal finance tracker with AI-powered transaction categorization. Runs locally on your machine as a desktop app.

## Features

- **AI Categorization**: Priority cascade system — amount rules, merchant mappings, then Claude API fallback
- **Review Queue**: Confirm or change predicted categories with one click
- **Spending Dashboard**: Charts, trends, and category breakdowns
- **Budget Tracking**: Set monthly targets and track progress
- **CSV Import**: Supports Discover, SoFi, and Wells Fargo formats
- **Cross-Platform**: macOS (.dmg) and Windows (.exe) installers

## Quick Start (Development)

### Prerequisites

- Python 3.10+
- Node.js 22+
- npm
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Setup

```bash
# Clone the repo
git clone https://github.com/seanlewis08/budget_app.git
cd budget_app

# Install Python dependencies
uv sync

# Install Node dependencies
npm install

# Copy environment file and add your API keys
cp .env.example .env

# Start the app (backend + frontend)
npm run dev
```

The app opens at `http://localhost:5173` with the API at `http://localhost:8000/docs`.

### Running Backend Only

```bash
npm run dev:backend
# API docs at http://localhost:8000/docs
```

### Running Frontend Only

```bash
npm run dev:frontend
# Dashboard at http://localhost:5173
```

## Plaid Bank Syncing

The app connects to your bank accounts via Plaid (production mode) and automatically syncs transactions.

- **Supported banks**: Discover, SoFi (Checking + Savings), Wells Fargo
- **Sync schedule**: Every 12 hours via macOS LaunchAgent, plus on every laptop wake/login
- **History**: Requests up to 730 days (2 years) of data on new connections
- **OAuth**: Supported for banks that require it (redirect URI: `http://localhost:5173/oauth-callback`)

### Plaid Environment Variables

```
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_sandbox_secret
PLAID_PRODUCTION_SECRET=your_production_secret
PLAID_ENV=production
```

## Background Sync Daemon

A standalone sync script runs independently of the desktop app, keeping your database up to date even when the app is closed.

### How It Works

- `backend/sync_daemon.py` connects to Plaid, pulls new transactions, categorizes them, and writes to `~/BudgetApp/budget.db`
- Runs as a macOS LaunchAgent (`com.seanlewis.budgetapp.sync.plist`)
- **Triggers**: On every login/wake + every 12 hours
- **Logs**: `~/BudgetApp/logs/sync.log`

### Activate the Daemon (one-time)

```bash
mkdir -p ~/BudgetApp/logs
cp com.seanlewis.budgetapp.sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist
```

### Daemon Commands

```bash
# Check if running
launchctl list | grep budgetapp

# Stop the daemon
launchctl unload ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist

# Restart (after editing the plist)
launchctl unload ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist
launchctl load ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist

# View sync logs
cat ~/BudgetApp/logs/sync.log

# Run sync manually (without the daemon)
cd ~/DataspellProjects/budget-app
uv run python3 -m backend.sync_daemon
```

## Database Git Backup

The sync daemon automatically commits `budget.db` to a private Git repo after each sync.

### Setup (one-time)

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
git remote add origin git@github.com:seanlewis08/budget-app-data.git
git add .gitignore budget.db
git commit -m "Initial database backup"
git branch -M main
git push -u origin main
```

After setup, every sync automatically commits and pushes the database with a message like:
`Backup 2026-02-15 09:00 — 1,247 transactions, 4.2 MB`

### Disable Backup

```bash
# Run sync without backup
uv run python3 -m backend.sync_daemon --no-backup
```

## Project Structure

```
budget-app/
├── electron/              # Electron main process (desktop wrapper)
├── backend/               # Python FastAPI (API + categorization engine)
│   ├── routers/           # API endpoints (transactions, accounts, archive, etc.)
│   ├── services/          # Business logic (categorizer, Plaid, CSV parsers, archive importer)
│   └── sync_daemon.py     # Standalone sync + backup script
├── frontend/              # React dashboard (Vite)
│   └── src/pages/         # ReviewQueue, Spending, Budget, Accounts, Data, Categories, Settings
├── scripts/               # Setup scripts (backup, etc.)
├── com.seanlewis.budgetapp.sync.plist  # macOS LaunchAgent config
└── Budget/                # Historical archive data (Excel/CSV, 2021-2025)
```

## Building Desktop App

```bash
# Build everything
npm run build

# Output: dist/ folder with .dmg (Mac) or .exe (Windows) installer
```

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy, SQLite
- **Frontend**: React, Recharts, Vite
- **Desktop**: Electron, electron-builder
- **AI**: Anthropic Claude API (Haiku)
- **Bank Sync**: Plaid API (production)
- **Background Sync**: macOS LaunchAgent + Git backup
- **CI/CD**: GitHub Actions

## Future Enhancements

- **Self-hosted cloud server**: Deploy backend to a personal Linux server for 24/7 syncing and multi-machine access (PostgreSQL, VPN tunneling)
- **Plaid webhooks**: Real-time transaction notifications via Cloudflare Tunnel
- **Email notifications**: Daily/weekly spending summaries
- **Mobile access**: Connect phone to self-hosted API
