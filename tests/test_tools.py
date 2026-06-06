"""Tests for ssh_tools.tools — handler functions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ssh_tools.config import SSHConfig
from ssh_tools.manager import Machine, SSHManager
from ssh_tools.tools import handle_ssh_machines, handle_ssh_sessions, handle_ssh_terminal

if TYPE_CHECKING:
    from pathlib import Path


def _make_manager(tmp_path: Path) -> SSHManager:
    return SSHManager(SSHConfig(data_dir=tmp_path))


# ---------------------------------------------------------------------------
# handle_ssh_terminal
# ---------------------------------------------------------------------------


def test_ssh_terminal_missing_machine(tmp_path: Path) -> None:
    handler = handle_ssh_terminal(_make_manager(tmp_path))
    result = json.loads(handler({"command": "echo hi"}))
    assert result["success"] is False
    assert "machine is required" in result["error"]


def test_ssh_terminal_missing_command(tmp_path: Path) -> None:
    handler = handle_ssh_terminal(_make_manager(tmp_path))
    result = json.loads(handler({"machine": "host1"}))
    assert result["success"] is False
    assert "command is required" in result["error"]


def test_ssh_terminal_nonexistent_machine(tmp_path: Path) -> None:
    handler = handle_ssh_terminal(_make_manager(tmp_path))
    result = json.loads(handler({"machine": "nope", "command": "echo hi"}))
    assert result["success"] is False
    assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# handle_ssh_machines
# ---------------------------------------------------------------------------


def test_machines_list_empty(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(handler({"action": "list"}))
    assert result["success"] is True
    assert result["count"] == 0


def test_machines_list_with_data(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="h1", host="1.1.1.1", user="admin", tags=["test"]))
    handler = handle_ssh_machines(mgr)

    result = json.loads(handler({"action": "list"}))
    assert result["success"] is True
    assert result["count"] == 1
    assert "h1" in result["machines"]
    assert result["machines"]["h1"]["host"] == "1.1.1.1"
    assert result["machines"]["h1"]["tags"] == ["test"]


def test_machines_add(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(
        handler(
            {
                "action": "add",
                "name": "host1",
                "host": "10.0.0.1",
                "user": "admin",
                "port": 2222,
            }
        )
    )
    assert result["success"] is True
    assert result["machine"]["host"] == "10.0.0.1"


def test_machines_add_missing_fields(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(handler({"action": "add"}))
    assert result["success"] is False
    assert "required" in result["error"]


def test_machines_add_missing_host(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(handler({"action": "add", "name": "h1"}))
    assert result["success"] is False
    assert "required" in result["error"]


def test_machines_remove(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="host1", host="10.0.0.1"))
    handler = handle_ssh_machines(mgr)

    result = json.loads(handler({"action": "remove", "name": "host1"}))
    assert result["success"] is True


def test_machines_remove_missing_name(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(handler({"action": "remove"}))
    assert result["success"] is False
    assert "required" in result["error"]


def test_machines_inspect(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="host1", host="10.0.0.1", aliases=["h1"]))
    handler = handle_ssh_machines(mgr)

    result = json.loads(handler({"action": "inspect", "name": "h1"}))
    assert result["success"] is True
    assert result["name"] == "host1"


def test_machines_inspect_missing_name(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(handler({"action": "inspect"}))
    assert result["success"] is False
    assert "required" in result["error"]


def test_machines_inspect_nonexistent(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(handler({"action": "inspect", "name": "nope"}))
    assert result["success"] is False
    assert "not found" in result["error"]


def test_machines_unknown_action(tmp_path: Path) -> None:
    handler = handle_ssh_machines(_make_manager(tmp_path))
    result = json.loads(handler({"action": "bogus"}))
    assert result["success"] is False
    assert "Unknown action" in result["error"]


# ---------------------------------------------------------------------------
# handle_ssh_sessions
# ---------------------------------------------------------------------------


def test_sessions_list_empty(tmp_path: Path) -> None:
    handler = handle_ssh_sessions(_make_manager(tmp_path))
    result = json.loads(handler({"action": "list"}))
    assert result["success"] is True
    assert result["count"] == 0


def test_sessions_list_with_data(tmp_path: Path) -> None:
    from ssh_tools.manager import Session

    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    handler = handle_ssh_sessions(mgr)

    result = json.loads(handler({"action": "list"}))
    assert result["success"] is True
    assert result["count"] == 1
    assert "s1" in result["sessions"]
    assert "idle_secs" in result["sessions"]["s1"]
    assert "idle_human" in result["sessions"]["s1"]


def test_sessions_kill_missing_id(tmp_path: Path) -> None:
    handler = handle_ssh_sessions(_make_manager(tmp_path))
    result = json.loads(handler({"action": "kill"}))
    assert result["success"] is False
    assert "session_id is required" in result["error"]


def test_sessions_kill_nonexistent(tmp_path: Path) -> None:
    handler = handle_ssh_sessions(_make_manager(tmp_path))
    result = json.loads(handler({"action": "kill", "session_id": "nope"}))
    assert result["success"] is False


def test_sessions_cleanup(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    handler = handle_ssh_sessions(mgr)

    result = json.loads(handler({"action": "cleanup"}))
    assert result["success"] is True
    assert result["cleaned"] == 0


def test_sessions_prune(tmp_path: Path) -> None:
    handler = handle_ssh_sessions(_make_manager(tmp_path))
    result = json.loads(handler({"action": "prune"}))
    assert result["success"] is True
    assert result["pruned"] == 0


def test_sessions_unknown_action(tmp_path: Path) -> None:
    handler = handle_ssh_sessions(_make_manager(tmp_path))
    result = json.loads(handler({"action": "bogus"}))
    assert result["success"] is False
    assert "Unknown action" in result["error"]
