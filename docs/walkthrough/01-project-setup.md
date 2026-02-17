# Part 1 — Project Setup & Foundation

Welcome to the Budget App walkthrough. Over these seven parts, you'll build a complete personal finance tracker from scratch — one that runs entirely on your own computer, categorizes transactions with AI, syncs with your real bank accounts, and tracks your investments. No cloud services store your data; everything lives in a local SQLite database.

This first part gets the foundation in place: the project structure, all the dependencies, the development environment, and a working skeleton you can launch and see running in your browser.

---

## 1.1 What We're Building

Before we write any code, let's understand what the finished app looks like. Budget App is a desktop application with three layers:

**The backend** is a Python web server (FastAPI) that handles all the business logic. It talks to your bank through Plaid, categorizes transactions using Claude AI, and stores everything in a SQLite database. It runs on `localhost:8000` and exposes a REST API.

**The frontend** is a React single-page application. It's the dashboard you interact with — charts, tables, a review queue for categorizing transactions, budget tracking, and more. During development it runs on `localhost:5173` with hot reloading.

**The desktop shell** is Electron, which wraps both of these into a native macOS or Windows application. When you distribute the app, users double-click an icon and the whole thing just works — they never see a terminal or a browser.

Here's how data flows through the system:

```
Bank Accounts (via Plaid API)
        ↓
  FastAPI Backend
        ↓
  3-Tier Categorization Engine
    1. Amount Rules    — exact match on dollar amounts
    2. Merchant Maps   — pattern matching on descriptions
    3. Claude AI       — intelligent fallback for unknowns
        ↓
  SQLite Database (~/BudgetApp/budget.db)
        ↓
  React Frontend (charts, review queue, budgets)
        ↓
  Electron Window (native desktop app)
```

---

## 1.2 Repository Structure

Create the project directory with this layout:

```
budget-app/
  backend/
    __init__.py
    routers/           # API endpoint handlers
      __init__.py
    services/          # Business logic (Plaid, AI, sync)
      __init__.py
      csv_parsers/     # Bank-specific CSV format handlers
        __init__.py
  electron/            # Desktop shell (main process, backend manager)
  frontend/            # React app (Vite)
  scripts/             # Utility scripts
  docs/                # Website and walkthrough
  .env                 # Your API keys (never committed)
  .env.example         # Template for .env
  .gitignore
  start.sh             # One-command dev launcher
  pyproject.toml       # Python dependencies
  package.json         # Node/Electron dependencies
```

Set it up:

```bash
mkdir -p budget-app/{backend/{routers,services/csv_parsers},electron,frontend,scripts,docs}
touch budget-app/backend/__init__.py
touch budget-app/backend/routers/__init__.py
touch budget-app/backend/services/__init__.py
touch budget-app/backend/services/csv_parsers/__init__.py
cd budget-app
git init
```

The separation matters. The `backend/` directory is pure Python — it can run independently without Node or Electron. The `frontend/` directory is pure React — it can run in a browser without Electron. The `electron/` directory ties them together into a desktop app. This separation makes development much easier because you can work on any layer independently.

---

## 1.3 Python Dependencies (`pyproject.toml`)

