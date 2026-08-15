"""
JARVIS — Main Entry Point
Boots the core engine, API server, and hotkey listener.
Run this to start JARVIS.

Usage:
    python main.py           — Full boot (voice + GUI + API)
    python main.py --text    — Text-only mode (no mic/speaker needed)
    python main.py --setup   — Run first-time setup wizard
"""

import sys
import os
import json
import asyncio
import threading
import argparse
import uvicorn
from colorama import Fore, Style, init as colorama_init

# Initialize colorama for colored terminal output
colorama_init()

# ─── Banner ───────────────────────────────────────────────────────────────────

BANNER = f"""
{Fore.CYAN}
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
{Style.RESET_ALL}
{Fore.BLUE}  Just A Rather Very Intelligent System{Style.RESET_ALL}
{Fore.WHITE}  Built by Himanshu | Phase 1 — Core Engine{Style.RESET_ALL}
"""


def print_banner():
    print(BANNER)


# ─── Setup Wizard ─────────────────────────────────────────────────────────────

def run_setup_wizard():
    """First-time setup — configure PIN, verify Ollama, test voice."""
    print(f"\n{Fore.YELLOW}[SETUP] Welcome to JARVIS First-Time Setup{Style.RESET_ALL}")
    print("="*50)

    # Check Ollama
    print("\n[SETUP] Step 1: Checking Ollama...")
    import requests
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            print(f"{Fore.GREEN}[SETUP] Ollama is running. ✓{Style.RESET_ALL}")
            models = [m["name"] for m in resp.json().get("models", [])]
            print(f"[SETUP] Available models: {models}")
            if not any("phi3" in m for m in models):
                print(f"{Fore.YELLOW}[SETUP] Phi-3 Mini not found. Run: ollama pull phi3:mini{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[SETUP] Ollama error. Start with: ollama serve{Style.RESET_ALL}")
    except Exception:
        print(f"{Fore.RED}[SETUP] Ollama not running! Install from https://ollama.com then run: ollama serve{Style.RESET_ALL}")
        print("[SETUP] You can still continue — JARVIS will work without LLM (basic mode).")

    # Setup PIN
    print("\n[SETUP] Step 2: Setting up PIN authentication...")
    from core.auth import setup_pin
    setup_pin()

    # Check .env
    print("\n[SETUP] Step 3: Environment variables...")
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        print("[SETUP] .env file found. ✓")
        print("[SETUP] Make sure to fill in: CALLMEBOT_PHONE, CALLMEBOT_API_KEY, OPENWEATHER_API_KEY")
    else:
        print(f"{Fore.YELLOW}[SETUP] .env not found. Copy from .env.example and fill in your keys.{Style.RESET_ALL}")

    # Create project directories
    print("\n[SETUP] Step 4: Creating directories...")
    dirs = [
        "E:/Himanshu Work/JARVIS/core",
        "E:/Himanshu Work/JARVIS/screenshots",
        "E:/Himanshu Work/JARVIS/core/logs",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"[SETUP]   Created: {d}")

    print(f"\n{Fore.GREEN}[SETUP] Setup complete! Run 'python main.py' to start JARVIS.{Style.RESET_ALL}")


# ─── Text Mode (no microphone) ────────────────────────────────────────────────

def run_text_mode(engine):
    """Simple terminal chat loop for testing without mic/speaker."""
    print(f"\n{Fore.CYAN}[JARVIS] Text mode active. Type commands below. Type 'quit' to exit.{Style.RESET_ALL}")
    print("─"*50)

    while True:
        try:
            user_input = input(f"{Fore.WHITE}You: {Style.RESET_ALL}").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "bye"):
                print(f"{Fore.CYAN}[JARVIS] Shutting down. Goodbye, Sir.{Style.RESET_ALL}")
                break

            response = engine.process_command(user_input)
            print(f"{Fore.CYAN}JARVIS: {Style.RESET_ALL}{response}\n")

        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}[JARVIS] Interrupted. Goodbye, Sir.{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"{Fore.RED}[ERROR] {e}{Style.RESET_ALL}")


# ─── API Server Thread ────────────────────────────────────────────────────────

