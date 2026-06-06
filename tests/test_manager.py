"""Tests for ssh_tools.manager — Machine, Session, SSHManager."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from ssh_tools.models import Machine, Session

from .conftest import _make_manager

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Machine dataclass
# ---------------------------------------------------------------------------


def test_machine_to_dict_roundtrip() -> None:
    m = Machine(name="test", host="10.0.0.1", user="admin", port=2222, aliases=["t"], tags=["dev"])
    d = m.to_dict()
    m2 = Machine.from_dict("test", d)
    assert m2.name == "test"
    assert m2.host == "10.0.0.1"
    assert m2.user == "admin"
    assert m2.port == 2222
    assert m2.aliases == ["t"]
    assert m2.tags == ["dev"]


def test_machine_defaults() -> None:
    m = Machine(name="x", host="1.2.3.4")
    assert m.user == "root"
    assert m.port == 22
    assert m.key == ""
    assert m.aliases is None
    assert m.tags is None
    assert m.description == ""
    assert m.added == ""


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------


def test_session_idle_seconds_active() -> None:
    now = datetime.now(UTC)
    s = Session(
        id="s1",
        machine="host1",
        started=now.isoformat(),
        last_active=(now - timedelta(minutes=5)).isoformat(),
        status="active",
    )
    idle = s.idle_seconds
    assert idle is not None
    assert 290 <= idle <= 310  # ~5 minutes


def test_session_idle_seconds_closed() -> None:
    s = Session(id="s1", machine="h", status="closed")
    assert s.idle_seconds is None


def test_session_idle_seconds_empty_last_active() -> None:
    s = Session(id="s1", machine="h", status="active", last_active="")
    assert s.idle_seconds is None


def test_session_idle_seconds_invalid_last_active() -> None:
    s = Session(id="s1", machine="h", status="active", last_active="not-a-date")
    assert s.idle_seconds is None


def test_session_idle_human_seconds() -> None:
    now = datetime.now(UTC)
    s = Session(
        id="s1",
        machine="h",
        status="active",
        last_active=(now - timedelta(seconds=30)).isoformat(),
    )
    assert s.idle_human == "30s"


def test_session_idle_human_minutes() -> None:
    now = datetime.now(UTC)
    s = Session(
        id="s1",
        machine="h",
        status="active",
        last_active=(now - timedelta(minutes=5, seconds=30)).isoformat(),
    )
    assert s.idle_human == "5m 30s"


def test_session_idle_human_hours() -> None:
    now = datetime.now(UTC)
    s = Session(
        id="s1",
        machine="h",
        status="active",
        last_active=(now - timedelta(hours=2, minutes=15)).isoformat(),
    )
    assert s.idle_human == "2h 15m"


def test_session_idle_human_unknown() -> None:
    s = Session(id="s1", machine="h", status="closed")
    assert s.idle_human == "unknown"


def test_session_to_dict_roundtrip() -> None:
    s = Session(id="s1", machine="h", pid=123, control_path="/tmp/c.sock", status="active")
    d = s.to_dict()
    s2 = Session.from_dict("s1", d)
    assert s2.id == "s1"
    assert s2.machine == "h"
    assert s2.pid == 123
    assert s2.control_path == "/tmp/c.sock"
    assert s2.status == "active"


# ---------------------------------------------------------------------------
# SSHManager — machine registry
# ---------------------------------------------------------------------------


def test_add_and_get_machine(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    m = Machine(name="host1", host="10.0.0.1", user="admin", port=2222)
    mgr.add_machine(m)

    got = mgr.get_machine("host1")
    assert got is not None
    assert got.host == "10.0.0.1"
    assert got.user == "admin"
    assert got.port == 2222


def test_add_machine_sets_timestamp(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    m = mgr.add_machine(Machine(name="h", host="1.1.1.1"))
    assert m.added
    # Verify it's a valid ISO timestamp
    dt = datetime.fromisoformat(m.added)
    assert dt.year >= 2026


def test_add_machine_overwrite(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="h", host="1.1.1.1", user="old"))
    mgr.add_machine(
        Machine(name="h", host="2.2.2.2", user="new", added="2026-01-01T00:00:00+00:00")
    )

    got = mgr.get_machine("h")
    assert got is not None
    assert got.host == "2.2.2.2"
    assert got.user == "new"
    # Preserved original added timestamp
    assert got.added == "2026-01-01T00:00:00+00:00"


def test_resolve_alias(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="host1", host="10.0.0.1", aliases=["h1"]))

    assert mgr.resolve_name("h1") == "host1"
    assert mgr.resolve_name("host1") == "host1"
    assert mgr.resolve_name("nope") is None


def test_get_machine_by_alias(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="host1", host="10.0.0.1", aliases=["h1"]))

    got = mgr.get_machine("h1")
    assert got is not None
    assert got.name == "host1"


def test_list_machines(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="a", host="1.1.1.1"))
    mgr.add_machine(Machine(name="b", host="2.2.2.2"))

    machines = mgr.list_machines()
    assert len(machines) == 2
    assert "a" in machines
    assert "b" in machines


def test_remove_machine(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="host1", host="10.0.0.1"))

    assert mgr.remove_machine("host1") is True
    assert mgr.get_machine("host1") is None


def test_remove_machine_by_alias(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.add_machine(Machine(name="host1", host="10.0.0.1", aliases=["h1"]))

    assert mgr.remove_machine("h1") is True
    assert mgr.get_machine("host1") is None


def test_remove_nonexistent(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    assert mgr.remove_machine("nope") is False


def test_get_nonexistent(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    assert mgr.get_machine("nope") is None


def test_machine_persists_across_instances(tmp_path: Path) -> None:
    mgr1 = _make_manager(tmp_path)
    mgr1.add_machine(Machine(name="h", host="1.1.1.1"))

    mgr2 = _make_manager(tmp_path)
    got = mgr2.get_machine("h")
    assert got is not None
    assert got.host == "1.1.1.1"


# ---------------------------------------------------------------------------
# SSHManager — session tracking
# ---------------------------------------------------------------------------


def test_register_and_list_sessions(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1", pid=100))

    active = mgr.list_sessions("active")
    assert len(active) == 1
    assert "s1" in active


def test_register_session_sets_timestamps(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))

    s = mgr.get_session("s1")
    assert s is not None
    assert s.started
    assert s.last_active
    assert s.status == "active"


def test_register_session_preserves_existing_started(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    custom_time = "2026-01-01T00:00:00+00:00"
    mgr.register_session(Session(id="s1", machine="host1", started=custom_time))

    s = mgr.get_session("s1")
    assert s is not None
    assert s.started == custom_time


def test_get_session(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))

    s = mgr.get_session("s1")
    assert s is not None
    assert s.machine == "host1"
    assert s.status == "active"


def test_close_session(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    mgr.close_session("s1")

    s = mgr.get_session("s1")
    assert s is not None
    assert s.status == "closed"

    active = mgr.list_sessions("active")
    assert "s1" not in active


def test_remove_session(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    mgr.remove_session("s1")

    assert mgr.get_session("s1") is None


def test_touch_session(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))

    mgr.touch_session("s1")
    s = mgr.get_session("s1")
    assert s is not None
    assert s.command_count == 1

    mgr.touch_session("s1")
    s = mgr.get_session("s1")
    assert s is not None
    assert s.command_count == 2


def test_list_sessions_all_statuses(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    mgr.register_session(Session(id="s2", machine="host1"))
    mgr.close_session("s2")

    all_sessions = mgr.list_sessions(status="")
    assert len(all_sessions) == 2

    closed = mgr.list_sessions("closed")
    assert len(closed) == 1
    assert "s2" in closed


def test_cleanup_idle(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))

    # Manually age the session
    with mgr._lock:
        sessions = mgr._load_sessions()
        old_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        sessions["s1"]["last_active"] = old_time
        mgr._save_sessions(sessions)

    result = mgr.cleanup_idle(max_idle_minutes=30)
    assert result["count"] == 1

    s = mgr.get_session("s1")
    assert s is not None
    assert s.status == "closed"


def test_cleanup_idle_skips_recent(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))

    result = mgr.cleanup_idle(max_idle_minutes=30)
    assert result["count"] == 0

    s = mgr.get_session("s1")
    assert s is not None
    assert s.status == "active"


def test_cleanup_idle_boundary(tmp_path: Path) -> None:
    """Session exactly at threshold should NOT be killed (> not >=)."""
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))

    # Set last_active to exactly 30 minutes ago
    with mgr._lock:
        sessions = mgr._load_sessions()
        exact_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        sessions["s1"]["last_active"] = exact_time
        mgr._save_sessions(sessions)

    result = mgr.cleanup_idle(max_idle_minutes=30)
    assert result["count"] == 0  # > threshold, not >=


def test_cleanup_idle_uses_config_default(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    # Config default is 30 minutes
    mgr.register_session(Session(id="s1", machine="host1"))

    with mgr._lock:
        sessions = mgr._load_sessions()
        old_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        sessions["s1"]["last_active"] = old_time
        mgr._save_sessions(sessions)

    result = mgr.cleanup_idle()  # No arg = use config default
    assert result["count"] == 1


def test_prune_closed(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    mgr.close_session("s1")

    with mgr._lock:
        sessions = mgr._load_sessions()
        old_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        sessions["s1"]["started"] = old_time
        mgr._save_sessions(sessions)

    count = mgr.prune_closed(max_age_hours=24)
    assert count == 1
    assert mgr.get_session("s1") is None


def test_prune_closed_keeps_recent(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    mgr.close_session("s1")

    count = mgr.prune_closed(max_age_hours=24)
    assert count == 0


def test_prune_closed_skips_active(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))

    with mgr._lock:
        sessions = mgr._load_sessions()
        old_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        sessions["s1"]["started"] = old_time
        mgr._save_sessions(sessions)

    count = mgr.prune_closed(max_age_hours=24)
    assert count == 0  # Active sessions not pruned


def test_prune_closed_with_invalid_date(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    mgr.close_session("s1")

    with mgr._lock:
        sessions = mgr._load_sessions()
        sessions["s1"]["started"] = "not-a-date"
        mgr._save_sessions(sessions)

    count = mgr.prune_closed(max_age_hours=24)
    assert count == 0  # Invalid date = skip, don't crash


def test_prune_closed_uses_config_default(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1"))
    mgr.close_session("s1")

    with mgr._lock:
        sessions = mgr._load_sessions()
        old_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        sessions["s1"]["started"] = old_time
        mgr._save_sessions(sessions)

    count = mgr.prune_closed()  # No arg = config default (24h)
    assert count == 1


def test_multiple_sessions_same_machine(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.register_session(Session(id="s1", machine="host1", pid=100))
    mgr.register_session(Session(id="s2", machine="host1", pid=200))

    active = mgr.list_sessions("active")
    assert len(active) == 2
    assert all(s.machine == "host1" for s in active.values())


# ---------------------------------------------------------------------------
# SSHManager — JSON corruption handling
# ---------------------------------------------------------------------------


def test_read_json_corrupt_file(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    corrupt_file = tmp_path / "machines.json"
    corrupt_file.write_text("NOT JSON {{{")

    result = mgr._read_json(corrupt_file, {"default": True})
    assert result == {"default": True}


def test_read_json_missing_file(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    result = mgr._read_json(tmp_path / "nonexistent.json", {"fallback": True})
    assert result == {"fallback": True}


def test_write_json_atomic(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    target = tmp_path / "test.json"

    mgr._write_json(target, {"key": "value"})
    assert json.loads(target.read_text()) == {"key": "value"}

    # Verify no leftover temp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# SSHManager — SSH execution
# ---------------------------------------------------------------------------


def test_run_command_nonexistent_machine(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    result = mgr.run_command("nope", "echo hi")
    assert result["success"] is False
    assert "not found" in result["error"]


def test_build_ssh_args(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    machine = Machine(name="h", host="10.0.0.1", user="admin", port=2222, key="~/.ssh/test")
    args = mgr._build_ssh_args(machine, "uptime", "/tmp/c.sock", timeout=30)

    assert args[0] == "ssh"
    assert "-p" in args
    assert "2222" in args
    assert "-i" in args
    assert "~/.ssh/test" in args
    assert "ControlMaster=auto" in args
    assert "admin@10.0.0.1" in args
    # Command is wrapped in bash -c 'set -o pipefail; ...'
    assert "bash" in args
    assert "-c" in args
    assert "pipefail" in args[-1]
    assert "uptime" in args[-1]


def test_build_ssh_args_no_control_path(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    machine = Machine(name="h", host="10.0.0.1")
    args = mgr._build_ssh_args(machine, "uptime", "", timeout=30)

    assert "ControlMaster" not in args


def test_build_ssh_args_no_key(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    machine = Machine(name="h", host="10.0.0.1")
    args = mgr._build_ssh_args(machine, "uptime", timeout=30)

    assert "-i" not in args


def test_build_ssh_args_timeout_clamping(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    machine = Machine(name="h", host="10.0.0.1")
    args = mgr._build_ssh_args(machine, "uptime", timeout=30)

    # ConnectTimeout should be min(30, 10) = 10
    ct_val = next(a for a in args if a.startswith("ConnectTimeout="))
    assert ct_val == "ConnectTimeout=10"


# ---------------------------------------------------------------------------
# SSHManager — idle checker
# ---------------------------------------------------------------------------


def test_start_stop_idle_checker(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.start_idle_checker()
    assert mgr._checker_thread is not None
    assert mgr._checker_thread.is_alive()

    mgr.stop_idle_checker()
    # Event is set — thread will exit after current sleep/cleanup cycle
    assert mgr._checker_event.is_set()


def test_stop_idle_checker_sets_event(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    assert not mgr._checker_event.is_set()
    mgr.start_idle_checker()
    mgr.stop_idle_checker()
    assert mgr._checker_event.is_set()


def test_start_idle_checker_idempotent(tmp_path: Path) -> None:
    mgr = _make_manager(tmp_path)
    mgr.start_idle_checker()
    thread1 = mgr._checker_thread
    mgr.start_idle_checker()  # Should be no-op
    assert mgr._checker_thread is thread1
    mgr.stop_idle_checker()
