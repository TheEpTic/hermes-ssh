"""SSH connection management — multiplexed sessions via ControlMaster."""
from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from . import sessions
from .registry import get_machine, resolve_name

DATA_DIR = Path(__file__).parent / "data"
SOCKET_DIR = DATA_DIR / "sockets"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOCKET_DIR.mkdir(parents=True, exist_ok=True)


def _build_ssh_args(
    machine: Dict[str, Any],
    command: str,
    control_path: str = "",
    timeout: int = 30,
) -> list[str]:
    """Build SSH command arguments."""
    cmd = [
        "ssh",
        "-o", f"ConnectTimeout={min(timeout, 10)}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "RequestTTY=no",
        "-p", str(machine.get("port", 22)),
    ]

    key = machine.get("key", "")
    if key:
        cmd.extend(["-i", os.path.expanduser(key)])

    if control_path:
        cmd.extend([
            "-o", f"ControlMaster=auto",
            "-o", f"ControlPath={control_path}",
            "-o", "ControlPersist=no",
        ])

    user = machine.get("user", "root")
    host = machine["host"]
    cmd.append(f"{user}@{host}")
    cmd.append(command)
    return cmd


def run_command(
    machine_name: str,
    command: str,
    timeout: int = 30,
    new_session: bool = False,
) -> Dict[str, Any]:
    """Run a command on a remote machine via SSH.

    Args:
        machine_name: Machine name or alias from registry
        command: Command to execute
        timeout: Seconds before killing the command
        new_session: Force a new connection (skip multiplexing)

    Returns:
        dict with stdout, stderr, exit_code, session_id
    """
    _ensure_dirs()

    # Resolve machine
    canonical = resolve_name(machine_name)
    if not canonical:
        return {"success": False, "error": f"Machine '{machine_name}' not found in registry. Add it first with ssh_machines."}

    machine = get_machine(canonical)
    if not machine:
        return {"success": False, "error": f"Machine '{machine_name}' not found in registry."}

    # Session ID
    session_id = f"ssh_{canonical}_{uuid.uuid4().hex[:8]}"
    control_path = "" if new_session else str(SOCKET_DIR / f"{canonical}.sock")

    ssh_args = _build_ssh_args(machine, command, control_path, timeout)

    start_time = time.monotonic()
    try:
        result = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout + 5,  # Extra buffer for SSH overhead
        )
        elapsed = round(time.monotonic() - start_time, 2)

        # Register session
        sessions.register_session(
            session_id=session_id,
            machine=canonical,
            pid=0,  # Command already finished
            control_path=control_path,
        )
        sessions.close_session(session_id)

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "elapsed_secs": elapsed,
            "machine": canonical,
            "session_id": session_id,
        }

    except subprocess.TimeoutExpired:
        elapsed = round(time.monotonic() - start_time, 2)
        sessions.register_session(
            session_id=session_id,
            machine=canonical,
            pid=0,
            control_path=control_path,
        )
        sessions.close_session(session_id)
        return {
            "success": False,
            "error": f"Command timed out after {timeout}s",
            "exit_code": -1,
            "elapsed_secs": elapsed,
            "machine": canonical,
            "session_id": session_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exit_code": -1,
            "machine": canonical,
        }


def start_interactive(
    machine_name: str,
    command: str = "",
    timeout: int = 30,
) -> Dict[str, Any]:
    """Start an interactive SSH session (background process).

    For commands that need persistent connections or background work.
    Returns session_id for later tracking/kill.
    """
    _ensure_dirs()

    canonical = resolve_name(machine_name)
    if not canonical:
        return {"success": False, "error": f"Machine '{machine_name}' not found in registry."}

    machine = get_machine(canonical)
    if not machine:
        return {"success": False, "error": f"Machine '{machine_name}' not found in registry."}

    session_id = f"ssh_{canonical}_{uuid.uuid4().hex[:8]}"
    control_path = str(SOCKET_DIR / f"{canonical}_{uuid.uuid4().hex[:4]}.sock")

    ssh_args = _build_ssh_args(machine, command or "bash", control_path, timeout)

    try:
        proc = subprocess.Popen(
            ssh_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        sessions.register_session(
            session_id=session_id,
            machine=canonical,
            pid=proc.pid,
            control_path=control_path,
        )

        # Give it a moment to connect
        time.sleep(0.5)
        poll = proc.poll()
        if poll is not None:
            stdout, stderr = proc.communicate()
            sessions.close_session(session_id)
            return {
                "success": poll == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": poll,
                "machine": canonical,
                "session_id": session_id,
            }

        return {
            "success": True,
            "pid": proc.pid,
            "machine": canonical,
            "session_id": session_id,
            "message": f"SSH session started to {canonical}. Use ssh_sessions to manage.",
        }

    except Exception as e:
        return {"success": False, "error": str(e), "machine": canonical}
