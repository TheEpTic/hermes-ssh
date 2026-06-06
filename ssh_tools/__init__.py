"""ssh-tools — SSH session management plugin for Hermes.

Provides:
  - ssh_terminal: Run commands on remote machines via SSH
  - ssh_machines: Machine registry (add/list/remove/test/inspect)
  - ssh_sessions: Active session tracking (list/kill/cleanup)
  - /ssh slash command for quick access
"""

from __future__ import annotations

import logging
from typing import Any

from .manager import SSHManager
from .schemas import SSH_MACHINES_SCHEMA, SSH_SESSIONS_SCHEMA, SSH_TERMINAL_SCHEMA
from .tools import handle_ssh_machines, handle_ssh_sessions, handle_ssh_terminal

logger = logging.getLogger(__name__)

# Module-level manager — initialized in register()
_manager: SSHManager | None = None


def _get_manager() -> SSHManager:
    global _manager
    if _manager is None:
        raise RuntimeError("ssh-tools plugin not registered. Call register() first.")
    return _manager


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------

_HELP = """\
/ssh — SSH session management

Subcommands:
  (no args)              List machines and active sessions
  <machine>              Show machine details
  <machine> <command>    Run command on machine
  test                   Test connectivity to all machines
  cleanup                Kill all idle sessions (>30 min)
  help                   Show this help
"""


def _handle_slash(raw_args: str) -> str | None:
    manager = _get_manager()
    args = raw_args.strip().split()

    if not args or args[0] in ("help", "-h", "--help"):
        return _HELP

    if args[0] == "test":
        machines = manager.list_machines()
        if not machines:
            return "No machines registered. Use ssh_machines to add one."
        lines = ["Testing connectivity:"]
        for name, machine in machines.items():
            result = manager.test_machine(name)
            icon = "✓" if result["success"] else "✗"
            error = f" — {result.get('error', '')}" if not result["success"] else ""
            lines.append(f"  {icon} {name} ({machine.host}){error}")
        return "\n".join(lines)

    if args[0] == "cleanup":
        result = manager.cleanup_idle()
        if result["count"] == 0:
            return "No idle sessions to clean up."
        lines = [f"Killed {result['count']} idle session(s):"]
        for item in result["killed"]:
            lines.append(f"  - {item['session_id']} on {item.get('machine', '?')}")
        return "\n".join(lines)

    name = args[0]
    target = manager.get_machine(name)
    if not target:
        return f"Machine '{name}' not found in registry."

    # Run command if provided
    if len(args) > 1:
        command = " ".join(args[1:])
        result = manager.run_command(name, command)
        parts = []
        if result.get("stdout"):
            parts.append(result["stdout"].rstrip())
        if result.get("stderr"):
            parts.append(f"stderr: {result['stderr'].rstrip()}")
        parts.append(f"exit: {result.get('exit_code', '?')} ({result.get('elapsed_secs', '?')}s)")
        return "\n".join(parts)

    # Inspect machine
    canonical = manager.resolve_name(name)
    assert canonical is not None  # machine exists, resolve must succeed
    lines = [
        f"Machine: {canonical}",
        f"  Host: {target.host}",
        f"  User: {target.user}",
        f"  Port: {target.port}",
    ]
    if target.key:
        lines.append(f"  Key: {target.key}")
    if target.aliases:
        lines.append(f"  Aliases: {', '.join(target.aliases)}")
    if target.tags:
        lines.append(f"  Tags: {', '.join(target.tags)}")
    if target.description:
        lines.append(f"  Desc: {target.description}")

    active = manager.list_sessions("active")
    machine_sessions = {k: v for k, v in active.items() if v.machine == canonical}
    if machine_sessions:
        lines.append(f"  Active sessions: {len(machine_sessions)}")
        for sid, s in machine_sessions.items():
            lines.append(f"    - {sid} (idle: {s.idle_human}, commands: {s.command_count})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session end hook
# ---------------------------------------------------------------------------


def _on_session_end(session_id: str = "", **kwargs: Any) -> None:
    try:
        manager = _get_manager()
        result = manager.cleanup_idle(max_idle_minutes=manager.config.session_end_idle_threshold)
        if result["count"] > 0:
            logger.info(
                "ssh-tools: auto-cleaned %d idle session(s) on session end",
                result["count"],
            )
    except Exception as exc:
        logger.debug("ssh-tools: session-end cleanup failed: %s", exc)


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(ctx: Any) -> None:
    """Register SSH tools with Hermes."""
    global _manager
    if _manager is not None:
        logger.debug("ssh-tools: already registered, skipping")
        return
    _manager = SSHManager()

    # Tools
    ctx.register_tool(
        name="ssh_terminal",
        toolset="ssh_tools",
        schema=SSH_TERMINAL_SCHEMA,
        handler=handle_ssh_terminal(_manager),
        description="Run a command on a remote machine via SSH.",
    )
    ctx.register_tool(
        name="ssh_machines",
        toolset="ssh_tools",
        schema=SSH_MACHINES_SCHEMA,
        handler=handle_ssh_machines(_manager),
        description="Manage the SSH machine registry.",
    )
    ctx.register_tool(
        name="ssh_sessions",
        toolset="ssh_tools",
        schema=SSH_SESSIONS_SCHEMA,
        handler=handle_ssh_sessions(_manager),
        description="Manage active SSH sessions.",
    )

    # Hooks
    ctx.register_hook("on_session_end", _on_session_end)

    # Slash command
    ctx.register_command(
        "ssh",
        handler=_handle_slash,
        description="SSH session management — machines, sessions, idle alerts.",
    )

    # Start background idle checker
    _manager.start_idle_checker()

    logger.info("ssh-tools plugin loaded")
