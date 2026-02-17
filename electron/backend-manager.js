/**
 * Backend Manager — Starts/stops the Python FastAPI backend.
 *
 * In development: runs `uvicorn` directly
 * In production: runs the PyInstaller-bundled executable
 */

const { spawn, execSync } = require('child_process')
const path = require('path')
const http = require('http')
const { app } = require('electron')

let backendProcess = null

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged
const BACKEND_PORT = 8000

/**
 * Kill any process currently listening on BACKEND_PORT.
 * Prevents "address already in use" from stale previous runs.
 */
function killStaleBackend() {
  try {
    if (process.platform === 'win32') {
      // Windows: find PID listening on the port, then kill it
      const out = execSync(
        `netstat -ano | findstr :${BACKEND_PORT} | findstr LISTENING`,
        { encoding: 'utf8', timeout: 5000 }
      )
      const pids = new Set(
        out.trim().split('\n')
          .map(line => line.trim().split(/\s+/).pop())
          .filter(Boolean)
      )
      for (const pid of pids) {
        try { execSync(`taskkill /PID ${pid} /F`, { timeout: 5000 }) } catch {}
      }
    } else {
      // macOS / Linux
      const out = execSync(`lsof -ti:${BACKEND_PORT}`, {
        encoding: 'utf8',
        timeout: 5000,
      })
      const pids = out.trim().split('\n').filter(Boolean)
      for (const pid of pids) {
        try { process.kill(Number(pid), 'SIGKILL') } catch {}
      }
    }
    if (process.platform !== 'win32') {
      console.log(`Killed stale process(es) on port ${BACKEND_PORT}`)
    }
  } catch {
    // No process on port — expected on clean launch
  }
}

function getBackendPath() {
  if (isDev) {
    return null // Use uvicorn directly in dev
  }

  // Production: PyInstaller bundle
  const platform = process.platform
  const ext = platform === 'win32' ? '.exe' : ''
  return path.join(
    process.resourcesPath,
    'backend',
    `budget-app-backend${ext}`
  )
}

function startBackend() {
  if (backendProcess) {
    console.log('Backend already running')
    return
  }

  // Clean up any zombie from a previous crash/quit
  killStaleBackend()

  if (isDev) {
    // Development mode: run uvicorn
    console.log('Starting backend in dev mode (uvicorn)...')
    backendProcess = spawn('uv', [
      'run', 'uvicorn',
      'backend.main:app',
      '--port', String(BACKEND_PORT),
      '--reload',
    ], {
      cwd: path.join(__dirname, '..'),
      env: { ...process.env },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
  } else {
    // Production mode: run PyInstaller bundle
    const backendPath = getBackendPath()
    console.log(`Starting backend from: ${backendPath}`)
    // Tell the backend where the frontend files are so it can serve the SPA.
    // This is the most reliable approach — Electron always knows its own
    // resourcesPath, and we ship frontend/dist as an extraResource.
    const frontendDir = path.join(process.resourcesPath, 'frontend', 'dist')
    console.log(`Frontend dir for backend: ${frontendDir}`)

    backendProcess = spawn(backendPath, [], {
      env: {
        ...process.env,
        BUDGET_APP_PORT: String(BACKEND_PORT),
        BUDGET_APP_FRONTEND_DIR: frontendDir,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
  }

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`)
  })

  backendProcess.stderr.on('data', (data) => {
    console.error(`[backend] ${data.toString().trim()}`)
  })

  backendProcess.on('close', (code) => {
    console.log(`Backend process exited with code ${code}`)
    backendProcess = null
  })

  backendProcess.on('error', (err) => {
    console.error('Failed to start backend:', err)
    backendProcess = null
  })
}

function stopBackend() {
  if (backendProcess) {
    console.log('Stopping backend...')
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', backendProcess.pid, '/f', '/t'])
    } else {
      backendProcess.kill('SIGTERM')
    }
    backendProcess = null
  }
}

function isBackendReady() {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${BACKEND_PORT}/health`, (res) => {
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(2000, () => {
      req.destroy()
      resolve(false)
    })
  })
}

module.exports = { startBackend, stopBackend, isBackendReady }
