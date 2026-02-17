# Part 7 — Electron Desktop App & Deployment

The previous six parts built a complete web application — a FastAPI backend and a React frontend that communicate over HTTP. This final part wraps them into a native desktop application using Electron, then covers the build and packaging process that produces a distributable `.dmg` file users can install with a double-click.

---

## 7.1 Architecture: Development vs. Production

In development, three processes run side by side: the FastAPI backend (port 8000), the Vite dev server (port 5173), and the Electron window. They're independent processes launched by `start.sh`, and you can restart any one without touching the others. The Vite proxy forwards `/api` requests to the backend.

In production, everything collapses into a single application bundle:

```
Budget App.app
  └── Contents/
      └── Resources/
          ├── backend/
          │   └── budget-app-backend     ← PyInstaller binary
          ├── frontend/
          │   └── dist/                  ← Vite build output
          └── app/
              ├── electron/
              │   ├── main.js
              │   ├── backend-manager.js
              │   └── preload.js
              └── package.json
```

The Electron app launches the PyInstaller binary as a child process, waits for it to respond on `/health`, then opens a browser window pointing at `http://localhost:8000`. The backend serves both the API and the React SPA from the same port — no proxy needed.

Here's how the two modes compare:

| Aspect | Development | Production |
|--------|-------------|------------|
| Backend | `uv run uvicorn ... --reload` | PyInstaller binary |
| Frontend | Vite dev server (HMR) | Static files served by FastAPI |
| API proxy | Vite proxy (`/api` → `:8000`) | Same origin (both on `:8000`) |
| Electron | `npx electron .` | Packaged `.app` / `.exe` |
| Window URL | `http://localhost:5173` | `http://localhost:8000` |
| Backend lifecycle | Managed by `start.sh` | Managed by `backend-manager.js` |

---

## 7.2 Electron Main Process (`electron/main.js`)

The main process is Electron's entry point. It creates the browser window, manages the backend lifecycle, and handles shutdown.

### Creating the Window

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
    mainWindow.loadURL('http://localhost:8000')
  }

  // Open external links in the default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}
```

Several choices here are deliberate:

`show: false` combined with `ready-to-show` prevents the white flash that happens when the window opens before content has loaded. The window stays hidden until the page is ready, then appears instantly.

`backgroundColor: '#0f1117'` matches the app's dark theme. Without this, there's a brief moment between the window appearing and the CSS loading where the background would be white.

`titleBarStyle: 'hiddenInset'` on macOS moves the traffic light buttons (close, minimize, maximize) into the content area instead of sitting in a separate title bar. This gives the app a cleaner, more native feel.

`contextIsolation: true` and `nodeIntegration: false` are security best practices. They prevent the web content from directly accessing Node.js APIs — any communication between the renderer and Node.js must go through the preload script's explicit API.

The `setWindowOpenHandler` catches any `<a target="_blank">` links and opens them in the system browser instead of spawning a new Electron window. When Claude's AI analysis includes links to financial resources, they open in Chrome/Safari rather than a stripped-down Electron window.

### Startup Sequence

The startup waits for the backend before showing any UI:

```javascript
async function startup() {
  if (isDev) {
    // Dev mode: backend already running via start.sh
    console.log('Dev mode — waiting for backend...')
    let retries = 0
    while (retries < 60) {
      if (await isBackendReady()) break
      await new Promise(r => setTimeout(r, 500))
      retries++
    }
  } else {
    // Production: start the bundled backend
    console.log('Starting Python backend...')
    startBackend()
    let retries = 0
    while (retries < 60) {
      if (await isBackendReady()) break
      await new Promise(r => setTimeout(r, 500))
      retries++
    }
    if (retries >= 60) {
      console.error('Backend failed to start within 30 seconds')
    }
  }
  createWindow()
}

app.whenReady().then(startup)
```

The polling loop checks `/health` every 500ms for up to 30 seconds. In development, `start.sh` has already launched the backend — Electron just waits for it to respond. In production, Electron launches the PyInstaller binary first, then polls.

### Shutdown

```javascript
app.on('window-all-closed', () => {
  if (!isDev) stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})

