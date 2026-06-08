"""Core SSH manager — single class owning all state and operations.

Consolidates machine registry, session tracking, and SSH execution.
No module-level mutable state — everything lives on the instance.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shlex
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from .config import DEFAULT_CONFIG, SSHConfig
from .models import Machine, Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSH Manager
# ---------------------------------------------------------------------------


class SSHManager:
    """Owns all SSH plugin state: machines, sessions, connections.

    Thread-safe. Designed for injection and testing with a custom config.
    """

    def __init__(self, config: SSHConfig | None = None) -> None:
        self._config = config or DEFAULT_CONFIG
        self._lock = threading.Lock()
        self._checker_thread: threading.Thread | None = None
        self._checker_event = threading.Event()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._config.ensure_dirs()

    @property
    def config(self) -> SSHConfig:
        return self._config

    @property
    def _audit_log_path(self) -> Path:
        return self._config.data_dir / "command_log.jsonl"

    # ----- JSON persistence -----

    def _read_json(self, path: Path, default: Any) -> Any:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Corrupt data in %s, resetting: %s", path, exc)
                return default
        return default

    def _write_json(self, path: Path, data: Any) -> None:
        """Atomic write: write to temp file then os.replace()."""
        self._config.data_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._config.data_dir),
            suffix=".tmp",
            prefix=path.stem,
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, str(path))
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    # ----- Machine registry -----

    def _load_machines(self) -> dict[str, dict[str, Any]]:
        raw = self._read_json(self._config.machines_file, {"machines": {}})
        result: dict[str, dict[str, Any]] = raw.get("machines", {})
        return result

    def _save_machines(self, machines: dict[str, dict[str, Any]]) -> None:
        self._write_json(self._config.machines_file, {"machines": machines})

    def list_machines(self) -> dict[str, Machine]:
        raw = self._load_machines()
        return {name: Machine.from_dict(name, d) for name, d in raw.items()}

    def get_machine(self, name: str) -> Machine | None:
        machines = self._load_machines()
        # Direct match
        if name in machines:
            return Machine.from_dict(name, machines[name])
        # Alias match
        for mname, mdata in machines.items():
            if name in mdata.get("aliases", []):
                return Machine.from_dict(mname, mdata)
        return None

    def resolve_name(self, name: str) -> str | None:
        """Resolve a name or alias to canonical machine name.

        Shared lookup used by get_machine, remove_machine, and run_command.
        """
        machines = self._load_machines()
        if name in machines:
            return name
        for mname, mdata in machines.items():
            if name in mdata.get("aliases", []):
                return mname
        return None

    def add_machine(self, machine: Machine) -> Machine:
        """Add or update a machine. Returns the stored machine."""
        if not machine.added:
            machine = replace(machine, added=datetime.now(UTC).isoformat())
        with self._lock:
            machines = self._load_machines()
            machines[machine.name] = machine.to_dict()
            self._save_machines(machines)
        return machine

    def remove_machine(self, name: str) -> bool:
        with self._lock:
            machines = self._load_machines()
            canonical = (
                name
                if name in machines
                else next(
                    (mn for mn, md in machines.items() if name in md.get("aliases", [])),
                    "",
                )
            )
            if canonical and canonical in machines:
                del machines[canonical]
                self._save_machines(machines)
                return True
        return False

    def test_machine(self, name: str) -> dict[str, Any]:
        machine = self.get_machine(name)
        if not machine:
            return {"success": False, "error": f"Machine '{name}' not found"}

        cmd = self._build_ssh_args(machine, "echo ok", timeout=self._config.connect_timeout)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._config.connect_timeout + 5,
            )
            if result.returncode == 0 and "ok" in result.stdout:
                return {"success": True, "status": "connected", "host": machine.host}
            return {
                "success": False,
                "status": "unreachable",
                "host": machine.host,
                "error": result.stderr.strip() or f"exit code {result.returncode}",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "status": "timeout",
                "host": machine.host,
                "error": "Connection timed out",
            }
        except Exception as e:
            return {"success": False, "status": "error", "host": machine.host, "error": str(e)}

    # ----- Session tracking -----

    def _load_sessions(self) -> dict[str, dict[str, Any]]:
        raw = self._read_json(self._config.sessions_file, {"sessions": {}})
        result: dict[str, dict[str, Any]] = raw.get("sessions", {})
        return result

    def _save_sessions(self, sessions: dict[str, dict[str, Any]]) -> None:
        self._write_json(self._config.sessions_file, {"sessions": sessions})

    def list_sessions(self, status: str = "active") -> dict[str, Session]:
        raw = self._load_sessions()
        return {
            sid: Session.from_dict(sid, d)
            for sid, d in raw.items()
            if not status or d.get("status") == status
        }

    def get_session(self, session_id: str) -> Session | None:
        raw = self._load_sessions()
        if session_id in raw:
            return Session.from_dict(session_id, raw[session_id])
        return None

    def register_session(self, session: Session) -> None:
        now = datetime.now(UTC).isoformat()
        if not session.started:
            session = replace(
                session,
                started=now,
                last_active=now,
                command_count=0,
                status="active",
            )
        with self._lock:
            sessions = self._load_sessions()
            sessions[session.id] = session.to_dict()
            self._save_sessions(sessions)

    def touch_session(self, session_id: str) -> None:
        with self._lock:
            sessions = self._load_sessions()
            if session_id in sessions:
                sessions[session_id]["last_active"] = datetime.now(UTC).isoformat()
                sessions[session_id]["command_count"] = (
                    sessions[session_id].get("command_count", 0) + 1
                )
                self._save_sessions(sessions)

    def close_session(self, session_id: str) -> None:
        with self._lock:
            sessions = self._load_sessions()
            if session_id in sessions:
                sessions[session_id]["status"] = "closed"
                self._save_sessions(sessions)

    def remove_session(self, session_id: str) -> None:
        with self._lock:
            sessions = self._load_sessions()
            sessions.pop(session_id, None)
            self._save_sessions(sessions)

    def kill_session(self, session_id: str) -> dict[str, Any]:
        """Kill an active SSH session by PID and close control socket.

        Note: There is a small race window between SIGTERM and the SIGKILL
        fallback check where the PID could be recycled by another process.
        In practice this is extremely unlikely (0.5s window, PIDs rarely
        recycle that fast on busy systems) but worth being aware of.
        """
        session = self.get_session(session_id)
        if not session:
            return {"success": False, "error": f"Session '{session_id}' not found"}

        results: dict[str, Any] = {"pid_killed": False, "socket_closed": False}

        # Kill the SSH process
        if session.pid:
            try:
                os.kill(session.pid, signal.SIGTERM)
                time.sleep(0.5)
                try:
                    os.kill(session.pid, 0)
                    os.kill(session.pid, signal.SIGKILL)
                except OSError:
                    pass
                results["pid_killed"] = True
            except OSError:
                results["pid_killed"] = True  # Already dead

        # Close control socket
        if session.control_path and os.path.exists(session.control_path):
            hostname = None
            try:
                machine = self.get_machine(session.machine)
                if machine:
                    hostname = machine.host
            except Exception:
                pass
            try:
                subprocess.run(
                    [
                        "ssh",
                        "-O",
                        "exit",
                        "-o",
                        f"ControlPath={session.control_path}",
                        hostname or "dummy",
                    ],
                    capture_output=True,
                    timeout=5,
                )
                results["socket_closed"] = True
            except Exception:
                pass

        self.close_session(session_id)
        return {"success": True, **results}

    def cleanup_idle(self, max_idle_minutes: int | None = None) -> dict[str, Any]:
        """Kill all sessions idle for more than max_idle_minutes."""
        threshold = (max_idle_minutes or self._config.idle_timeout_minutes) * 60
        active = self.list_sessions("active")
        # Collect IDs of sessions that need killing (single read pass)
        to_kill = []
        for sid, session in active.items():
            idle = session.idle_seconds
            if idle is not None and idle > threshold:
                to_kill.append(sid)

        # Kill processes and close control sockets (no session file reloads)
        killed: list[dict[str, Any]] = []
        for sid in to_kill:
            session = active[sid]
            result: dict[str, Any] = {"pid_killed": False, "socket_closed": False}
            # Kill the SSH process
            if session.pid:
                try:
                    os.kill(session.pid, signal.SIGTERM)
                    time.sleep(0.5)
                    try:
                        os.kill(session.pid, 0)
                        os.kill(session.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    result["pid_killed"] = True
                except OSError:
                    result["pid_killed"] = True  # Already dead
            # Close control socket
            if session.control_path and os.path.exists(session.control_path):
                try:
                    machine = self.get_machine(session.machine)
                    hostname = machine.host if machine else "dummy"
                except Exception:
                    hostname = "dummy"
                try:
                    subprocess.run(
                        [
                            "ssh",
                            "-O",
                            "exit",
                            "-o",
                            f"ControlPath={session.control_path}",
                            hostname,
                        ],
                        capture_output=True,
                        timeout=5,
                    )
                    result["socket_closed"] = True
                except Exception:
                    pass
            killed.append({"session_id": sid, "machine": session.machine, **result})

        # Batch close all sessions in one save
        self._close_sessions_batch(to_kill)
        return {"killed": killed, "count": len(killed)}

    def _close_sessions_batch(self, session_ids: list[str]) -> None:
        """Mark multiple sessions as closed in a single file write."""
        if not session_ids:
            return
        with self._lock:
            sessions = self._load_sessions()
            for sid in session_ids:
                if sid in sessions:
                    sessions[sid]["status"] = "closed"
            self._save_sessions(sessions)

    def prune_closed(self, max_age_hours: int | None = None) -> int:
        """Remove closed sessions older than max_age_hours."""
        hours = max_age_hours or self._config.closed_prune_hours
        with self._lock:
            raw = self._load_sessions()
            now = datetime.now(UTC)
            to_remove = []
            for sid, sdata in raw.items():
                if sdata.get("status") != "active":
                    try:
                        started = datetime.fromisoformat(sdata.get("started", ""))
                        if (now - started).total_seconds() > hours * 3600:
                            to_remove.append(sid)
                    except (ValueError, TypeError):
                        pass
            for sid in to_remove:
                del raw[sid]
            if to_remove:
                self._save_sessions(raw)
        return len(to_remove)

    # ----- SSH execution -----

    def _build_ssh_args(
        self,
        machine: Machine,
        command: str,
        control_path: str = "",
        timeout: int = 30,
    ) -> list[str]:
        cmd = [
            "ssh",
            "-o",
            f"ConnectTimeout={min(timeout, 10)}",
            "-o",
            f"StrictHostKeyChecking={self._config.strict_host_key_checking}",
            "-o",
            "BatchMode=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "RequestTTY=no",
            "-p",
            str(machine.port),
        ]
        if machine.key:
            cmd.extend(["-i", machine.key])
        if control_path:
            cmd.extend(
                [
                    "-o",
                    "ControlMaster=auto",
                    "-o",
                    f"ControlPath={control_path}",
                    "-o",
                    "ControlPersist=300",
                ]
            )
        cmd.append(f"{machine.user}@{machine.host}")
        # Wrap in bash -c to ensure bash features (pipefail, [[, etc.) work
        # regardless of the remote user's default shell.  set -o pipefail
        # makes pipeline exit codes predictable (non-zero if any component
        # fails, not just the last command).
        wrapped = f"set -o pipefail; {command}"
        cmd.extend(["bash", "-c", shlex.quote(wrapped)])
        return cmd

    def run_command(
        self,
        machine_name: str,
        command: str,
        timeout: int | None = None,
        new_session: bool = False,
        background: bool = False,
        max_output_chars: int = 50_000,
    ) -> dict[str, Any]:
        """Run a command on a remote machine via SSH.

        Args:
            machine_name: Name or alias of the target machine.
            command: Shell command to execute remotely.
            timeout: Override for the command timeout (seconds).
            new_session: If True, skip SSH multiplexing / control socket.
            background: If True, launch via Popen and return immediately.
            max_output_chars: Truncate stdout/stderr beyond this length.
        """
        timeout = timeout or self._config.command_timeout

        machine = self.get_machine(machine_name)
        if not machine:
            return {"success": False, "error": f"Machine '{machine_name}' not found."}

        canonical = machine.name

        session_id = f"ssh_{canonical}_{uuid.uuid4().hex[:8]}"
        control_path = "" if new_session else str(self._config.socket_dir / f"{canonical}.sock")
        ssh_args = self._build_ssh_args(machine, command, control_path, timeout)

        start_time = time.monotonic()

        # ---- background path ----
        if background:
            try:
                proc = subprocess.Popen(
                    ssh_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._processes[session_id] = proc
                self.register_session(
                    Session(
                        id=session_id, machine=canonical, pid=proc.pid, control_path=control_path
                    )
                )
                elapsed = round(time.monotonic() - start_time, 2)
                self._log_command(
                    canonical, command, exit_code=None, elapsed=elapsed, session_id=session_id
                )
                return {
                    "success": True,
                    "background": True,
                    "pid": proc.pid,
                    "machine": canonical,
                    "session_id": session_id,
                }
            except Exception as e:
                logger.debug("run_command (bg) failed for %s: %s", canonical, e, exc_info=True)
                return {"success": False, "error": str(e), "exit_code": -1, "machine": canonical}

        # ---- synchronous path ----
        try:
            result = subprocess.run(
                ssh_args,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
            elapsed = round(time.monotonic() - start_time, 2)

            stdout = self._truncate_output(result.stdout, max_output_chars)
            stderr = self._truncate_output(result.stderr, max_output_chars)

            self._log_command(canonical, command, result.returncode, elapsed, session_id)
            return {
                "success": result.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
                "elapsed_secs": elapsed,
                "machine": canonical,
                "session_id": session_id,
            }

        except subprocess.TimeoutExpired:
            elapsed = round(time.monotonic() - start_time, 2)
            self._log_command(
                canonical, command, exit_code=-1, elapsed=elapsed, session_id=session_id
            )
            return {
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "exit_code": -1,
                "elapsed_secs": elapsed,
                "machine": canonical,
                "session_id": session_id,
            }
        except Exception as e:
            logger.debug("run_command failed for %s: %s", canonical, e, exc_info=True)
            elapsed = round(time.monotonic() - start_time, 2)
            self._log_command(
                canonical, command, exit_code=-1, elapsed=elapsed, session_id=session_id
            )
            return {"success": False, "error": str(e), "exit_code": -1, "machine": canonical}

    # ----- Output helpers -----

    @staticmethod
    def _truncate_output(text: str, max_chars: int) -> str:
        """Return *text* unchanged if within *max_chars*, else truncate and annotate."""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + f"\n[truncated \u2014 {len(text)} total chars]"

    # ----- Background process helpers -----

    def poll_session(self, session_id: str) -> dict[str, Any]:
        """Check if a background process is still running.

        Returns a dict with ``running`` (bool) and, when the process has
        finished, the collected stdout/stderr plus the exit code.
        """
        proc = self._processes.get(session_id)
        if proc is None:
            return {"success": False, "error": f"No background process for session '{session_id}'"}
        exit_code = proc.poll()
        if exit_code is None:
            return {"success": True, "session_id": session_id, "running": True}
        # Process finished — collect output
        stdout = (proc.stdout.read() or b"").decode(errors="replace") if proc.stdout else ""
        stderr = (proc.stderr.read() or b"").decode(errors="replace") if proc.stderr else ""
        self._processes.pop(session_id, None)
        self.close_session(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "running": False,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        }

    def read_output(self, session_id: str) -> dict[str, Any]:
        """Read stdout/stderr from a completed background process.

        Unlike :meth:`poll_session` this does **not** check whether the
        process is still running — it is intended for callers who already
        know the process has finished.
        """
        proc = self._processes.get(session_id)
        if proc is None:
            return {"success": False, "error": f"No background process for session '{session_id}'"}
        exit_code = proc.poll()
        if exit_code is None:
            return {
                "success": False,
                "error": f"Process for session '{session_id}' is still running",
            }
        stdout = (proc.stdout.read() or b"").decode(errors="replace") if proc.stdout else ""
        stderr = (proc.stderr.read() or b"").decode(errors="replace") if proc.stderr else ""
        self._processes.pop(session_id, None)
        self.close_session(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        }

    # ----- Audit log -----

    def _log_command(
        self,
        machine: str,
        command: str,
        exit_code: int | None,
        elapsed: float,
        session_id: str,
    ) -> None:
        """Append a single JSONL line to the command audit log."""
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "machine": machine,
            "command": command,
            "exit_code": exit_code,
            "elapsed_secs": elapsed,
            "session_id": session_id,
        }
        try:
            self._config.data_dir.mkdir(parents=True, exist_ok=True)
            with self._audit_log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            logger.debug("Failed to append to audit log %s", self._audit_log_path, exc_info=True)

    def list_command_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the last *limit* entries from the command audit log."""
        if not self._audit_log_path.exists():
            return []
        lines = self._audit_log_path.read_text(encoding="utf-8").splitlines()
        tail = lines[-limit:]
        entries: list[dict[str, Any]] = []
        for line in tail:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return entries

    # ----- Background idle checker -----

    def start_idle_checker(self) -> None:
        if self._checker_thread is not None and self._checker_thread.is_alive():
            return

        _prune_counter: list[int] = [0]  # mutable counter shared by closure
        _PRUNE_EVERY = 10  # prune every 10 idle-check cycles

        def _loop() -> None:
            while not self._checker_event.is_set():
                with contextlib.suppress(Exception):
                    self.cleanup_idle()
                _prune_counter[0] += 1
                if _prune_counter[0] >= _PRUNE_EVERY:
                    _prune_counter[0] = 0
                    with contextlib.suppress(Exception):
                        self.prune_closed()
                time.sleep(self._config.idle_check_interval)

        self._checker_event.clear()
        self._checker_thread = threading.Thread(target=_loop, daemon=True)
        self._checker_thread.start()

    def stop_idle_checker(self) -> None:
        self._checker_event.set()
