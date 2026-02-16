# Part 1 — Project Setup & Foundation

This part covers the repository structure, dependency management, environment configuration, and the development launcher script. By the end, you'll have a runnable skeleton that starts a FastAPI backend, a React frontend, and an Electron window.

---

## 1.1 Repository Structure

Create the top-level directory layout:

```
budget-app/
  backend/
    __init__.py
    routers/
      __init__.py
    services/
      __init__.py
  electron/
  frontend/
  scripts/
  docs/
  .env
  .env.example
  .gitignore
  start.sh
  pyproject.toml
```

```bash
mkdir -p budget-app/{backend/{routers,services},electron,frontend,scripts,docs}
touch budget-app/backend/__init__.py
touch budget-app/backend/routers/__init__.py
touch budget-app/backend/services/__init__.py
cd budget-app
git init
```

---

## 1.2 Python Dependencies (`pyproject.toml`)

We use [uv](https://docs.astral.sh/uv/) as the Python package manager. Create `pyproject.toml` at the project root:

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

Key dependencies and why they're needed:

| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | Web framework and ASGI server |
| `sqlalchemy` | ORM for SQLite database |
| `pydantic` | Request/response validation |
| `python-dotenv` | Load `.env` files |
| `anthropic` | Claude AI SDK for categorization and insights |
| `pandas` + `openpyxl` | CSV/Excel import and data manipulation |
| `python-multipart` | File upload support |
| `plaid-python` | Plaid API SDK for bank account integration |
| `cryptography` | Fernet encryption for Plaid access tokens at rest |
| `apscheduler` | Background job scheduling (sync, price fetching) |
| `yfinance` | Live stock price data for investment tracking |

Install everything:

```bash
uv sync
```

---

## 1.3 Frontend Dependencies

Scaffold the React frontend with Vite:

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
```

Install the runtime dependencies:

```bash
npm install react-router-dom recharts lucide-react react-plaid-link
```

Your `frontend/package.json` should look like:

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

## 1.4 Vite Configuration

Configure Vite to proxy API calls to the FastAPI backend. Create `frontend/vite.config.js`:

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

The proxy configuration is important: during development, the React dev server runs on port 5173 and the FastAPI backend on port 8000. The proxy forwards any request starting with `/api` or `/health` to the backend, so the frontend can use relative URLs like `fetch('/api/transactions')` without hardcoding the backend URL.

---

## 1.5 Environment Variables

Create `.env.example` as a template:

```bash
# Budget App Environment Variables
# Copy this file to .env and fill in your values

# Anthropic API Key (for Claude AI categorization — Tier 3)
# Get yours at: https://console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Plaid (automated bank syncing)
# Sign up at: https://dashboard.plaid.com
PLAID_CLIENT_ID=
PLAID_SECRET=                  # Sandbox secret (from Plaid dashboard)
PLAID_PRODUCTION_SECRET=       # Production secret (from Plaid dashboard)
PLAID_ENV=sandbox              # sandbox, development, or production
PLAID_TOKEN_ENCRYPTION_KEY=    # Auto-generated on first run if empty

# Email Notifications (Phase 3)
# Create a Gmail App Password at: Google Account > Security > App Passwords
EMAIL_ADDRESS=
EMAIL_APP_PASSWORD=
EMAIL_RECIPIENT=

# Cloudflare Tunnel (Phase 2 — webhook delivery)
CLOUDFLARE_TUNNEL_TOKEN=
```

Copy it to create your actual `.env`:

```bash
cp .env.example .env
# Edit .env with your API keys
```

Add `.env` to `.gitignore` so secrets never get committed:

```
# .gitignore
.env
__pycache__/
*.pyc
node_modules/
frontend/dist/
*.egg-info/
.venv/
```

---

## 1.6 Development Launcher (`start.sh`)

The `start.sh` script starts all three services (backend, frontend, Electron) with a single command and tears them all down cleanly on exit:

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

How it works:

1. Starts the FastAPI backend with `uv run uvicorn` (with `--reload` for auto-restart on file changes)
2. Starts the Vite dev server in a subshell
3. Polls both services until they respond (up to 30 seconds each)
4. Launches Electron in development mode
5. When Electron closes (or Ctrl+C), the `trap` handler kills both background processes

---

## 1.7 Data Directory

The app stores its database outside the project directory so it persists across updates and reinstalls:

```
~/BudgetApp/
  budget.db          # Main transaction database
  investments.db     # Investment portfolio database
  logs/
    sync.log         # Sync daemon output
  .encryption_key    # Fernet key for Plaid token encryption
```

This directory is created automatically by the database module (covered in Part 2), but you can create it manually:

```bash
mkdir -p ~/BudgetApp/logs
```

---

## 1.8 Minimal Backend Skeleton

To verify everything works, create a bare-bones FastAPI app. Create `backend/main.py`:

```python
"""Budget App — FastAPI Backend"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Budget App",
    description="Personal finance tracker with AI-powered categorization",
    version="0.1.0",
)

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

Test it:

```bash
uv run uvicorn backend.main:app --port 8000 --reload
# In another terminal:
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0"}
```

---

## 1.9 Minimal Frontend Skeleton

Replace `frontend/src/App.jsx` with a placeholder:

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

---

## What's Next

With the project scaffolded and all dependencies installed, Part 2 covers the SQLite database setup, SQLAlchemy ORM models, and the full FastAPI application skeleton with lifespan management.

→ [Part 2: Database Models & Backend Core](02-database-and-models.md)
