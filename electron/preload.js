/**
 * Preload script — runs in the renderer process before web content loads.
 * Provides a secure bridge between the renderer and Node.js.
 */

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  // Expose any Electron-specific APIs here
  getVersion: () => process.env.npm_package_version || '0.1.0',
  getPlatform: () => process.platform,
})
