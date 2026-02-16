# Part 7 — Electron Desktop App & Deployment

This part covers wrapping the FastAPI backend and React frontend into a native desktop application using Electron, and the build/packaging process for distribution.

---

## 7.1 Architecture

In production, the Electron app bundles everything into a single package:

```
Budget App.app
  └── Contents/
      └── Resources/
          ├── backend/
          │   └── budget-app-backend  (PyInstaller binary)
          ├── frontend/
          │   └── dist/               (Vite build output)
          └── app/
              ├── electron/
              │   ├── main.js
              │   ├── backend-manager.js
              │   └── preload.js
              └── package.json
```

In development, the three processes run separately:

- Backend: `uv run uvicorn backend.main:app --port 8000 --reload`
- Frontend: `cd frontend && npm run dev` (Vite dev server on port 5173)
- Electron: `NODE_ENV=development npx electron .` (loads from Vite)

The `start.sh` script handles all three (see Part 1).

---

## 7.2 Electron Main Process (`electron/main.js`)

The main process creates the browser window and manages the backend lifecycle:

```javascript
const { app, BrowserWindow, shell } = require('electron')
const path = require('path')
const { startBackend, stopBackend, isBackendReady } = require('./backend-manager')

app.setName('Budget App')

let mainWindow = null
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'Budget App',
    icon: path.join(__dirname, 'icons', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    backgroundColor: '#0f1117',
    show: false,
  })

  mainWindow.once('ready-to-show', () => mainWindow.show())

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'))
  }

  // Open external links in the default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}
```

Key design decisions:

- **`show: false` + `ready-to-show`**: Prevents the white flash while the app loads
- **`backgroundColor: '#0f1117'`**: Matches the dark theme so the window background blends seamlessly
- **`titleBarStyle: 'hiddenInset'`**: Uses macOS's native title bar with the traffic lights inset (cleaner look)
- **`contextIsolation: true`**: Security best practice — prevents the renderer from accessing Node.js APIs directly
- **External links**: Opens any `<a target="_blank">` links in the system browser instead of a new Electron window

### Startup Sequence

```javascript
async function startup() {
  if (isDev) {
    // Dev mode: backend already running via start.sh
    // Just wait for it to respond
    let retries = 0
    while (retries < 60) {
      if (await isBackendReady()) break
      await new Promise(r => setTimeout(r, 500))
      retries++
    }
  } else {
    // Production: start the bundled backend
    startBackend()
    let retries = 0
    while (retries < 60) {
      if (await isBackendReady()) break
      await new Promise(r => setTimeout(r, 500))
      retries++
    }
  }
  createWindow()
}

app.whenReady().then(startup)
```

The startup polls the `/health` endpoint every 500ms for up to 30 seconds. In development, `start.sh` has already started the backend. In production, the backend-manager starts the PyInstaller binary.

### Shutdown

```javascript
app.on('window-all-closed', () => {
  if (!isDev) stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (!isDev) stopBackend()
})
```

In development, the backend is managed by `start.sh`, so Electron doesn't touch it. In production, Electron stops the backend process on quit.

---

## 7.3 Backend Manager (`electron/backend-manager.js`)

Manages the Python backend process lifecycle:

