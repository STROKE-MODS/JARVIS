"""
JARVIS Phase 7 — Media Control
Handles:
  - Global media key control (play/pause/next/prev/volume) — works with
    whatever app currently owns the system media session (Spotify,
    a YouTube tab in Chrome/Brave, VLC, etc.), same as a real keyboard's
    media keys. No per-app integration needed for this part.
  - "Play <song> on YouTube" — searches YouTube and opens the first
    result's watch page directly, which autoplays in-browser.
  - "Play <song> on Spotify" — opens the Spotify desktop app's search
    for the query. NOTE: without a Spotify Developer app + OAuth (and a
    Premium account, which the Web Playback/Control API requires), this
    can only open the search — it can't click Play for you. If you want
    true hands-free Spotify playback later, that needs a separate
    Spotify API integration; flagging this now rather than pretending
    it does something it doesn't.
"""

import ctypes
import re
import subprocess
import urllib.parse
import requests

# ─── Virtual key codes for Windows global media keys ──────────────────────
VK_MEDIA_NEXT_TRACK  = 0xB0
VK_MEDIA_PREV_TRACK  = 0xB1
VK_MEDIA_STOP        = 0xB2
VK_MEDIA_PLAY_PAUSE  = 0xB3
VK_VOLUME_MUTE       = 0xAD
VK_VOLUME_DOWN       = 0xAE
VK_VOLUME_UP         = 0xAF
KEYEVENTF_KEYUP      = 0x0002


def _press_media_key(vk_code: int):
    """Simulate a hardware media key press — this is the same signal a
    real keyboard's play/pause/next/prev buttons send, so it controls
    whichever app Windows currently considers the active media session,
    regardless of which window has focus."""
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def media_play_pause() -> str:
    _press_media_key(VK_MEDIA_PLAY_PAUSE)
    return "Toggled play/pause, Sir."


def media_next() -> str:
    _press_media_key(VK_MEDIA_NEXT_TRACK)
    return "Skipped to next track, Sir."


def media_previous() -> str:
    _press_media_key(VK_MEDIA_PREV_TRACK)
    return "Went back to previous track, Sir."


def media_stop() -> str:
    _press_media_key(VK_MEDIA_STOP)
    return "Playback stopped, Sir."


def media_mute() -> str:
    _press_media_key(VK_VOLUME_MUTE)
    return "Media volume muted, Sir."


def media_volume_up() -> str:
    _press_media_key(VK_VOLUME_UP)
    return "Media volume increased, Sir."


def media_volume_down() -> str:
    _press_media_key(VK_VOLUME_DOWN)
    return "Media volume decreased, Sir."


# ─── YouTube search-and-play ───────────────────────────────────────────────

def play_on_youtube(query: str) -> str:
    """Search YouTube and open the first result's watch page directly —
    this autoplays in most browsers, unlike the plain search results page.

    Implementation note: this scrapes YouTube's search results HTML for
    the first videoId, since that avoids needing a YouTube Data API key
    for something this simple. It's best-effort — if YouTube changes
    their page structure this regex can stop matching. If that happens,
    the safe fallback (also implemented below) is opening the search
    results page instead, which always works, just doesn't autoplay.
    """
    if not query.strip():
        return "What would you like me to play on YouTube, Sir?"

    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"

    try:
        resp = requests.get(search_url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
        if match:
            video_id = match.group(1)
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            subprocess.Popen(f'start brave "{watch_url}"', shell=True)
            return f"Playing '{query}' on YouTube, Sir."
    except Exception as e:
        print(f"[MEDIA] YouTube search scrape failed: {e}")

    # Fallback — always works, just requires you to click the first result
    subprocess.Popen(f'start brave "{search_url}"', shell=True)
    return f"Opened YouTube search results for '{query}', Sir. Couldn't auto-select a video this time — please pick one."


# ─── Spotify search (best-effort — see module docstring for limitation) ────

def play_on_spotify(query: str) -> str:
    """Open Spotify desktop app's search for the query. Cannot auto-press
    Play without a Spotify Developer OAuth integration + Premium account —
    that's a separate, heavier integration if you want it later."""
    if not query.strip():
        return "What would you like me to search for on Spotify, Sir?"

    uri = f"spotify:search:{urllib.parse.quote(query)}"
    try:
        subprocess.Popen(f'start "" "{uri}"', shell=True)
        return f"Opened Spotify search for '{query}', Sir. You'll need to hit play — I can't control Spotify playback directly yet."
    except Exception as e:
        return f"Could not open Spotify, Sir: {e}"