def start_api_server(engine):
    """Start FastAPI server in a background thread."""
    import api_server
    api_server.set_engine(engine)

    config = json.load(open("config.json"))
    host = config["api"]["host"]
    port = config["api"]["port"]

    print(f"[API] Starting JARVIS API server on http://{host}:{port}")

    def run():
        uvicorn.run(
            "api_server:app",
            host=host,
            port=port,
            log_level="warning",  # Suppress verbose uvicorn logs
            reload=False
        )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print(f"[API] API server running. Electron GUI can connect at http://{host}:{port}")
    return thread


# ─── Hotkey Listener ─────────────────────────────────────────────────────────

def start_hotkey_listener(engine):
    """
    Listen for Ctrl+Space (toggle activation) AND F7 (push-to-talk, hold
    to speak) globally, regardless of which window has focus.
    Runs in background thread.
    """
    try:
        import keyboard
        import threading

        def on_ctrl_space():
            if engine.auth.is_authenticated():
                print("\n[HOTKEY] Ctrl+Space detected — activating JARVIS...")
                engine._on_wake_word_detected()
            else:
                print("[HOTKEY] JARVIS locked. Triggering authentication...")
                engine.auth.authenticate()

        keyboard.add_hotkey("ctrl+space", on_ctrl_space)
        print("[HOTKEY] Ctrl+Space listener active.")

        # ── F7 push-to-talk: hold to speak, release to process ──────────
        _f7_held = threading.Event()
        _ptt_thread_running = threading.Event()

        def _on_f7_press(event):
            if _ptt_thread_running.is_set():
                return  # already listening from a previous press, ignore repeats
            _f7_held.set()
            _ptt_thread_running.set()

            def _run():
                engine._on_push_to_talk(lambda: _f7_held.is_set())
                _ptt_thread_running.clear()

            threading.Thread(target=_run, daemon=True).start()

        def _on_f7_release(event):
            _f7_held.clear()

        keyboard.on_press_key("f7", _on_f7_press, suppress=False)
        keyboard.on_release_key("f7", _on_f7_release, suppress=False)
        print("[HOTKEY] F7 push-to-talk active — hold F7 to speak, release to send.")

    except ImportError:
        print("[HOTKEY] 'keyboard' library not installed. Install with: pip install keyboard")
    except Exception as e:
        print(f"[HOTKEY] Failed to register hotkey: {e}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print_banner()

    parser = argparse.ArgumentParser(description="JARVIS — AI Personal Assistant")
    parser.add_argument("--text", action="store_true", help="Text-only mode (no microphone)")
    parser.add_argument("--setup", action="store_true", help="Run first-time setup wizard")
    parser.add_argument("--no-voice", action="store_true", help="Disable voice output (TTS)")
    parser.add_argument("--no-api", action="store_true", help="Skip API server (no Electron GUI)")
    args = parser.parse_args()

    
    if args.setup:
        run_setup_wizard()
        return

    # Boot core engine
    from core.jarvis_engine import JARVISEngine
    engine = JARVISEngine()

    # Start API server (for Electron GUI)
    if not args.no_api:
        start_api_server(engine)
    # Start hotkey listener
    start_hotkey_listener(engine)

    # Full startup (auth + greeting + wake word loop)
    if args.text or args.no_voice:
        # Skip voice auth for text mode
        engine.auth.authenticated = True
        print(f"\n{Fore.GREEN}[JARVIS] Running in text mode. Authentication bypassed for testing.{Style.RESET_ALL}")
        run_text_mode(engine)
    else:
        # Full mode — voice auth, TTS greeting, background wake word loop
        if engine.startup():
            print(f"\n{Fore.GREEN}[JARVIS] JARVIS is fully operational, Sir.{Style.RESET_ALL}")
            print(f"{Fore.CYAN}  Wake word : 'Hey JARVIS'{Style.RESET_ALL}")
            print(f"{Fore.CYAN}  Hotkey    : Ctrl+Space{Style.RESET_ALL}")
            print(f"{Fore.CYAN}  Text mode : python main.py --text{Style.RESET_ALL}")
            print(f"{Fore.CYAN}  Press Ctrl+C to shut down.{Style.RESET_ALL}\n")

            # Keep main thread alive
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print(f"\n{Fore.CYAN}[JARVIS] Shutting down. Goodbye, Sir.{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[JARVIS] Startup failed. Exiting.{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
