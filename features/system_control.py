"""
JARVIS Phase 3 — System Control
Handles:
  - Open / Close apps by voice
  - Volume control (set, up, down, mute, unmute, max)
  - Screenshot (save to JARVIS/screenshots/)
  - Mouse & keyboard automation
  - Window management (minimize, maximize, switch, close)
"""
import threading
import comtypes
import glob
import os
from typing import Optional
import subprocess
import psutil
import pyautogui
import pygetwindow as gw
from datetime import datetime
from pathlib import Path
import ctypes
import win32gui
import win32con
import win32process
import win32api
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
# Screenshot save folder
SCREENSHOT_DIR = Path("E:/Himanshu Work/JARVIS_Phase1/JARVIS/screenshots")
USER_HOME = os.environ.get("USERPROFILE", os.path.expanduser("~"))
_thread_local = threading.local()
# ─── App name → executable mapping ───────────────────────────────────────────
APP_MAP = {
    "chrome":               r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome":        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "brave":                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "brave browser":        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "browser":              r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "edge":                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "vs code":              fr"{USER_HOME}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "vscode":               fr"{USER_HOME}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "visual studio code":   fr"{USER_HOME}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "code":                 fr"{USER_HOME}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "powershell":           r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    "terminal":             r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    "cmd":                  r"C:\Windows\System32\cmd.exe",
    "command prompt":       r"C:\Windows\System32\cmd.exe",
    "task manager":         r"C:\Windows\System32\Taskmgr.exe",
    "taskmgr":              r"C:\Windows\System32\Taskmgr.exe",
    "file explorer":        r"C:\Windows\explorer.exe",
    "explorer":             r"C:\Windows\explorer.exe",
    "calculator":           r"C:\Windows\System32\calc.exe",
    "calc":                 r"C:\Windows\System32\calc.exe",
    "notepad":              r"C:\Windows\System32\notepad.exe",
    "paint":                r"C:\Windows\System32\mspaint.exe",
    "control panel":        r"C:\Windows\System32\control.exe",
    "settings":             "ms-settings:",
    "registry":             r"C:\Windows\System32\regedit.exe",
    "spotify":              fr"{USER_HOME}\AppData\Roaming\Spotify\Spotify.exe",
    "vlc":                  r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "whatsapp":             fr"{USER_HOME}\AppData\Local\WhatsApp\WhatsApp.exe",
    "discord":              fr"{USER_HOME}\AppData\Local\Discord\app-1.0.9169\Discord.exe",
    "telegram":             fr"{USER_HOME}\AppData\Roaming\Telegram Desktop\Telegram.exe",
}

# Window title keywords for matching
WINDOW_MAP = {
    "chrome":       "chrome",
    "browse":        "brave",
    "brave":          "brave",
    "google chrome":"chrome",
    "vs code":      "visual studio code",
    "vscode":       "visual studio code",
    "code":         "visual studio code",
    "spotify":      "spotify",
    "notepad":      "notepad",
    "notepad++":    "notepad++",
    "powershell":   "powershell",
    "terminal":     "powershell",
    "explorer":     "file explorer",
    "file explorer":"file explorer",
    "task manager": "task manager",
    "taskmanager":   "task manager",
    "taskmngr":       "task manager",
    "whatsapp":     "whatsapp",
    "discord":      "discord",
    "edge":         "edge",
}


# ─── App Control ──────────────────────────────────────────────────────────────
def _find_discord_exe():
    base = fr"{USER_HOME}\AppData\Local\Discord"
    matches = glob.glob(fr"{base}\app-*\Discord.exe")
    return sorted(matches)[-1] if matches else None
def open_app(app_name: str) -> str:
    """Open an application by name."""
    app_lower = app_name.lower().strip()

    # Special URLs that open in browser
    URL_APPS = {
        "whatsapp web": "https://web.whatsapp.com",
        "youtube":      "https://youtube.com",
        "gmail":        "https://mail.google.com",
        "github":       "https://github.com",
        "google":       "https://google.com",
        "chatgpt":      "https://chat.openai.com",
    }

    if app_lower in URL_APPS:
        url = URL_APPS[app_lower]
        subprocess.Popen(f'start brave "{url}"', shell=True)
        return f"Opening {app_name} in brave, Sir."

    # Look up exe
    exe = APP_MAP.get(app_lower)

    if exe:
        try:
            if exe.startswith("ms-"):
                subprocess.Popen(f"start {exe}", shell=True)
            else:
                try:
                    subprocess.Popen([exe], shell=False)
                except OSError:
                    # Fallback for apps needing elevation (e.g. Task Manager)
                    subprocess.Popen(f'start "" "{exe}"', shell=True)
            return f"Opening {app_name}, Sir."
        except Exception as e:
            return f"Failed to open {app_name}, Sir. Error: {e}"
    else:
        # Try running it directly as typed
        try:
            subprocess.Popen(app_name, shell=True)
            return f"Attempting to open {app_name}, Sir."
        except Exception:
            return f"I couldn't find {app_name}, Sir. Make sure it's installed."