```javascript
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')

let backendProcess = null
const BACKEND_PORT = 8000

function getBackendPath() {
  // Production: PyInstaller bundle inside app resources
  const ext = process.platform === 'win32' ? '.exe' : ''
  return path.join(
    process.resourcesPath,
    'backend',
    `budget-app-backend${ext}`
  )
}

function startBackend() {
  if (backendProcess) return

  const backendPath = getBackendPath()
  backendProcess = spawn(backendPath, [], {
    env: {
      ...process.env,
      BUDGET_APP_PORT: String(BACKEND_PORT),
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  })

  backendProcess.stdout.on('data', (data) =>
    console.log(`[backend] ${data.toString().trim()}`)
  )
  backendProcess.stderr.on('data', (data) =>
    console.error(`[backend] ${data.toString().trim()}`)
  )
  backendProcess.on('close', (code) => {
    console.log(`Backend exited with code ${code}`)
    backendProcess = null
  })
}

function stopBackend() {
  if (!backendProcess) return
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', backendProcess.pid, '/f', '/t'])
  } else {
    backendProcess.kill('SIGTERM')
  }
  backendProcess = null
}

function isBackendReady() {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${BACKEND_PORT}/health`, (res) =>
      resolve(res.statusCode === 200)
    )
    req.on('error', () => resolve(false))
    req.setTimeout(2000, () => { req.destroy(); resolve(false) })
  })
}
```

---

## 7.4 Preload Script (`electron/preload.js`)

The preload script bridges the secure renderer and Node.js:

```javascript
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getVersion: () => process.env.npm_package_version || '0.1.0',
  getPlatform: () => process.platform,
})
```

This exposes a minimal API to the renderer. The app currently uses it lightly, but it's the correct pattern for any future Electron ↔ renderer communication (e.g., native file dialogs, system notifications).

---

## 7.5 Building the Python Backend

PyInstaller bundles the Python backend into a standalone binary that doesn't require Python to be installed:

```bash
# Install PyInstaller (in the build optional dependencies)
uv pip install pyinstaller

# Build the backend binary
pyinstaller \
  --name budget-app-backend \
  --onefile \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.lifespan.on \
  --add-data "backend:backend" \
  --add-data ".env:.env" \
  backend_entry.py
```

The entry point (`backend_entry.py`) starts uvicorn programmatically:

```python
#!/usr/bin/env python3
"""Entry point for PyInstaller-bundled backend."""
import uvicorn
import os

if __name__ == "__main__":
    port = int(os.environ.get("BUDGET_APP_PORT", 8000))
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port)
```

The `--hidden-import` flags are necessary because PyInstaller's dependency analysis misses some uvicorn internals that are loaded dynamically.

---

## 7.6 Building the Electron App

### Frontend Build

First, build the React frontend for production:

```bash
cd frontend
npm run build
# Output: frontend/dist/
```

The production build generates static files that Electron loads directly via `loadFile()` (no dev server needed).

### Electron Packaging

The `package.json` at the project root configures electron-builder:

```json
{
  "name": "budget-app",
  "version": "0.1.0",
  "main": "electron/main.js",
  "build": {
    "appId": "com.seanlewis.budgetapp",
    "productName": "Budget App",
    "directories": {
      "output": "release"
    },
    "files": [
      "electron/**/*",
      "frontend/dist/**/*",
      "package.json"
    ],
    "extraResources": [
      {
        "from": "dist/budget-app-backend",
        "to": "backend/budget-app-backend"
      }
    ],
    "mac": {
      "target": "dmg",
      "category": "public.app-category.finance",
      "icon": "electron/icons/icon.icns"
    },
    "win": {
      "target": "nsis",
      "icon": "electron/icons/icon.ico"
    }
  }
}
```

Build the distributable:

```bash
# After building both the Python backend and React frontend
npx electron-builder --mac    # DMG for macOS
npx electron-builder --win    # NSIS installer for Windows
```

The output goes to the `release/` directory.

### Build Pipeline Summary

```
1. uv sync                           # Install Python deps
2. cd frontend && npm install         # Install Node deps
3. cd frontend && npm run build       # Build React → frontend/dist/
4. pyinstaller ... backend_entry.py   # Bundle Python → dist/budget-app-backend
5. npx electron-builder --mac         # Package everything → release/Budget App.dmg
```

---

## 7.7 Production vs. Development

| Aspect | Development | Production |
|--------|-------------|------------|
| Backend | `uv run uvicorn ... --reload` | PyInstaller binary |
| Frontend | Vite dev server (HMR) | Static files from `frontend/dist/` |
| API proxy | Vite proxy (`/api` → `:8000`) | Direct localhost:8000 |
| Electron | `npx electron .` | Packaged `.app` / `.exe` |
| Window URL | `http://localhost:5173` | `file:///frontend/dist/index.html` |
| Backend lifecycle | Managed by `start.sh` | Managed by `backend-manager.js` |

---

