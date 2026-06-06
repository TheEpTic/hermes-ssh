"""Machine registry — add/list/remove/test machines stored in data/machines.json."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


DATA_DIR = Path(__file__).parent / "data"
MACHINES_FILE = DATA_DIR / "machines.json"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> Dict[str, Any]:
    _ensure_data_dir()
    if MACHINES_FILE.exists():
        try:
            return json.loads(MACHINES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {"machines": {}}
    return {"machines": {}}


def _save(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    MACHINES_FILE.write_text(json.dumps(data, indent=2) + "\n")


def list_machines() -> Dict[str, Any]:
    """Return all registered machines."""
    return _load()["machines"]


def get_machine(name: str) -> Optional[Dict[str, Any]]:
    """Get a machine by name or alias."""
    data = _load()
    # Direct match
    if name in data["machines"]:
        return data["machines"][name]
    # Alias match
    for machine_name, machine in data["machines"].items():
        aliases = machine.get("aliases", [])
        if name in aliases:
            return machine
    return None


def resolve_name(name: str) -> Optional[str]:
    """Resolve a name or alias to the canonical machine name."""
    data = _load()
    if name in data["machines"]:
        return name
    for machine_name, machine in data["machines"].items():
        if name in machine.get("aliases", []):
            return machine_name
    return None


def add_machine(
    name: str,
    host: str,
    user: str = "root",
    port: int = 22,
    key: str = "",
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
    description: str = "",
) -> Dict[str, Any]:
    """Add or update a machine in the registry."""
    data = _load()
    machine = {
        "host": host,
        "user": user,
        "port": port,
        "key": key,
        "aliases": aliases or [],
        "tags": tags or [],
        "description": description,
        "added": datetime.now(timezone.utc).isoformat(),
    }
    data["machines"][name] = machine
    _save(data)
    return machine


def remove_machine(name: str) -> bool:
    """Remove a machine by name or alias. Returns True if removed."""
    data = _load()
    canonical = resolve_name(name)
    if canonical and canonical in data["machines"]:
        del data["machines"][canonical]
        _save(data)
        return True
    return False


def test_machine(name: str, connect_timeout: int = 5) -> Dict[str, Any]:
    """Test connectivity to a machine. Returns status dict."""
    machine = get_machine(name)
    if not machine:
        return {"success": False, "error": f"Machine '{name}' not found in registry"}

    host = machine["host"]
    user = machine["user"]
    port = machine["port"]
    key = machine.get("key", "")

    cmd = [
        "ssh",
        "-o", f"ConnectTimeout={connect_timeout}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-p", str(port),
    ]
    if key:
        cmd.extend(["-i", key])
    cmd.append(f"{user}@{host}")
    cmd.append("echo ok")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=connect_timeout + 5
        )
        if result.returncode == 0 and "ok" in result.stdout:
            return {"success": True, "status": "connected", "host": host}
        return {
            "success": False,
            "status": "unreachable",
            "host": host,
            "error": result.stderr.strip() or f"exit code {result.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "status": "timeout", "host": host, "error": "Connection timed out"}
    except Exception as e:
        return {"success": False, "status": "error", "host": host, "error": str(e)}
