/**
 * Budget App — Electron Main Process
 *
 * Responsibilities:
 * 1. Start the Python/FastAPI backend as a child process
 * 2. Wait for the backend to be ready
 * 3. Open the React dashboard in a native window
 * 4. Clean up on exit
 */

const { app, BrowserWindow, shell } = require('electron')
const path = require('path')
const { startBackend, stopBackend, isBackendReady } = require('./backend-manager')

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
    // Modern look
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    backgroundColor: '#0f1117',
    show: false, // Show after ready
  })

  // Show when ready to avoid flash
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // Load the app
  if (isDev) {
    // Development: load from Vite dev server
    mainWindow.loadURL('http://localhost:3000')
    mainWindow.webContents.openDevTools()
  } else {
    // Production: load the built React app
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'))
  }

  // Open external links in default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

async function startup() {
  // Start the Python backend
  console.log('Starting Python backend...')
  startBackend()

  // Wait for the backend to be ready (up to 30 seconds)
  const maxRetries = 60
  let retries = 0

  while (retries < maxRetries) {
    if (await isBackendReady()) {
      console.log('Backend is ready!')
      break
    }
    await new Promise(resolve => setTimeout(resolve, 500))
    retries++
  }

  if (retries >= maxRetries) {
    console.error('Backend failed to start within 30 seconds')
    // Still open the window — it'll show connection errors
  }

  createWindow()
}

// App lifecycle
app.whenReady().then(startup)

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.on('before-quit', () => {
  stopBackend()
})
