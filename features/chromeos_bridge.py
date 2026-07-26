"""
JARVIS Phase 5 — ChromeOS Bridge (SERVER MODE)
Windows side — runs a WebSocket SERVER. The ChromeOS agent connects IN to this.
This avoids needing Crostini port forwarding, since outbound connections
from the Chromebook's Linux container work fine even when inbound is blocked.
"""

import json
import time
import uuid
import asyncio
import threading
from datetime import datetime
import websockets  # pip install websockets

# ─── Config ───────────────────────────────────────────────────────────────────
SECRET_KEY  = "jarvis_lan_secret_2024"
SERVER_PORT = 8767
TIMEOUT     = 10  # seconds to wait for a response

_chromeos_stats = {
    "connected": False,
    "cpu_percent": 0,
    "ram_percent": 0,
    "ram_used_gb": "0",
    "ram_total_gb": "0",
    "battery": None,
    "ip": "unknown",
    "hostname": "unknown",
    "uptime": 0,
    "last_updated": None
}

_connected_ws = None      # the live websocket connection object
_loop = None               # the asyncio event loop running the server
_server_thread = None
_pending_responses = {}
_lock = threading.Lock()


# ─── Connection Handler ────────────────────────────────────────────────────────

async def _handle_client(websocket):
    global _connected_ws, _chromeos_stats
    print("[CHROMEOS] ✓ Chromebook connected!")
    _connected_ws = websocket
    _chromeos_stats["connected"] = True

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "handshake":
                print(f"[CHROMEOS] Handshake from: {msg.get('hostname')} ({msg.get('platform')})")

            elif msg_type == "stats":
                _chromeos_stats.update(msg)
                _chromeos_stats["connected"] = True
                _chromeos_stats["last_updated"] = datetime.now().isoformat()

            elif msg_type == "response":
                msg_id = msg.get("id")
                if msg_id:
                    with _lock:
                        _pending_responses[msg_id] = msg

            elif msg_type == "error":
                print(f"[CHROMEOS] Agent error: {msg.get('message')}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        print("[CHROMEOS] Chromebook disconnected.")
        _connected_ws = None
        _chromeos_stats["connected"] = False


def _run_server():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    async def _main():
        async with websockets.serve(_handle_client, "0.0.0.0", SERVER_PORT):
            print(f"[CHROMEOS] WebSocket server listening on 0.0.0.0:{SERVER_PORT}")
            print("[CHROMEOS] Waiting for Chromebook agent to connect...")
            await asyncio.Future()  # run forever

    _loop.run_until_complete(_main())


# ─── Public API (same function names as before, so jarvis_engine.py doesn't change) ──

def initialize_bridge(chromeos_ip: str = None) -> str:
    """Start the WebSocket server. chromeos_ip is ignored/unused in server mode
    but kept as a parameter so existing calls in jarvis_engine.py don't break."""
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        return "ChromeOS bridge server already running, Sir."

    _server_thread = threading.Thread(target=_run_server, daemon=True)
    _server_thread.start()
    time.sleep(1)
    return f"ChromeOS bridge server started on port {SERVER_PORT}, Sir. Waiting for the Chromebook to connect."


def is_connected() -> bool:
    return _connected_ws is not None


def _send_command(command: str, params: dict = None, timeout: int = TIMEOUT) -> dict:
    if not is_connected():
        return {"success": False, "output": "ChromeOS agent not connected"}

    msg_id = str(uuid.uuid4())[:8]
    payload = {
        "id": msg_id,
        "key": SECRET_KEY,
        "command": command,
        "params": params or {},
        "timestamp": datetime.now().isoformat()
    }

    try:
        asyncio.run_coroutine_threadsafe(
            _connected_ws.send(json.dumps(payload)), _loop
        )
    except Exception as e:
        return {"success": False, "output": f"Send failed: {e}"}

    deadline = time.time() + timeout
    while time.time() < deadline:
        with _lock:
            if msg_id in _pending_responses:
                return _pending_responses.pop(msg_id)
        time.sleep(0.1)

    return {"success": False, "output": "Timeout waiting for ChromeOS response"}


# ─── Command Functions (same as before) ────────────────────────────────────────

def get_chromeos_stats() -> str:
    if not is_connected():
        return "ChromeOS is not connected, Sir. Make sure the agent is running on your Chromebook."
    stats = _chromeos_stats
    battery_str = ""
    if stats.get("battery"):
        b = stats["battery"]
        battery_str = f"Battery: {b.get('percent', '?')}% ({b.get('status', '?')}). "
    return (
        f"ChromeOS status, Sir: "
        f"CPU {stats.get('cpu_percent', 0)}%, "
        f"RAM {stats.get('ram_percent', 0)}% "
        f"({stats.get('ram_used_gb', 0)}GB/{stats.get('ram_total_gb', 0)}GB). "
        f"{battery_str}"
        f"IP: {stats.get('ip', 'unknown')}. "
        f"Uptime: {stats.get('uptime', 0)} minutes."
    )


def open_url_on_chromeos(url: str) -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    if not url.startswith("http"):
        url = "https://" + url
    result = _send_command("open_url", {"url": url})
    if result.get("success"):
        return f"Opening {url} on your Chromebook, Sir."
    return f"Could not open URL on ChromeOS, Sir: {result.get('output', 'Unknown error')}"


def run_command_on_chromeos(cmd: str) -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    result = _send_command("run_command", {"cmd": cmd})
    output = result.get("output", "No output")
    if result.get("success"):
        return f"Command executed on ChromeOS, Sir. Output: {output[:300]}"
    return f"Command failed on ChromeOS, Sir: {output[:200]}"


def run_python_on_chromeos(code: str) -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    result = _send_command("run_python", {"code": code}, timeout=30)
    output = result.get("output", "No output")
    if result.get("success"):
        return f"Python executed on ChromeOS, Sir. Output: {output[:300]}"
    return f"Python execution failed, Sir: {output[:200]}"


def run_python_file_on_chromeos(filepath: str) -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    result = _send_command("run_python_file", {"filepath": filepath}, timeout=60)
    output = result.get("output", "No output")
    if result.get("success"):
        return f"Running {filepath} on ChromeOS, Sir. Output: {output[:300]}"
    return f"Failed to run file on ChromeOS, Sir: {output[:200]}"


def chromeos_media_control(action: str) -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    command_map = {
        "play": "media_play_pause", "pause": "media_play_pause",
        "next": "media_next", "previous": "media_previous",
        "mute": "mute", "volumeup": "volume_up", "volumedown": "volume_down",
    }
    cmd = command_map.get(action.lower())
    if not cmd:
        return f"Unknown media action: {action}, Sir."
    result = _send_command(cmd)
    if result.get("success"):
        return f"Media {action} on ChromeOS, Sir."
    return "Media control failed on ChromeOS, Sir."


def get_chromeos_processes() -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    result = _send_command("process_list")
    if result.get("success"):
        return f"Top processes on ChromeOS, Sir:\n{result.get('output', '')[:400]}"
    return "Could not get process list, Sir."


def get_chromeos_disk() -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    result = _send_command("disk_usage")
    if result.get("success"):
        return f"ChromeOS disk usage, Sir:\n{result.get('output', '')[:300]}"
    return "Could not get disk usage, Sir."


def list_files_on_chromeos(directory: str = "~") -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    result = _send_command("list_files", {"dir": directory})
    if result.get("success"):
        return f"Files in {directory} on ChromeOS, Sir:\n{result.get('output', '')[:400]}"
    return "Could not list files on ChromeOS, Sir."


def ping_chromeos() -> str:
    if not is_connected():
        return "ChromeOS bridge not connected, Sir."
    result = _send_command("ping", timeout=5)
    if result.get("success"):
        return "ChromeOS agent is online, Sir. Ping successful."
    return "ChromeOS agent is not responding, Sir."


def get_chromeos_ip() -> str:
    if not is_connected():
        return "ChromeOS not connected, Sir."
    result = _send_command("get_ip")
    if result.get("success"):
        return f"ChromeOS IP addresses, Sir: {result.get('output', '')}"
    return "Could not get ChromeOS IP, Sir."