We use [uv](https://docs.astral.sh/uv/) as the Python package manager. It's dramatically faster than pip and handles virtual environments automatically. Create `pyproject.toml` at the project root:

```toml
[project]
name = "budget-app"
version = "0.1.0"
description = "Personal finance tracker with AI-powered categorization"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115.6",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy>=2.0.36",
    "pydantic>=2.10.4",
    "python-dotenv>=1.0.1",
    "anthropic>=0.42.0",
    "pandas>=2.2.3",
    "openpyxl>=3.1.5",
    "python-multipart>=0.0.18",
    "plaid-python>=27.0.0",
    "aiofiles>=24.1.0",
    "cryptography>=44.0.0",
    "apscheduler>=3.10.4",
    "yfinance>=0.2.36",
]

[project.optional-dependencies]
build = [
    "pyinstaller>=6.11.1",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
]
```

Here's why each dependency is needed:

**Web framework and server:** `fastapi` is a modern Python web framework that gives you automatic API documentation, request validation, and dependency injection. `uvicorn` is the ASGI server that actually runs FastAPI. Together they're the backbone of the backend.

**Database:** `sqlalchemy` is the ORM (Object-Relational Mapper) that lets you define database tables as Python classes and query them with Python code instead of raw SQL. We use it with SQLite, which stores the entire database in a single file — no database server needed.

**Validation:** `pydantic` handles request/response validation. FastAPI uses it under the hood, so when someone sends a malformed request, they get a clear error message instead of a crash.

**Configuration:** `python-dotenv` loads API keys and settings from a `.env` file into environment variables, keeping secrets out of your code.

**AI:** `anthropic` is the official Claude SDK. We use it for transaction categorization (Tier 3) and financial insights.

**Data handling:** `pandas` and `openpyxl` handle CSV and Excel file imports. `python-multipart` enables file upload support in FastAPI.

**Banking:** `plaid-python` is the official Plaid SDK for connecting to bank accounts, fetching transactions, and getting balances.

**Security:** `cryptography` provides Fernet symmetric encryption. We use it to encrypt Plaid access tokens before storing them in the database — if someone gets your database file, they can't access your bank without the encryption key.

**Background jobs:** `apscheduler` runs periodic tasks like syncing transactions every 4 hours and refreshing stock prices during market hours.

**Investments:** `yfinance` fetches live stock prices from Yahoo Finance.

Install everything:

```bash
uv sync
```

---

## 1.4 Frontend Dependencies

Scaffold the React frontend with Vite:

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
```

Then add the runtime libraries we'll need:

```bash
npm install react-router-dom recharts lucide-react react-plaid-link
```

**`react-router-dom`** handles client-side navigation. Instead of full page reloads, clicking a sidebar link instantly swaps the main content area. We'll have 13+ routes — spending, budgets, accounts, investments, insights, and more.

**`recharts`** is a charting library built specifically for React. We use it for spending pie charts, monthly trend bar charts, cash flow line charts, and budget progress bars.

**`lucide-react`** provides clean, consistent icons. Every button, status badge, and navigation link uses a Lucide icon.

**`react-plaid-link`** is the official React wrapper for Plaid Link — the bank connection widget. When users click "Link Bank," this library opens a secure modal where they can log into their bank. Plaid handles the authentication, and we get back a token we can use to fetch their transactions.

Your `frontend/package.json` should look like this:

```json
{
  "name": "budget-app-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "recharts": "^2.13.3",
    "lucide-react": "^0.460.0",
    "react-plaid-link": "^3.5.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^6.0.3"
  }
}
```

---

## 1.5 Vite Configuration

During development, the React dev server and the FastAPI backend run on different ports. The frontend is on 5173, the backend on 8000. When the frontend calls `fetch('/api/transactions')`, that request needs to reach the backend — but by default, the browser sends it to port 5173 (where Vite is running), not port 8000.

Vite's proxy solves this. Create `frontend/vite.config.js`:

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
```

Any request that starts with `/api` or `/health` gets forwarded to the FastAPI backend. This means the frontend code can always use relative URLs like `/api/transactions` regardless of whether it's running in development (Vite proxy) or production (Electron serving everything from the same origin).

---

## 1.6 Environment Variables

Your API keys need to live somewhere, but they should never be committed to git. Create `.env.example` as a template that you *do* commit:

```bash
# Budget App Environment Variables
# Copy this file to .env and fill in your values

# Anthropic API Key (for Claude AI categorization and insights)
# Get yours at: https://console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Plaid (automated bank syncing)
# Sign up at: https://dashboard.plaid.com
PLAID_CLIENT_ID=
PLAID_SECRET=                  # Sandbox secret
PLAID_PRODUCTION_SECRET=       # Production secret
PLAID_ENV=sandbox              # sandbox, development, or production

# Encryption key for Plaid tokens (auto-generated on first run if empty)
PLAID_TOKEN_ENCRYPTION_KEY=
```

Copy it to create your actual `.env`:

```bash
cp .env.example .env
# Edit .env with your API keys
```

A note about the Settings page: later in Part 5, we'll build a Settings page in the UI where you can enter these keys through the app itself. The Settings page saves credentials to the database, which means you don't *need* a `.env` file at all in production. But `.env` is still useful during development because it lets you set keys before the database even exists.

Add `.env` to `.gitignore` so it never gets committed:

```
# .gitignore
.env
__pycache__/
*.pyc
node_modules/
frontend/dist/
*.egg-info/
.venv/
dist/
build/
*.db
```

---

## 1.7 The Data Directory

