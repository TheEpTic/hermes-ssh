"""ssh-tools — SSH session management plugin for Hermes.

Provides:
  - ssh_terminal: Run commands on remote machines via SSH
  - ssh_machines: Machine registry (add/list/remove/test/inspect)
  - ssh_sessions: Active session tracking (list/kill/cleanup)
  - /ssh slash command for quick access
  - on_session_end hook for auto-cleanup of stale sessions

Data files (in plugin's data/ dir):
  - machines.json: Machine registry
  - sessions.json: Active session tracking
  - sockets/: SSH ControlMaster sockets
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from . import sessions
from .schemas import SSH_MACHINES_SCHEMA, SSH_SESSIONS_SCHEMA, SSH_TERMINAL_SCHEMA
from .tools import handle_ssh_machines, handle_ssh_sessions, handle_ssh_terminal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------

_HELP = """\
/ssh — SSH session management

Subcommands:
  (no args)              List machines and active sessions
  <machine>              Show machine details
  <machine> <command>    Run command on machine (delegates to ssh_terminal)
  test                   Test connectivity to all machines
  cleanup                Kill all idle sessions (>30 min)
  help                   Show this help

Examples:
  /ssh                   — list everything
  /ssh elder             — show elder details
  /ssh elder uptime      — run 'uptime' on elder
  /ssh test              — test all machines
  /ssh cleanup           — kill idle sessions
"""


def _handle_slash(raw_args: str) -> Optional[str]:
    """Handle /ssh slash command."""
    from . import registry

    args = raw_args.strip().split()

    if not args or args[0] in ("help", "-h", "--help"):
        return _HELP

    # /ssh test — test all machines
    if args[0] == "test":
        machines = registry.list_machines()
        if not machines:
            return "No machines registered. Use ssh_machines to add one."
        lines = ["Testing connectivity:"]
        for name in machines:
            result = registry.test_machine(name)
            status = "✓" if result["success"] else "✗"
            error = f" — {result.get('error', '')}" if not result["success"] else ""
            lines.append(f"  {status} {name} ({machines[name]['host']}){error}")
        return "\n".join(lines)

    # /ssh cleanup
    if args[0] == "cleanup":
        result = sessions.cleanup_idle(30)
        if result["count"] == 0:
            return "No idle sessions to clean up."
        lines = [f"Killed {result['count']} idle session(s):"]
        for item in result["killed"]:
            lines.append(f"  - {item['session_id']} on {item.get('machine', '?')}")
        return "\n".join(lines)

    # /ssh <machine> — inspect or run command
    name = args[0]
    machine = registry.get_machine(name)
    if not machine:
        return f"Machine '{name}' not found in registry."

    # If there's a command, run it
    if len(args) > 1:
        command = " ".join(args[1:])
        from .ssh import run_command
        result = run_command(name, command)
        parts = []
        if result.get("stdout"):
            parts.append(result["stdout"].rstrip())
        if result.get("stderr"):
            parts.append(f"stderr: {result['stderr'].rstrip()}")
        parts.append(f"exit: {result.get('exit_code', '?')} ({result.get('elapsed_secs', '?')}s)")
        return "\n".join(parts)

    # Just inspect
    canonical = registry.resolve_name(name)
    lines = [
        f"Machine: {canonical}",
        f"  Host: {machine['host']}",
        f"  User: {machine['user']}",
        f"  Port: {machine['port']}",
    ]
    if machine.get("key"):
        lines.append(f"  Key: {machine['key']}")
    if machine.get("aliases"):
        lines.append(f"  Aliases: {', '.join(machine['aliases'])}")
    if machine.get("tags"):
        lines.append(f"  Tags: {', '.join(machine['tags'])}")
    if machine.get("description"):
        lines.append(f"  Desc: {machine['description']}")

    # Show active sessions for this machine
    active = sessions.list_sessions("active")
    machine_sessions = {k: v for k, v in active.items() if v.get("machine") == canonical}
    if machine_sessions:
        lines.append(f"  Active sessions: {len(machine_sessions)}")
        for sid, s in machine_sessions.items():
            idle = sessions.idle_seconds(sid)
            idle_str = f"{idle}s" if idle is not None else "?"
            lines.append(f"    - {sid} (idle: {idle_str}, commands: {s.get('command_count', 0)})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session end hook — auto-cleanup
# ---------------------------------------------------------------------------

def _on_session_end(session_id: str = "", **kwargs) -> None:
    """When a Hermes session ends, clean up stale SSH sessions."""
    try:
        active = sessions.list_sessions("active")
        if not active:
            return
        # Kill sessions idle > 10 minutes at session end (conservative)
        result = sessions.cleanup_idle(max_idle_minutes=10)
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

def register(ctx) -> None:
    """Register SSH tools with Hermes."""

    # Tools
    ctx.register_tool(
        name="ssh_terminal",
        toolset="ssh_tools",
        schema=SSH_TERMINAL_SCHEMA,
        handler=handle_ssh_terminal,
        description="Run a command on a remote machine via SSH.",
    )
    ctx.register_tool(
        name="ssh_machines",
        toolset="ssh_tools",
        schema=SSH_MACHINES_SCHEMA,
        handler=handle_ssh_machines,
        description="Manage the SSH machine registry.",
    )
    ctx.register_tool(
        name="ssh_sessions",
        toolset="ssh_tools",
        schema=SSH_SESSIONS_SCHEMA,
        handler=handle_ssh_sessions,
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

    # Start idle checker (background thread)
    sessions.start_idle_checker(interval=60, max_idle_minutes=30)

    logger.info("ssh-tools plugin loaded")
