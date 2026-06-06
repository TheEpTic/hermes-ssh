"""Session tracking — monitor active SSH sessions, detect idle, cleanup."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DATA_DIR = Path(__file__).parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
_lock = threading.Lock()

# Background idle checker
_checker_thread: Optional[threading.Thread] = None
_checker_running = False


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> Dict[str, Any]:
    _ensure_data_dir()
    if SESSIONS_FILE.exists():
        try:
            data = json.loads(SESSIONS_FILE.read_text())
            # Migrate old format
            if "sessions" not in data:
                data = {"sessions": data}
            return data
        except (json.JSONDecodeError, OSError):
            return {"sessions": {}}
    return {"sessions": {}}


def _save(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    SESSIONS_FILE.write_text(json.dumps(data, indent=2) + "\n")


def register_session(
    session_id: str,
    machine: str,
    pid: int,
    control_path: str = "",
) -> None:
    """Register a new active SSH session."""
    with _lock:
        data = _load()
        data["sessions"][session_id] = {
            "machine": machine,
            "pid": pid,
            "control_path": control_path,
            "started": datetime.now(timezone.utc).isoformat(),
            "last_active": datetime.now(timezone.utc).isoformat(),
            "command_count": 0,
            "status": "active",
        }
        _save(data)


def touch_session(session_id: str) -> None:
    """Update last_active timestamp for a session."""
    with _lock:
        data = _load()
        if session_id in data["sessions"]:
            data["sessions"][session_id]["last_active"] = datetime.now(timezone.utc).isoformat()
            data["sessions"][session_id]["command_count"] = (
                data["sessions"][session_id].get("command_count", 0) + 1
            )
            _save(data)


def close_session(session_id: str) -> None:
    """Mark a session as closed."""
    with _lock:
        data = _load()
        if session_id in data["sessions"]:
            data["sessions"][session_id]["status"] = "closed"
            _save(data)


def remove_session(session_id: str) -> None:
    """Remove a session from tracking entirely."""
    with _lock:
        data = _load()
        data["sessions"].pop(session_id, None)
        _save(data)


def list_sessions(status: str = "active") -> Dict[str, Any]:
    """List sessions, optionally filtered by status."""
    data = _load()
    if status:
        return {
            k: v for k, v in data["sessions"].items()
            if v.get("status") == status
        }
    return data["sessions"]


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific session."""
    data = _load()
    return data["sessions"].get(session_id)


def idle_seconds(session_id: str) -> Optional[int]:
    """Calculate how many seconds a session has been idle."""
    session = get_session(session_id)
    if not session or session.get("status") != "active":
        return None
    last_active = session.get("last_active")
    if not last_active:
        return None
    try:
        last = datetime.fromisoformat(last_active)
        now = datetime.now(timezone.utc)
        return int((now - last).total_seconds())
    except (ValueError, TypeError):
        return None


def kill_session(session_id: str) -> Dict[str, Any]:
    """Kill an active SSH session by PID and close control socket."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session '{session_id}' not found"}

    pid = session.get("pid")
    control_path = session.get("control_path", "")
    results = {"pid_killed": False, "socket_closed": False}

    # Kill the SSH process
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            # Check if still alive
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            results["pid_killed"] = True
        except OSError:
            results["pid_killed"] = True  # Already dead

    # Close control socket
    if control_path and os.path.exists(control_path):
        try:
            subprocess.run(
                ["ssh", "-O", "exit", "-o", f"ControlPath={control_path}", "dummy"],
                capture_output=True, timeout=5,
            )
            results["socket_closed"] = True
        except Exception:
            pass

    close_session(session_id)
    return {"success": True, **results}


def cleanup_idle(max_idle_minutes: int = 30) -> Dict[str, Any]:
    """Kill all sessions idle for more than max_idle_minutes."""
    active = list_sessions("active")
    killed = []
    for sid, session in active.items():
        idle = idle_seconds(sid)
        if idle is not None and idle > max_idle_minutes * 60:
            result = kill_session(sid)
            killed.append({"session_id": sid, "machine": session.get("machine"), **result})
    return {"killed": killed, "count": len(killed)}


def prune_closed(max_age_hours: int = 24) -> int:
    """Remove closed sessions older than max_age_hours."""
    data = _load()
    now = datetime.now(timezone.utc)
    to_remove = []
    for sid, session in data["sessions"].items():
        if session.get("status") != "active":
            try:
                started = datetime.fromisoformat(session.get("started", ""))
                if (now - started).total_seconds() > max_age_hours * 3600:
                    to_remove.append(sid)
            except (ValueError, TypeError):
                pass
    with _lock:
        for sid in to_remove:
            del data["sessions"][sid]
        if to_remove:
            _save(data)
    return len(to_remove)


def start_idle_checker(interval: int = 60, max_idle_minutes: int = 30) -> None:
    """Start a background thread that checks for idle sessions."""
    global _checker_thread, _checker_running

    if _checker_running:
        return

    def _check_loop():
        global _checker_running
        _checker_running = True
        while _checker_running:
            try:
                cleanup_idle(max_idle_minutes)
            except Exception:
                pass
            time.sleep(interval)

    _checker_thread = threading.Thread(target=_check_loop, daemon=True)
    _checker_thread.start()


def stop_idle_checker() -> None:
    """Stop the background idle checker."""
    global _checker_running
    _checker_running = False