app.on('before-quit', () => {
  if (!isDev) stopBackend()
})
```

On macOS, closing all windows doesn't quit the app (standard Mac behavior). On Windows and Linux, it does. The `activate` event handles the macOS case where the user clicks the Dock icon to reopen the window.

In development, Electron never touches the backend — `start.sh` handles that. In production, Electron sends `SIGTERM` to the backend process on quit.

---

## 7.3 Backend Manager (`electron/backend-manager.js`)

The backend manager handles starting, stopping, and health-checking the Python backend process.

### Killing Stale Processes

A subtle problem: if the app crashes or is force-quit, the backend process might keep running. The next launch would fail with "address already in use." The backend manager handles this preemptively:

```javascript
function killStaleBackend() {
  try {
    if (process.platform === 'win32') {
      const out = execSync(
        `netstat -ano | findstr :${BACKEND_PORT} | findstr LISTENING`,
        { encoding: 'utf8', timeout: 5000 }
      )
      // Parse PIDs and kill them
      ...
    } else {
      // macOS / Linux
      const out = execSync(`lsof -ti:${BACKEND_PORT}`, {
        encoding: 'utf8', timeout: 5000,
      })
      const pids = out.trim().split('\n').filter(Boolean)
      for (const pid of pids) {
        try { process.kill(Number(pid), 'SIGKILL') } catch {}
      }
    }
  } catch {
    // No process on port — expected on clean launch
  }
}
```

This runs before every `startBackend()` call. If port 8000 is already in use, it kills whatever's listening there. The `try/catch` wrapper handles the clean case where nothing is running.

### Starting the Backend

```javascript
function startBackend() {
  if (backendProcess) return

  killStaleBackend()

  if (isDev) {
    // Development: run uvicorn directly
    backendProcess = spawn('uv', [
      'run', 'uvicorn', 'backend.main:app',
      '--port', String(BACKEND_PORT), '--reload',
    ], {
      cwd: path.join(__dirname, '..'),
      env: { ...process.env },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
  } else {
    // Production: run PyInstaller bundle
    const backendPath = path.join(
      process.resourcesPath, 'backend', 'budget-app-backend'
    )
    const frontendDir = path.join(
      process.resourcesPath, 'frontend', 'dist'
    )

    backendProcess = spawn(backendPath, [], {
      env: {
        ...process.env,
        BUDGET_APP_PORT: String(BACKEND_PORT),
        BUDGET_APP_FRONTEND_DIR: frontendDir,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
  }

  backendProcess.stdout.on('data', (data) =>
    console.log(`[backend] ${data.toString().trim()}`)
  )
  backendProcess.stderr.on('data', (data) =>
    console.error(`[backend] ${data.toString().trim()}`)
  )
}
```

In production, Electron passes two environment variables to the backend: `BUDGET_APP_PORT` (which port to listen on) and `BUDGET_APP_FRONTEND_DIR` (where the built React files live). The backend uses these to serve the SPA.

The `stdio: ['pipe', 'pipe', 'pipe']` captures stdout and stderr from the backend. All Python output appears in Electron's console prefixed with `[backend]`, which makes debugging production issues much easier.

### Health Check

```javascript
function isBackendReady() {
  return new Promise((resolve) => {
    const req = http.get(
      `http://localhost:${BACKEND_PORT}/health`,
      (res) => resolve(res.statusCode === 200)
    )
    req.on('error', () => resolve(false))
    req.setTimeout(2000, () => { req.destroy(); resolve(false) })
  })
}
```

A simple HTTP request to `/health`. Returns `true` if the backend responds with 200, `false` for any error or timeout. The startup loop calls this every 500ms.

---

## 7.4 Preload Script (`electron/preload.js`)

The preload script is the secure bridge between the renderer process (your React app) and Node.js:

```javascript
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getVersion: () => process.env.npm_package_version || '0.1.0',
  getPlatform: () => process.platform,
})
```

This exposes a minimal `window.electronAPI` object to the renderer. The app currently uses it lightly — mainly to show the version number in Settings. But it's the correct pattern for any future Electron-to-renderer communication like native file dialogs, system notifications, or menu bar integration.

With `contextIsolation: true`, the renderer can only access what's explicitly exposed through `contextBridge`. It can't import Node.js modules or access the filesystem directly. This matters for a finance app — you don't want a malicious ad in a third-party library to read your database.

---

## 7.5 Serving the Frontend in Production

In development, the Vite dev server serves the React app and proxies API calls. In production, there's no Vite — the backend serves both the API and the frontend from the same server. This is handled in `backend/main.py`:

```python
def _get_frontend_dir() -> Path | None:
    """Locate the React frontend build directory."""
    # Priority 1: BUDGET_APP_FRONTEND_DIR env var (set by Electron)
    env_dir = os.environ.get("BUDGET_APP_FRONTEND_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir() and (p / "index.html").is_file():
            return p

    # Priority 2: search relative to the PyInstaller binary
    if getattr(sys, 'frozen', False):
        exe = Path(sys.executable)
        candidates = [
            exe.parent.parent / "frontend" / "dist",
            exe.parent / "frontend" / "dist",
        ]
        for c in candidates:
            if c.is_dir() and (c / "index.html").is_file():
                return c
        return None

    # Priority 3: development — frontend/dist next to project root
    dev_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dev_path.is_dir():
        return dev_path
    return None
```

Three fallback strategies ensure the frontend is found regardless of where the app is installed. The env var approach is most reliable — Electron always knows its own `resourcesPath` and passes the exact location.

Once found, the frontend is mounted with a SPA catch-all route:

```python
def _setup_frontend_serving(app: FastAPI) -> None:
    frontend_dir = _get_frontend_dir()
    if not frontend_dir or not getattr(sys, 'frozen', False):
        return  # Don't serve frontend in development

    # Mount /assets for JS, CSS, images
    assets_dir = frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)),
                  name="static-assets")

    # Catch-all: non-API GET routes serve index.html (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        file_path = frontend_dir / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))
```

The catch-all is the SPA routing trick: when you navigate to `/spending` or `/insights`, there's no actual `spending.html` file — it's all handled by React Router in the browser. The catch-all serves `index.html` for any path that isn't an API route or a real file, letting React Router take over client-side.

The catch-all only activates in packaged mode (`sys.frozen == True`). In development, Vite handles this, and registering a catch-all GET route would break POST/PUT/DELETE requests by intercepting them.

---

## 7.6 PyInstaller: Bundling Python

PyInstaller analyzes the Python backend's import tree and bundles everything — Python interpreter, all dependencies, and the application code — into a single executable. Users don't need Python installed on their machine.

### The Spec File (`backend/budget-app.spec`)

The spec file is PyInstaller's build configuration. The key sections:

```python
a = Analysis(
    ['run_app.py'],
    pathex=[str(Path.cwd().parent)],
    datas=[
        (certifi_dir, 'certifi'),   # SSL certificates
    ],
    hiddenimports=[
        # Uvicorn internals (loaded dynamically)
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'sqlalchemy.dialects.sqlite',

        # All routers (imported at runtime via main.py)
        'backend.routers.transactions',
        'backend.routers.categories',
        'backend.routers.budgets',
        'backend.routers.import_csv',
        'backend.routers.notifications',
        'backend.routers.accounts',
        'backend.routers.archive',
        'backend.routers.investments',
        'backend.routers.insights',
        'backend.routers.settings',

        # All services
        'backend.services.categorize',
        'backend.services.seed_data',
        'backend.services.plaid_service',
        'backend.services.sync_scheduler',
        'backend.services.financial_advisor',
        'backend.services.price_fetcher',
        'backend.services.archive_importer',

        # CSV parsers
        'backend.services.csv_parsers.discover',
        'backend.services.csv_parsers.sofi',
        'backend.services.csv_parsers.wellsfargo',

        # Infrastructure
        'backend.investments_database',
        'backend.models_investments',
    ],
)
```

**Hidden imports** are the main challenge. PyInstaller discovers dependencies by tracing `import` statements statically, but many Python libraries use dynamic imports (like uvicorn loading protocol handlers, or SQLAlchemy loading dialect drivers). These need to be listed explicitly or the bundled app crashes at runtime with `ModuleNotFoundError`.

**SSL certificates** are bundled via the `datas` section. Without the certifi CA bundle, any HTTPS request (to Plaid, Anthropic, or Yahoo Finance) fails with `CERTIFICATE_VERIFY_FAILED`. The entry point (`run_app.py`) detects the frozen environment and points SSL at the bundled certificates:

```python
if getattr(sys, 'frozen', False):
    _cert_file = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
    if os.path.isfile(_cert_file):
        os.environ.setdefault('SSL_CERT_FILE', _cert_file)
        os.environ.setdefault('REQUESTS_CA_BUNDLE', _cert_file)
```

**Frontend files are NOT bundled** in the PyInstaller binary. They ship as Electron `extraResources` instead (see the package.json configuration). This separation keeps the backend binary smaller and makes it possible to update the frontend without rebuilding the Python bundle.

### Build Command

```bash
cd backend
pyinstaller budget-app.spec
```

The output goes to `backend/dist/budget-app-backend` — a single executable that's roughly 80–120 MB (the Python interpreter plus all dependencies).

---

## 7.7 Electron Builder: Packaging Everything

The root `package.json` configures `electron-builder` to produce distributable installers:

```json
{
  "name": "budget-app",
  "version": "0.1.7",
  "main": "electron/main.js",
  "scripts": {
    "build:frontend": "cd frontend && npm run build",
    "build:backend": "cd backend && pyinstaller budget-app.spec",
    "build": "npm run build:frontend && electron-builder"
  },
  "build": {
    "appId": "com.seanlewis.budgetapp",
    "productName": "Budget App",
    "files": [
      "electron/**/*",
      "frontend/dist/**/*"
    ],
    "mac": {
      "category": "public.app-category.finance",
      "icon": "electron/icons/icon.icns",
      "target": [{ "target": "dmg", "arch": ["x64", "arm64"] }],
      "extraResources": [
        { "from": "backend/dist/budget-app-backend",
          "to": "backend/budget-app-backend" },
        { "from": "frontend/dist", "to": "frontend/dist" }
      ]
    },
    "win": {
      "icon": "electron/icons/icon.ico",
      "target": [{ "target": "nsis", "arch": ["x64"] }],
      "extraResources": [
        { "from": "backend/dist/budget-app-backend.exe",
          "to": "backend/budget-app-backend.exe" },
        { "from": "frontend/dist", "to": "frontend/dist" }
      ]
    }
  }
}
```

`files` tells electron-builder which files to include in the Electron app itself — the main process code and the frontend build output. `extraResources` copies additional files alongside the app (the PyInstaller binary and a second copy of the frontend for the backend to serve).

The macOS build targets both `x64` (Intel) and `arm64` (Apple Silicon), producing a universal `.dmg`. The Windows build produces an NSIS installer.

### Full Build Pipeline

```bash
# 1. Install dependencies
uv sync                              # Python
cd frontend && npm install && cd ..   # Node

# 2. Build the React frontend
npm run build:frontend                # → frontend/dist/

# 3. Build the Python backend
npm run build:backend                 # → backend/dist/budget-app-backend

# 4. Package everything into a DMG
npm run build                         # → dist/Budget App-0.1.7.dmg
```

Step 4 runs `electron-builder`, which takes the Electron code, the frontend build, and the PyInstaller binary, and assembles them into a macOS `.app` bundle wrapped in a `.dmg`. The output goes to the `dist/` directory.

---

## 7.8 Environment and Configuration in Production

### .env Loading

In development, `.env` lives in the project root and `load_dotenv()` finds it. In production, the app runs from `/Applications/`, so the project root doesn't exist. The backend loads environment variables from two locations:

```python
load_dotenv(dotenv_path=Path.home() / "BudgetApp" / ".env")
load_dotenv()
```

The first call looks in `~/BudgetApp/.env` (next to the database), which is the right place for a production install. The second call is a fallback that checks the current working directory. Variables set by the first call aren't overwritten by the second.

### Database Settings

The Settings page saves API keys to the `app_settings` database table. On startup, the lifespan function loads these into environment variables:

```python
def _load_db_settings_into_env():
    db = SessionLocal()
    rows = db.query(AppSetting).all()
    for row in rows:
        if row.value and row.key in SETTING_ENV_MAP:
            os.environ[SETTING_ENV_MAP[row.key]] = row.value
    db.close()
```

This means users can configure everything through the app's Settings page — they never need to touch a `.env` file or a terminal.

### Graceful Degradation

The app is designed to work without any API keys configured. A user can download the `.dmg`, install it, and immediately start importing CSV bank exports and manually categorizing transactions. The features that require external services degrade gracefully:

- **Without Plaid keys:** The "Connect Bank" button shows a helpful message explaining how to get credentials. CSV import works normally.
- **Without Anthropic key:** The AI categorization tier is skipped — transactions that can't be matched by amount rules or merchant patterns go to the review queue as `pending_review`. The Insights page explains that an API key is needed.
- **Without either:** The app is a fully functional manual finance tracker with charts, budgets, categories, and all the visualization features.

---

## 7.9 Project Summary

When fully assembled, the Budget App has:

- **Multiple bank accounts** connected via Plaid, with automatic sync every 4 hours
- **3-tier categorization** — amount rules, merchant patterns, and Claude AI — with 18 parent categories, 80+ subcategories, and 50+ merchant mappings
- **13+ frontend pages**: Review Queue, Spending, Cash Flow, Recurring Monitor, Budget, Accounts, Investments, Insights, Data, Categories, Settings, Deleted Transactions, Sync History
- **AI features**: Transaction categorization (Claude Haiku) and financial insights (Claude Sonnet for analysis, Haiku for chat), both with prompt caching
- **Investment tracking**: Plaid integration or manual entry, live prices via Yahoo Finance, daily portfolio snapshots
- **Background sync**: APScheduler in-app (4h bank, 6h investments, 30min prices) plus standalone daemon for background syncing
- **Data integrity**: SyncLog audit trail, soft-delete with restore, Fernet-encrypted Plaid tokens, deduplication on every import path
- **Archive import**: Historical Excel/CSV import spanning 4+ years of bank-specific formats with automatic account and category resolution
- **Desktop distribution**: Electron shell with PyInstaller-bundled backend, producing a single `.dmg`

The data lives entirely on your machine in `~/BudgetApp/` — two SQLite databases, an optional `.env` file, and a logs directory. No cloud services store your financial data; the only external calls are to Plaid (for bank connectivity), Anthropic (for AI features), and Yahoo Finance (for stock prices).

---

## Quick Reference: All API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Backend health check |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/transactions` | List transactions (with filters) |
| GET | `/api/transactions/pending` | Pending review queue |
| POST | `/api/transactions/{id}/review` | Confirm/reject category |
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
| GET | `/api/categories` | List all categories |
| GET | `/api/categories/tree` | Category hierarchy |
| POST | `/api/categories` | Create category |
| PUT | `/api/categories/{id}` | Update category |
| POST | `/api/categories/{id}/merge` | Merge categories |
| DELETE | `/api/categories/{id}` | Delete category |
| GET | `/api/budgets` | List budgets for month |
| POST | `/api/budgets` | Create/update budget |
| GET | `/api/accounts` | List accounts |
| POST | `/api/accounts` | Create account |
| GET | `/api/accounts/sync-history` | Sync audit log |
| POST | `/api/accounts/link/token` | Create Plaid link token |
| POST | `/api/accounts/link/exchange` | Exchange public token |
| POST | `/api/accounts/{id}/sync` | Sync single account |
| POST | `/api/accounts/sync-all` | Sync all accounts |
| POST | `/api/accounts/{id}/disconnect` | Disconnect account |
| POST | `/api/accounts/{id}/reset-cursor` | Reset sync cursor |
| DELETE | `/api/accounts/{id}` | Delete account |
| POST | `/api/import` | CSV import |
| POST | `/api/import/auto-detect` | Detect bank format |
| GET | `/api/archive/scan` | Scan for archives |
| POST | `/api/archive/import` | Import archive file |
| GET | `/api/archive/coverage` | Data coverage report |
| GET | `/api/investments/summary` | Portfolio summary |
| GET | `/api/investments/holdings` | All holdings |
| GET | `/api/investments/performance` | Performance chart data |
| GET | `/api/investments/allocation` | Asset allocation |
| GET | `/api/investments/transactions` | Investment transactions |
| GET | `/api/investments/accounts` | Investment accounts |
| POST | `/api/investments/link-token` | Investment link token |
| POST | `/api/investments/link/exchange` | Exchange investment token |
| POST | `/api/investments/accounts/manual` | Create manual account |
| POST | `/api/investments/accounts/{id}/holdings` | Add manual holding |
| POST | `/api/investments/accounts/{id}/sync` | Sync investment account |
| POST | `/api/investments/refresh-prices` | Refresh stock prices |
| DELETE | `/api/investments/accounts/{id}` | Delete investment account |
| GET | `/api/insights/snapshot` | Financial snapshot |
| POST | `/api/insights/analyze` | AI analysis (SSE stream) |
| POST | `/api/insights/chat` | Follow-up chat (SSE stream) |
| GET | `/api/settings/` | Load settings |
| POST | `/api/settings/` | Save settings |

---

← [Back to Index](README.md)