The app stores its data outside the project directory, in `~/BudgetApp/`. This is a deliberate choice — when you update the app or rebuild it, the project directory changes but your data stays safe. Here's what lives there:

```
~/BudgetApp/
  budget.db            # Main database (transactions, accounts, categories)
  investments.db       # Investment portfolio database
  .env                 # Optional: API keys (loaded before CWD/.env)
  .encryption_key      # Fernet key for Plaid token encryption
  logs/
    sync.log           # Background sync output
```

This directory is created automatically by the database module (Part 2), but you can create it now:

```bash
mkdir -p ~/BudgetApp/logs
```

Why two databases? The main `budget.db` handles everyday finances — transactions, accounts, categories, budgets. The `investments.db` handles portfolio tracking — holdings, securities, investment transactions. Keeping them separate means you could use the budgeting features without investment tracking, or vice versa. It also keeps the main database smaller and faster for the operations that happen most often.

---

## 1.8 Development Launcher (`start.sh`)

During development, you need to start three things: the Python backend, the React dev server, and the Electron window. The `start.sh` script does all three with a single command and tears them all down cleanly when you're done:

```bash
#!/bin/bash
# Budget App — One-click launcher for development
# Starts backend (FastAPI) + frontend (Vite) + Electron window

cd "$(dirname "$0")"

cleanup() {
  echo "Shutting down..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  wait 2>/dev/null
  echo "Done."
  exit 0
}
trap cleanup INT TERM EXIT

# Start backend
echo "Starting backend..."
uv run uvicorn backend.main:app --port 8000 --reload &
BACKEND_PID=$!

# Start frontend (run in subshell so cd doesn't affect parent)
echo "Starting frontend..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# Wait for both to be ready
echo "Waiting for services..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "  Backend ready"
    break
  fi
  sleep 1
done

for i in $(seq 1 30); do
  if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "  Frontend ready"
    break
  fi
  sleep 1
done

# Launch Electron
echo "Launching app..."
NODE_ENV=development npx electron .

# Electron closed — cleanup runs via trap
```

Make it executable:

```bash
chmod +x start.sh
```

The `trap` command is the key detail. When you close the Electron window or press Ctrl+C, the `cleanup` function runs and kills both background processes. Without it, you'd have orphaned uvicorn and Vite processes running until you manually find and kill them.

The `--reload` flag on uvicorn means the backend automatically restarts whenever you save a Python file. Vite has hot module replacement built in, so React changes appear instantly in the browser. This makes the development loop very fast — save a file, see the result immediately.

---

## 1.9 Minimal Backend Skeleton

Let's verify everything works with a bare-bones FastAPI app. Create `backend/main.py`:

```python
"""Budget App — FastAPI Backend"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Budget App",
    description="Personal finance tracker with AI-powered categorization",
    version="0.1.0",
)

# CORS allows the frontend (on a different port) to call the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}
```

CORS (Cross-Origin Resource Sharing) is a browser security feature. Without the CORS middleware, the browser would block the frontend from calling the backend because they're on different ports. The middleware tells the browser "yes, requests from localhost:5173 are allowed."

Test it:

```bash
uv run uvicorn backend.main:app --port 8000 --reload
# In another terminal:
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0"}
```

You can also visit `http://localhost:8000/docs` in your browser to see the auto-generated API documentation. FastAPI creates this from your endpoint definitions — as we add more routes, this page becomes a complete, interactive reference.

---

## 1.10 Minimal Frontend Skeleton

Replace `frontend/src/App.jsx` with a simple placeholder:

```jsx
export default function App() {
  return (
    <div style={{ padding: 40 }}>
      <h1>Budget App</h1>
      <p>Personal Finance Tracker</p>
    </div>
  )
}
```

And `frontend/src/main.jsx`:

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

Test it:

```bash
cd frontend && npm run dev
# Open http://localhost:5173 — you should see "Budget App"
```

At this point you have a working full-stack skeleton. The backend serves a health endpoint, the frontend shows a page, and the Vite proxy connects them. Everything else we build from here is just adding features to this foundation.

---

## What's Next

With the project scaffolded, Part 2 dives into the database layer. We'll set up SQLite with SQLAlchemy, define all the ORM models (accounts, transactions, categories, budgets, and more), wire up the lifespan management that initializes everything on startup, and build a lightweight migration system for evolving the schema over time.

→ [Part 2: Database Models & Backend Core](02-database-and-models.md)