def close_app(app_name: str) -> str:
    """Close an application by name — kills the process instantly."""
    app_lower = app_name.lower().strip()
    exe = APP_MAP.get(app_lower, app_name)
    process_name = exe.replace(".exe", "").lower()
    process_name = os.path.basename(process_name)  # strip any path, just in case

    killed = []
    # Pass 1: exact match only
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            proc_name_lower = proc.info["name"].lower().replace(".exe", "")
            if proc_name_lower == process_name:
                proc.kill()
                killed.append(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Pass 2: fallback to substring match only if exact match found nothing
    if not killed:
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                proc_name_lower = proc.info["name"].lower().replace(".exe", "")
                if process_name in proc_name_lower:
                    proc.kill()
                    killed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    if killed:
        unique = list(set(killed))
        return f"Closed {', '.join(unique)}, Sir."
    return f"No running process found for '{app_name}', Sir."

def list_running_apps() -> str:
    """List all currently running applications."""
    known_apps = set(APP_MAP.values())
    running = []

    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name in known_apps:
                display = name.replace(".exe", "").replace("_", " ").title()
                if display not in running:
                    running.append(display)
        except Exception:
            pass

    if running:
        return f"Currently running, Sir: {', '.join(running[:10])}."
    return "No known applications are currently running, Sir."

# ─── Volume Control ───────────────────────────────────────────────────────────

import comtypes

def _get_volume_interface():
    """Get (or reuse) the cached Windows audio endpoint volume interface for this thread."""
    if getattr(_thread_local, "volume_interface", None) is not None:
        return _thread_local.volume_interface

    try:
        comtypes.CoInitialize()
    except OSError:
        pass  # already initialized on this thread

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))

    # Cache it on this thread so we never recreate/destroy it repeatedly
    _thread_local.volume_interface = volume
    _thread_local.devices_ref = devices  # keep a reference alive too

    return volume
def set_volume(level: int) -> str:
    """Set system volume to an exact percentage (0-100)."""
    level = max(0, min(100, int(level)))
    try:
        volume = _get_volume_interface()
        volume.SetMasterVolumeLevelScalar(level / 100, None)
        return f"Volume set to {level}%, Sir."
    except Exception as e:
        return f"Volume control failed, Sir: {e}"


def volume_up(delta: int = 10) -> str:
    """Increase volume by delta percent."""
    try:
        volume = _get_volume_interface()
        current = volume.GetMasterVolumeLevelScalar()
        new_level = min(1.0, current + (delta / 100))
        volume.SetMasterVolumeLevelScalar(new_level, None)
        return f"Volume increased to {round(new_level * 100)}%, Sir."
    except Exception as e:
        return f"Volume up failed, Sir: {e}"


def volume_down(delta: int = 10) -> str:
    """Decrease volume by delta percent."""
    try:
        volume = _get_volume_interface()
        current = volume.GetMasterVolumeLevelScalar()
        new_level = max(0.0, current - (delta / 100))
        volume.SetMasterVolumeLevelScalar(new_level, None)
        return f"Volume decreased to {round(new_level * 100)}%, Sir."
    except Exception as e:
        return f"Volume down failed, Sir: {e}"


def mute_volume() -> str:
    """Mute audio (idempotent — safe to call even if already muted)."""
    try:
        volume = _get_volume_interface()
        volume.SetMute(1, None)
        return "Audio muted, Sir."
    except Exception as e:
        return f"Mute failed, Sir: {e}"


def unmute_volume() -> str:
    """Unmute audio (idempotent — safe to call even if already unmuted)."""
    try:
        volume = _get_volume_interface()
        volume.SetMute(0, None)
        return "Audio unmuted, Sir."
    except Exception as e:
        return f"Unmute failed, Sir: {e}"


def get_current_volume() -> str:
    """Get the actual current volume level and mute state."""
    try:
        volume = _get_volume_interface()
        level = round(volume.GetMasterVolumeLevelScalar() * 100)
        is_muted = volume.GetMute()
        status = "muted" if is_muted else "unmuted"
        return f"Current volume is {level}% and audio is {status}, Sir."
    except Exception as e:
        return f"Volume check failed, Sir: {e}"
# ─── Screenshot ───────────────────────────────────────────────────────────────

