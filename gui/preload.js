/**
 * JARVIS Preload — Phase 2
 * Exposes window controls + tab switching + window shown event to renderer
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvis', {
  hide: () => ipcRenderer.send('hide-window'),
  toggle: () => ipcRenderer.send('toggle-window'),
  minimize: () => ipcRenderer.send('minimize-window'),
  maximize: () => ipcRenderer.send('maximize-window'),
  getApiUrl: () => ipcRenderer.invoke('get-api-url'),
  getWsUrl: () => ipcRenderer.invoke('get-ws-url'),
  onWindowShown: (cb) => ipcRenderer.on('window-shown', cb),
  onSwitchTab: (cb) => ipcRenderer.on('switch-tab', (_, tab) => cb(tab)),
});