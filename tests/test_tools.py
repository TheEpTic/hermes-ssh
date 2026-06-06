"""Tests for ssh_tools.handlers — handler functions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import ssh_tools
from ssh_tools.handlers import handle_ssh_machines, handle_ssh_sessions, handle_ssh_terminal
from ssh_tools.handlers.slash import create_slash_handler
from ssh_tools.models import Machine, Session

from .conftest import _make_manager

if TYPE_CHECKING:
    from pathlib import Path


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


# ---------------------------------------------------------------------------
# Slash command handler (create_slash_handler)
# ---------------------------------------------------------------------------


def test_slash_no_args_shows_help(tmp_path: Path) -> None:
    ssh_tools._manager = _make_manager(tmp_path)
    _handle_slash = create_slash_handler(ssh_tools._get_manager)
    result = _handle_slash("")
    assert result is not None
    assert "ssh" in result.lower() or "SSH" in result


def test_slash_help_keyword(tmp_path: Path) -> None:
    ssh_tools._manager = _make_manager(tmp_path)
    _handle_slash = create_slash_handler(ssh_tools._get_manager)
    result = _handle_slash("help")
    assert result is not None
    assert "ssh" in result.lower() or "SSH" in result


def test_slash_test_no_machines(tmp_path: Path) -> None:
    ssh_tools._manager = _make_manager(tmp_path)
    _handle_slash = create_slash_handler(ssh_tools._get_manager)
    result = _handle_slash("test")
    assert result is not None
    assert "No machines" in result


def test_slash_cleanup_no_idle(tmp_path: Path) -> None:
    ssh_tools._manager = _make_manager(tmp_path)
    _handle_slash = create_slash_handler(ssh_tools._get_manager)
    result = _handle_slash("cleanup")
    assert result is not None
    assert "No idle" in result


def test_slash_unknown_machine(tmp_path: Path) -> None:
    ssh_tools._manager = _make_manager(tmp_path)
    _handle_slash = create_slash_handler(ssh_tools._get_manager)
    result = _handle_slash("nonexistent")
    assert result is not None
    assert "not found" in result.lower()


def test_slash_inspect_machine(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(
        Machine(
            name="host1", host="10.0.0.1", user="admin", port=2222, aliases=["h1"], tags=["dev"]
        )
    )
    ssh_tools._manager = mgr
    _handle_slash = create_slash_handler(ssh_tools._get_manager)
    result = _handle_slash("host1")
    assert result is not None
    assert "host1" in result
    assert "10.0.0.1" in result
    assert "admin" in result


def test_slash_inspect_by_alias(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="host1", host="10.0.0.1", aliases=["h1"]))
    ssh_tools._manager = mgr
    _handle_slash = create_slash_handler(ssh_tools._get_manager)
    result = _handle_slash("h1")
    assert result is not None
    assert "host1" in result