def take_screenshot(filename: str = None) -> str:
    """Take a screenshot and save to JARVIS screenshots folder."""
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        elif not filename.endswith(".png"):
            filename += ".png"

        filepath = SCREENSHOT_DIR / filename
        pyautogui.screenshot(str(filepath))

        return f"Screenshot saved as '{filename}', Sir. Location: {SCREENSHOT_DIR}"
    except Exception as e:
        return f"Screenshot failed, Sir: {e}"


def shutdown_pc() -> str:
    """Shutdown the Windows PC."""
    result = subprocess.run("shutdown /s /t 5 /f", shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Shutdown failed, Sir: {result.stderr.strip()}"
    return "Shutting down your PC in 5 seconds, Sir. Goodbye."

def restart_pc() -> str:
    """Restart the Windows PC."""
    result = subprocess.run("shutdown /r /t 5 /f", shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Restart failed, Sir: {result.stderr.strip()}"
    return "Restarting your PC in 5 seconds, Sir."

def cancel_shutdown() -> str:
    """Cancel a pending shutdown."""
    subprocess.run("shutdown /a", shell=True)
    return "Shutdown cancelled, Sir."

def screenshot_region(x: int, y: int, width: int, height: int) -> str:
    """Take a screenshot of a specific region."""
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"region_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = SCREENSHOT_DIR / filename
        img = pyautogui.screenshot(region=(x, y, width, height))
        img.save(str(filepath))
        return f"Region screenshot saved as '{filename}', Sir."
    except Exception as e:
        return f"Region screenshot failed, Sir: {e}"


# ─── Mouse & Keyboard Automation ──────────────────────────────────────────────

def mouse_click(x: int = None, y: int = None, button: str = "left") -> str:
    """Click at position (x, y) or at current position."""
    try:
        if x is not None and y is not None:
            pyautogui.click(x, y, button=button)
            return f"Clicked at ({x}, {y}), Sir."
        else:
            pyautogui.click(button=button)
            pos = pyautogui.position()
            return f"Clicked at current position ({pos.x}, {pos.y}), Sir."
    except Exception as e:
        return f"Click failed, Sir: {e}"


def mouse_move(x: int, y: int) -> str:
    """Move mouse to position (x, y)."""
    try:
        pyautogui.moveTo(x, y, duration=0.3)
        return f"Mouse moved to ({x}, {y}), Sir."
    except Exception as e:
        return f"Mouse move failed, Sir: {e}"


def type_text(text: str) -> str:
    """Type text at current cursor position."""
    try:
        pyautogui.write(text, interval=0.05)
        return f"Typed: '{text}', Sir."
    except Exception as e:
        return f"Typing failed, Sir: {e}"


def press_key(key: str) -> str:
    """Press a keyboard key or combination."""
    try:
        # Handle key combinations like "ctrl+c", "alt+f4"
        if "+" in key:
            keys = [k.strip() for k in key.split("+")]
            pyautogui.hotkey(*keys)
            return f"Pressed {key.upper()}, Sir."
        else:
            pyautogui.press(key)
            return f"Pressed {key}, Sir."
    except Exception as e:
        return f"Key press failed, Sir: {e}"


def copy_to_clipboard() -> str:
    """Copy selected text to clipboard."""
    pyautogui.hotkey("ctrl", "c")
    return "Copied to clipboard, Sir."


def paste_from_clipboard() -> str:
    """Paste from clipboard."""
    pyautogui.hotkey("ctrl", "v")
    return "Pasted from clipboard, Sir."


def get_clipboard_content() -> str:
    """Read current clipboard content."""
    try:
        import pyperclip
        content = pyperclip.paste()
        if content:
            preview = content[:100] + "..." if len(content) > 100 else content
            return f"Clipboard contains: '{preview}', Sir."
        return "Clipboard is empty, Sir."
    except ImportError:
        # Fallback via PowerShell
        try:
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True
            )
            content = result.stdout.strip()
            if content:
                return f"Clipboard contains: '{content[:100]}', Sir."
            return "Clipboard is empty, Sir."
        except Exception:
            return "Could not read clipboard, Sir."


def scroll(direction: str = "down", amount: int = 3) -> str:
    """Scroll up or down."""
    try:
        clicks = amount if direction == "up" else -amount
        pyautogui.scroll(clicks)
        return f"Scrolled {direction}, Sir."
    except Exception as e:
        return f"Scroll failed, Sir: {e}"


# ─── Window Management ────────────────────────────────────────────────────────

def get_all_windows() -> list:
    """Get all visible windows."""
    try:
        windows = gw.getAllWindows()
        return [w for w in windows if w.title.strip()]
    except Exception:
        return []


def find_window(app_name: str):
    """Find a window by app name."""
    app_lower = app_name.lower().strip()
    keyword = WINDOW_MAP.get(app_lower, app_lower)

    all_windows = get_all_windows()
    for w in all_windows:
        if keyword.lower() in w.title.lower():
            return w
    # Fuzzy match — check if any word matches
    for w in all_windows:
        if any(word in w.title.lower() for word in app_lower.split()):
            return w
    return None
def find_hwnd(app_name: str):
    """Find window handle using win32gui."""
    app_lower = app_name.lower().strip()
    keyword = WINDOW_MAP.get(app_lower, app_lower)
    result = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if keyword.lower() in title:
                result.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return result[0] if result else None

def _force_foreground(hwnd):
    """Force a window to foreground — bypasses Windows focus steal prevention."""
    import ctypes
    
    # Get current foreground window thread
    fore_thread = ctypes.windll.user32.GetWindowThreadProcessId(
        ctypes.windll.user32.GetForegroundWindow(), None)
    app_thread = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
    
    # Attach threads
    if fore_thread != app_thread:
        ctypes.windll.user32.AttachThreadInput(fore_thread, app_thread, True)
        win32gui.BringWindowToTop(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        ctypes.windll.user32.AttachThreadInput(fore_thread, app_thread, False)
    else:
        win32gui.BringWindowToTop(hwnd)
    
    ctypes.windll.user32.SetForegroundWindow(hwnd)


def focus_window(app_name: str) -> str:
    hwnd = find_hwnd(app_name)
    if hwnd:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            _force_foreground(hwnd)
            return f"Switched to {app_name}, Sir."
        except Exception as e:
            return f"Could not switch to {app_name}, Sir: {e}"
    return f"No window found for '{app_name}', Sir. Is it open?"


def minimize_window(app_name: Optional[str] = None) -> str:
    if app_name:
        hwnd = find_hwnd(app_name)
        if hwnd:
            try:
                _force_foreground(hwnd)
                import time; time.sleep(0.3)
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return f"Minimized {app_name}, Sir."
            except Exception as e:
                return f"Could not minimize {app_name}, Sir: {e}"
        return f"Window '{app_name}' not found, Sir."
    pyautogui.hotkey('win', 'down')
    return "Window minimized, Sir."


def maximize_window(app_name: Optional[str] = None) -> str:
    if app_name:
        hwnd = find_hwnd(app_name)
        if hwnd:
            try:
                _force_foreground(hwnd)
                import time; time.sleep(0.3)
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                return f"Maximized {app_name}, Sir."
            except Exception as e:
                return f"Could not maximize {app_name}, Sir: {e}"
        return f"Window '{app_name}' not found, Sir."
    pyautogui.hotkey('win', 'up')
    return "Window maximized, Sir."

def close_window(app_name: Optional[str] = None) -> str:
    """Close a window."""
    if app_name:
        window = find_window(app_name)
        if window:
            try:
                window.close()
                return f"Closed {app_name} window, Sir."
            except Exception:
                pass
        # Fall back to killing process
        return close_app(app_name)
    else:
        pyautogui.hotkey("alt", "f4")
        return "Closed current window, Sir."


def list_open_windows() -> str:
    """List all open windows."""
    windows = get_all_windows()
    if not windows:
        return "No windows are currently open, Sir."
    titles = [w.title for w in windows[:10] if len(w.title) > 2]
    return f"Open windows, Sir: {', '.join(titles[:8])}."


def snap_window_left(app_name: Optional[str] = None) -> str:
    if app_name:
        focus_window(app_name)
        import time; time.sleep(0.4)
    pyautogui.hotkey('win', 'left')
    return f"Snapped {app_name or 'window'} to left, Sir."

def snap_window_right(app_name: Optional[str] = None) -> str:
    if app_name:
        focus_window(app_name)
        import time; time.sleep(0.4)
    pyautogui.hotkey('win', 'right')
    return f"Snapped {app_name or 'window'} to right, Sir."

def show_desktop() -> str:
    """Show desktop (minimize all windows)."""
    pyautogui.hotkey("win", "d")
    return "Showing desktop, Sir."


def lock_screen() -> str:
    ctypes.windll.user32.LockWorkStation()
    return "Screen locked, Sir."

def open_task_view() -> str:
    """Open Windows Task View."""
    pyautogui.hotkey("win", "tab")
    return "Task view opened, Sir."


# ─── System Power ─────────────────────────────────────────────────────────────

def sleep_system() -> str:
    ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
    return "Going to sleep, Sir. Goodnight."

def get_screen_resolution() -> str:
    """Get current screen resolution."""
    size = pyautogui.size()
    return f"Screen resolution is {size.width}x{size.height}, Sir."


def get_mouse_position() -> str:
    """Get current mouse position."""
    pos = pyautogui.position()
    return f"Mouse is at ({pos.x}, {pos.y}), Sir."
