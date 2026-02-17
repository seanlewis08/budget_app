/**
 * Backend Manager — Starts/stops the Python FastAPI backend.
 *
 * In development: runs `uvicorn` directly
 * In production: runs the PyInstaller-bundled executable
 */

const { spawn } = require('child_process')
const path = require('path')
const http = require('http')
const { app } = require('electron')

let backendProcess = null

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged
const BACKEND_PORT = 8000

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
