"""
JARVIS API Server
FastAPI bridge between the Python core engine and the Electron GUI.
Serves REST endpoints + WebSocket for real-time updates.
"""

import asyncio
import json
import os
import threading
import psutil
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import JARVIS modules
from core.memory import (
    get_recent_conversations, get_pending_tasks, get_audit_log,
    add_task, complete_task, log_action
)

app = FastAPI(title="JARVIS API", version="1.0.0")

# Allow Electron renderer process to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Global JARVIS engine reference (set by main.py) ──────────────────────────
jarvis_engine = None
connected_clients: list[WebSocket] = []
_main_loop = None  

@app.on_event("startup")
async def _capture_loop():
    global _main_loop
    _main_loop = asyncio.get_event_loop()

def set_engine(engine):
    global jarvis_engine
    jarvis_engine = engine


# ─── Request models ───────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    text: str
    source: str = "text"  # "text" or "voice"


class TaskRequest(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "normal"


# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "JARVIS online", "time": datetime.now().isoformat()}


@app.get("/health")
def health():
    """Health check — GUI polls this to confirm core is running."""
    return {
        "status": "online",
        "authenticated": jarvis_engine.auth.is_authenticated() if jarvis_engine else False,
        "llm_available": jarvis_engine.llm.is_available() if jarvis_engine else False,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/command")
async def process_command(req: CommandRequest):
    """
    Main command endpoint. GUI sends text or voice-trigger commands here.
    JARVIS is voice-primary: every response is SPOKEN aloud via TTS,
    regardless of whether the command was typed or spoken. The GUI does
    not render responses as chat text — it is not a chatbot interface.
    """
    if not jarvis_engine:
        raise HTTPException(status_code=503, detail="JARVIS engine not initialized")

    if not jarvis_engine.auth.is_authenticated():
        raise HTTPException(status_code=401, detail="JARVIS is locked. Authentication required.")

    # Voice trigger from GUI mic button — tell core to listen.
    # _on_wake_word_detected already speaks the response internally once
    # it has finished listening and processing, so nothing further is
    # needed here.
    if req.text == "__voice_trigger__":
        def _run_and_broadcast():
            _broadcast_voice_status("listening")
            try:
                jarvis_engine._on_wake_word_detected()
            finally:
                _broadcast_voice_status("idle")

        threading.Thread(target=_run_and_broadcast, daemon=True).start()
        return {"response": "__listening__", "timestamp": datetime.now().isoformat()}
        

    try:
        response = await jarvis_engine.process_command_async(req.text)
        log_action("text_command", req.text, response[:100], success=True)

        # Speak every response aloud — JARVIS should say it, not print it.
        # Runs in a background thread so TTS (which blocks) doesn't stall
        # the API's event loop.
        if jarvis_engine.voice:
            threading.Thread(
                target=jarvis_engine.voice.speak,
                args=(response,),
                daemon=True
            ).start()

        # Still broadcast over WebSocket for any client that wants raw
        # data (e.g. logging), but the GUI itself no longer renders this
        # as a chat bubble.
        await broadcast({
            "type": "command_response",
            "user": req.text,
            "jarvis": response,
            "timestamp": datetime.now().isoformat()
        })

        return {"response": response, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        log_action("text_command", req.text, error_msg=str(e), success=False)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/system/stats")
def system_stats():
    """Real-time system stats for the HUD."""
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage("C:\\")
    except Exception:
        disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    return {
        "cpu_percent": cpu,
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / (1024**3), 1),
        "ram_total_gb": round(ram.total / (1024**3), 1),
        "disk_percent": round(disk.percent, 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "net_bytes_sent": net.bytes_sent,
        "net_bytes_recv": net.bytes_recv,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/conversations")
def get_conversations(limit: int = 30):
    """Get recent conversation history."""
    return {"conversations": get_recent_conversations(limit)}


@app.get("/tasks")
def get_tasks():
    """Get all pending tasks."""
    return {"tasks": get_pending_tasks()}


@app.post("/tasks")
def create_task(req: TaskRequest):
    """Add a new task."""
    add_task(req.title, req.description, req.due_date, req.priority)
    log_action("add_task", req.title)
    return {"status": "created", "title": req.title}


@app.patch("/tasks/{task_id}/complete")
def finish_task(task_id: int):
    """Mark a task as complete."""
    complete_task(task_id)
    log_action("complete_task", f"task_id:{task_id}")
    return {"status": "completed"}


@app.get("/audit")
def get_audit(limit: int = 50):
    """Get the full audit log."""
    return {"log": get_audit_log(limit)}


@app.get("/time")
def get_time():
    """Current time + date for the HUD clock."""
    now = datetime.now()
    return {
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%A, %d %B %Y"),
        "timestamp": now.isoformat()
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Remove any dead connections first
    connected_clients.clear()
    connected_clients.append(websocket)
    print(f"[API] GUI connected via WebSocket.")

    try:
        asyncio.create_task(stream_stats(websocket))
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"[API] GUI disconnected.")

async def stream_stats(websocket: WebSocket):
    """Stream system stats to GUI every 2 seconds."""
    while websocket in connected_clients:
        try:
            stats = {
                "type": "stats",
                "cpu": psutil.cpu_percent(interval=None),
                "ram": psutil.virtual_memory().percent,
                "time": datetime.now().strftime("%H:%M:%S"),
                "date": datetime.now().strftime("%d %b %Y")
            }
            await websocket.send_json(stats)
        except Exception:
            break
        await asyncio.sleep(2)


async def broadcast(message: dict):
    """Broadcast a message to all connected WebSocket clients."""
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.append(client)
    for c in disconnected:
        if c in connected_clients:
            connected_clients.remove(c)
def _broadcast_voice_status(status: str):
    """Called from background threads (not the main event loop), so we
    schedule the actual async broadcast onto the main loop safely instead
    of trying to await it directly from a plain thread."""
    if _main_loop is None:
        return
    asyncio.run_coroutine_threadsafe(
        broadcast({"type": "voice_status", "status": status}),
        _main_loop
    )

# ─── Notification endpoint ────────────────────────────────────────────────────

@app.post("/notify")
async def send_notification(data: dict):
    """Push a notification to the GUI and/or toast."""
    await broadcast({"type": "notification", **data})
    return {"status": "sent"}