## 7.8 Project Summary

When fully assembled, the Budget App has:

- **4 bank accounts** connected via Plaid (Discover, SoFi Checking, SoFi Savings, Wells Fargo)
- **3-tier categorization** with 18 parent categories, 80+ subcategories, and 50+ merchant mappings
- **13+ frontend pages**: Review Queue, Spending, Cash Flow, Recurring, Budget, Accounts, Investments, Insights, Data, Categories, Settings, Deleted Transactions, Sync History
- **AI-powered features**: Transaction categorization (Claude Haiku), financial insights (Claude Sonnet + Haiku chat)
- **Investment tracking**: Plaid + yfinance for portfolio analysis with daily snapshots
- **Background sync**: APScheduler (in-app) + LaunchAgent daemon (background) + Git backup
- **Audit trail**: SyncLog, DeletedTransactions, and detailed logging throughout

The data lives entirely on the user's machine in `~/BudgetApp/` — no cloud services required beyond the Plaid and Anthropic APIs.

---

## Quick Reference: All API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Backend health check |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/transactions` | List transactions (with filters) |
| GET | `/api/transactions/pending` | Pending review queue |
| POST | `/api/transactions/{id}/review` | Confirm category |
| POST | `/api/transactions/commit` | Commit staged transactions |
| DELETE | `/api/transactions/{id}` | Soft-delete transaction |
| POST | `/api/transactions/bulk-delete` | Bulk soft-delete |
| POST | `/api/transactions/bulk-categorize` | Bulk categorize |
| GET | `/api/transactions/spending-by-category` | Monthly spending breakdown |
| GET | `/api/transactions/monthly-trend` | Monthly trend data |
| GET | `/api/transactions/cash-flow` | Cash flow analysis |
| GET | `/api/transactions/recurring-monitor` | Recurring charges grid |
| GET | `/api/transactions/years` | Available years |
| GET | `/api/transactions/deleted` | Deleted transactions log |
| POST | `/api/transactions/deleted/{id}/restore` | Restore deleted |
| DELETE | `/api/transactions/deleted/{id}` | Purge from log |
| DELETE | `/api/transactions/deleted` | Purge all from log |
| GET | `/api/categories` | List categories |
| GET | `/api/categories/tree` | Category hierarchy |
| POST | `/api/categories` | Create category |
| PUT | `/api/categories/{id}` | Update category |
| POST | `/api/categories/{id}/merge` | Merge categories |
| DELETE | `/api/categories/{id}` | Delete category |
| GET | `/api/budgets` | List budgets for month |
| POST | `/api/budgets` | Create/update budget |
| GET | `/api/accounts` | List accounts |
| GET | `/api/accounts/sync-history` | Sync audit log |
| POST | `/api/accounts/link/create` | Plaid link token |
| POST | `/api/accounts/link/exchange` | Exchange public token |
| POST | `/api/accounts/{id}/sync` | Sync single account |
| POST | `/api/accounts/sync-all` | Sync all accounts |
| POST | `/api/accounts/{id}/disconnect` | Disconnect account |
| POST | `/api/import` | CSV import |
| POST | `/api/import/auto-detect` | Detect bank format |
| GET | `/api/archive/scan` | Scan for archives |
| POST | `/api/archive/import` | Import archive |
| GET | `/api/archive/coverage` | Data coverage |
| GET | `/api/investments/summary` | Portfolio summary |
| GET | `/api/investments/holdings` | All holdings |
| GET | `/api/investments/performance` | Performance chart data |
| GET | `/api/investments/allocation` | Asset allocation |
| GET | `/api/investments/transactions` | Investment transactions |
| POST | `/api/investments/link-token` | Investment link token |
| POST | `/api/investments/link/exchange` | Exchange investment token |
| POST | `/api/investments/refresh-prices` | Refresh stock prices |
| GET | `/api/insights/snapshot` | Financial snapshot |
| POST | `/api/insights/analyze` | AI analysis (SSE stream) |
| POST | `/api/insights/chat` | Follow-up chat (SSE stream) |

---

← [Back to Index](README.md)
