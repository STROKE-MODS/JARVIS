/**
 * JARVIS Electron Main Process — Phase 2
 * Updated window size to match new 680x760 GUI
 */

const { app, BrowserWindow, globalShortcut, Tray, Menu, nativeImage, ipcMain, screen } = require('electron');
const path = require('path');
const WebSocket = require('ws');

let mainWindow = null;
let tray = null;
let popupWindow = null;
let voiceWs = null;

// ─── Window ───────────────────────────────────────────────────────────────────

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width: 680,
    height: 760,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: true,
    skipTaskbar: true,
    show: false,
    // Bottom-right corner positioning
    x: width - 696,
    y: height - 778,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  mainWindow.on('close', (e) => {
    e.preventDefault();
    mainWindow.hide();
  });

  // Dev tools shortcut (remove in production)
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.key === 'F12') {
      mainWindow.webContents.openDevTools({ mode: 'detach' });
    }
  });
}

// ─── Tray ──────────────────────────────────────────────────────────────────────

function createTray() {
  // Fallback to empty icon if tray_icon.png not found
  let icon;
  try {
    icon = nativeImage.createFromPath(path.join(__dirname, 'assets', 'tray_icon.png'));
    if (icon.isEmpty()) throw new Error('empty');
  } catch {
    icon = nativeImage.createEmpty();
  }

  tray = new Tray(icon);
  tray.setToolTip('J.A.R.V.I.S — Online');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '⚡ Show JARVIS', click: toggleWindow },
    { label: '📋 Chat', click: () => { showWindow(); sendTab('chat'); } },
    { label: '✅ Tasks', click: () => { showWindow(); sendTab('tasks'); } },
    { label: '📊 System Stats', click: () => { showWindow(); sendTab('stats'); } },
    { type: 'separator' },
    { label: '❌ Quit JARVIS', click: () => app.exit(0) }
  ]));
  tray.on('click', toggleWindow);
}

// ADD this new function:
function createPopupWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  popupWindow = new BrowserWindow({
    width: 260,
    height: 60,
    x: width - 280,
    y: height - 100,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    focusable: false,   // never steals focus from whatever you're doing
    show: false,         // hidden until a 'listening' broadcast arrives
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  popupWindow.loadFile(path.join(__dirname, 'popup.html'));
  popupWindow.setAlwaysOnTop(true, 'screen-saver'); // stays above nearly everything
}

function showPopup() {
  if (popupWindow) popupWindow.showInactive(); // show without stealing focus
}

function hidePopup() {
  if (popupWindow) popupWindow.hide();
}
// ADD this new function:
function connectVoiceStatusSocket() {
  try {
    voiceWs = new WebSocket('ws://127.0.0.1:8765/ws');

    voiceWs.on('open', () => {
      console.log('[POPUP] Connected to JARVIS voice status socket.');
    });

    voiceWs.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.type === 'voice_status') {
          if (msg.status === 'listening') showPopup();
          else hidePopup();
        }
      } catch (e) {
        // ignore malformed messages
      }
    });

    voiceWs.on('close', () => {
      console.log('[POPUP] Voice status socket closed — retrying in 3s...');
      setTimeout(connectVoiceStatusSocket, 3000);
    });

    voiceWs.on('error', () => {
      // swallow — 'close' handler above will trigger the retry
    });
  } catch (e) {
    setTimeout(connectVoiceStatusSocket, 3000);
  }
}
function sendTab(name) {
  if (mainWindow) mainWindow.webContents.send('switch-tab', name);
}

// ─── Toggle ────────────────────────────────────────────────────────────────────

function toggleWindow() {
  if (mainWindow.isVisible()) {
    mainWindow.hide();
  } else {
    showWindow();
  }
}

function showWindow() {
  mainWindow.show();
  mainWindow.focus();
  mainWindow.webContents.send('window-shown');
}

// ─── IPC ───────────────────────────────────────────────────────────────────────

ipcMain.on('hide-window', () => mainWindow.hide());
ipcMain.on('toggle-window', () => toggleWindow());

// These were missing before — the GUI's minimize/maximize buttons called
// window.jarvis.minimize()/maximize() but nothing on this side ever
// listened for them, so the buttons silently did nothing.
ipcMain.on('minimize-window', () => {
  if (mainWindow) mainWindow.minimize();
});
ipcMain.on('maximize-window', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow.maximize();
  }
});

ipcMain.handle('get-api-url', () => 'http://127.0.0.1:8765');
ipcMain.handle('get-ws-url', () => 'ws://127.0.0.1:8765/ws');

// ─── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  createTray();
  createPopupWindow();
  connectVoiceStatusSocket();

  // Ctrl+Space global hotkey
  const ok = globalShortcut.register('CommandOrControl+Space', toggleWindow);
  if (!ok) console.error('[JARVIS] Failed to register Ctrl+Space hotkey');
  else console.log('[JARVIS] Ctrl+Space hotkey registered ✓');

  console.log('[JARVIS] Electron GUI ready. Window: 680x760, bottom-right corner.');
  console.log('[JARVIS] Listening popup ready — will appear bottom-right when JARVIS is listening.');
});

app.on('will-quit', () => globalShortcut.unregisterAll());
app.on('window-all-closed', (e) => e.preventDefault());