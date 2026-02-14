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

### Setup

```bash
# Clone the repo
git clone https://github.com/seanlewis08/budget_app.git
cd budget_app

# Install Python dependencies
pip install -r backend/requirements.txt

# Install Node dependencies
npm install

# Copy environment file and add your API keys
cp .env.example .env

# Start the app (backend + frontend)
npm run dev
```

The app opens at `http://localhost:3000` with the API at `http://localhost:8000/docs`.

### Running Backend Only

```bash
npm run dev:backend
# API docs at http://localhost:8000/docs
```

### Running Frontend Only

```bash
npm run dev:frontend
# Dashboard at http://localhost:3000
```

## Project Structure

```
budget-app/
├── electron/          # Electron main process (desktop wrapper)
├── backend/           # Python FastAPI (API + categorization engine)
│   ├── routers/       # API endpoints
│   ├── services/      # Business logic (categorizer, CSV parsers)
│   └── scripts/       # Migration & export utilities
├── frontend/          # React dashboard (Vite)
│   └── src/pages/     # ReviewQueue, Spending, Budget, Accounts, Settings
└── .github/workflows/ # CI/CD (build + release)
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
- **CI/CD**: GitHub Actions
