"""Core SSH manager — single class owning all state and operations.

Consolidates machine registry, session tracking, and SSH execution.
No module-level mutable state — everything lives on the instance.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from .config import DEFAULT_CONFIG, SSHConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Machine:
    """A registered remote host."""

    name: str
    host: str
    user: str = "root"
    port: int = 22
    key: str = ""
    aliases: list[str] | None = None
    tags: list[str] | None = None
    description: str = ""
    added: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "user": self.user,
            "port": self.port,
            "key": self.key,
            "aliases": self.aliases or [],
            "tags": self.tags or [],
            "description": self.description,
            "added": self.added,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Machine:
        return cls(
            name=name,
            host=data.get("host", ""),
            user=data.get("user", "root"),
            port=data.get("port", 22),
            key=data.get("key", ""),
            aliases=data.get("aliases", []),
            tags=data.get("tags", []),
            description=data.get("description", ""),
            added=data.get("added", ""),
        )


@dataclass
class Session:
    """An active or closed SSH session."""

    id: str
    machine: str
    pid: int = 0
    control_path: str = ""
    started: str = ""
    last_active: str = ""
    command_count: int = 0
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine": self.machine,
            "pid": self.pid,
            "control_path": self.control_path,
            "started": self.started,
            "last_active": self.last_active,
            "command_count": self.command_count,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, sid: str, data: dict[str, Any]) -> Session:
        return cls(
            id=sid,
            machine=data.get("machine", ""),
            pid=data.get("pid", 0),
            control_path=data.get("control_path", ""),
            started=data.get("started", ""),
            last_active=data.get("last_active", ""),
            command_count=data.get("command_count", 0),
            status=data.get("status", "active"),
        )

    @property
    def idle_seconds(self) -> int | None:
        if self.status != "active" or not self.last_active:
            return None
        try:
            last = datetime.fromisoformat(self.last_active)
            return int((datetime.now(UTC) - last).total_seconds())
        except (ValueError, TypeError):
            return None

    @property
    def idle_human(self) -> str:
        s = self.idle_seconds
        if s is None:
            return "unknown"
        if s < 60:
            return f"{s}s"
        if s < 3600:
            return f"{s // 60}m {s % 60}s"
        return f"{s // 3600}h {(s % 3600) // 60}m"


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

    @property
    def config(self) -> SSHConfig:
        return self._config

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
        raw: dict[str, Any] = self._read_json(self._config.machines_file, {"machines": {}})
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
        """Resolve a name or alias to canonical machine name."""
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
            machine = Machine(
                name=machine.name,
                host=machine.host,
                user=machine.user,
                port=machine.port,
                key=machine.key,
                aliases=machine.aliases,
                tags=machine.tags,
                description=machine.description,
                added=datetime.now(UTC).isoformat(),
            )
        with self._lock:
            machines = self._load_machines()
            machines[machine.name] = machine.to_dict()
            self._save_machines(machines)
        return machine

    def remove_machine(self, name: str) -> bool:
        with self._lock:
            machines = self._load_machines()
            canonical = None
            if name in machines:
                canonical = name
            else:
                for mname, mdata in machines.items():
                    if name in mdata.get("aliases", []):
                        canonical = mname
                        break
            if canonical and canonical in machines:
                del machines[canonical]
                self._save_machines(machines)
                return True
        return False

    def test_machine(self, name: str) -> dict[str, Any]:
        machine = self.get_machine(name)
        if not machine:
            return {"success": False, "error": f"Machine '{name}' not found"}

        cmd = [
            "ssh",
            "-o",
            f"ConnectTimeout={self._config.connect_timeout}",
            "-o",
            f"StrictHostKeyChecking={self._config.strict_host_key_checking}",
            "-o",
            "BatchMode=yes",
            "-p",
            str(machine.port),
        ]
        if machine.key:
            cmd.extend(["-i", machine.key])
        cmd.append(f"{machine.user}@{machine.host}")
        cmd.append("echo ok")

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
        raw: dict[str, Any] = self._read_json(self._config.sessions_file, {"sessions": {}})
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
            session = Session(
                id=session.id,
                machine=session.machine,
                pid=session.pid,
                control_path=session.control_path,
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
        """Kill an active SSH session by PID and close control socket."""
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
            try:
                subprocess.run(
                    ["ssh", "-O", "exit", "-o", f"ControlPath={session.control_path}", "dummy"],
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
        killed = []
        for sid, session in active.items():
            idle = session.idle_seconds
            if idle is not None and idle > threshold:
                result = self.kill_session(sid)
                killed.append({"session_id": sid, "machine": session.machine, **result})
        return {"killed": killed, "count": len(killed)}

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
                    "ControlPersist=no",
                ]
            )
        cmd.append(f"{machine.user}@{machine.host}")
        cmd.append(command)
        return cmd

    def run_command(
        self,
        machine_name: str,
        command: str,
        timeout: int | None = None,
        new_session: bool = False,
    ) -> dict[str, Any]:
        """Run a command on a remote machine via SSH."""
        timeout = timeout or self._config.command_timeout
        self._config.ensure_dirs()

        canonical = self.resolve_name(machine_name)
        if not canonical:
            return {"success": False, "error": f"Machine '{machine_name}' not found in registry."}

        machine = self.get_machine(canonical)
        if not machine:
            return {"success": False, "error": f"Machine '{machine_name}' not found."}

        session_id = f"ssh_{canonical}_{uuid.uuid4().hex[:8]}"
        control_path = "" if new_session else str(self._config.socket_dir / f"{canonical}.sock")
        ssh_args = self._build_ssh_args(machine, command, control_path, timeout)

        start_time = time.monotonic()
        try:
            result = subprocess.run(
                ssh_args,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
            elapsed = round(time.monotonic() - start_time, 2)

            self.register_session(
                Session(id=session_id, machine=canonical, pid=0, control_path=control_path)
            )
            self.close_session(session_id)

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
            self.register_session(
                Session(id=session_id, machine=canonical, pid=0, control_path=control_path)
            )
            self.close_session(session_id)
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
            return {"success": False, "error": str(e), "exit_code": -1, "machine": canonical}

    # ----- Background idle checker -----

    def start_idle_checker(self) -> None:
        if self._checker_event.is_set():
            return

        def _loop() -> None:
            self._checker_event.set()
            while not self._checker_event.is_set():
                with contextlib.suppress(Exception):
                    self.cleanup_idle()
                time.sleep(self._config.idle_check_interval)

        self._checker_thread = threading.Thread(target=_loop, daemon=True)
        self._checker_thread.start()

    def stop_idle_checker(self) -> None:
        self._checker_event.set()
