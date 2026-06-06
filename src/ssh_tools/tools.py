"""Tool handlers — thin wrappers around SSHManager for the plugin interface."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .manager import Machine, SSHManager

if TYPE_CHECKING:
    from collections.abc import Callable


def handle_ssh_terminal(manager: SSHManager) -> Callable[[dict[str, Any]], str]:
    """Create a handler for ssh_terminal that captures manager via closure."""

    def _handle(params: dict[str, Any], **kwargs: Any) -> str:
        machine = params.get("machine", "")
        command = params.get("command", "")
        timeout = params.get("timeout")
        new_session = params.get("new_session", False)

        if not machine:
            return json.dumps({"success": False, "error": "machine is required"})
        if not command:
            return json.dumps({"success": False, "error": "command is required"})

        result = manager.run_command(
            machine_name=machine,
            command=command,
            timeout=timeout,
            new_session=new_session,
        )
        return json.dumps(result)

    return _handle


def handle_ssh_machines(manager: SSHManager) -> Callable[[dict[str, Any]], str]:
    """Create a handler for ssh_machines that captures manager via closure."""

    def _handle(params: dict[str, Any], **kwargs: Any) -> str:
        action = params.get("action", "list")

        if action == "list":
            machines = manager.list_machines()
            return json.dumps(
                {
                    "success": True,
                    "machines": {
                        name: {
                            "host": m.host,
                            "user": m.user,
                            "port": m.port,
                            "aliases": m.aliases or [],
                            "tags": m.tags or [],
                            "description": m.description,
                        }
                        for name, m in machines.items()
                    },
                    "count": len(machines),
                }
            )

        if action == "add":
            name = params.get("name", "")
            host = params.get("host", "")
            if not name or not host:
                return json.dumps({"success": False, "error": "name and host are required"})
            machine = manager.add_machine(
                Machine(
                    name=name,
                    host=host,
                    user=params.get("user", "root"),
                    port=params.get("port", 22),
                    key=params.get("key", ""),
                    aliases=params.get("aliases", []),
                    tags=params.get("tags", []),
                    description=params.get("description", ""),
                )
            )
            return json.dumps({"success": True, "machine": machine.to_dict()})

        if action == "remove":
            name = params.get("name", "")
            if not name:
                return json.dumps({"success": False, "error": "name is required"})
            removed = manager.remove_machine(name)
            return json.dumps(
                {
                    "success": removed,
                    "message": f"Removed '{name}'" if removed else f"'{name}' not found",
                }
            )

        if action == "inspect":
            name = params.get("name", "")
            if not name:
                return json.dumps({"success": False, "error": "name is required"})
            inspected = manager.get_machine(name)
            if not inspected:
                return json.dumps({"success": False, "error": f"Machine '{name}' not found"})
            canonical = manager.resolve_name(name)
            return json.dumps(
                {
                    "success": True,
                    "name": canonical,
                    "machine": inspected.to_dict(),
                }
            )

        if action == "test":
            name = params.get("name", "")
            if not name:
                return json.dumps({"success": False, "error": "name is required"})
            return json.dumps(manager.test_machine(name))

        return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    return _handle


def handle_ssh_sessions(manager: SSHManager) -> Callable[[dict[str, Any]], str]:
    """Create a handler for ssh_sessions that captures manager via closure."""

    def _handle(params: dict[str, Any], **kwargs: Any) -> str:
        action = params.get("action", "list")

        if action == "list":
            active = manager.list_sessions("active")
            enriched = {}
            for sid, session in active.items():
                enriched[sid] = {
                    **session.to_dict(),
                    "idle_secs": session.idle_seconds,
                    "idle_human": session.idle_human,
                }
            return json.dumps(
                {
                    "success": True,
                    "sessions": enriched,
                    "count": len(enriched),
                }
            )

        if action == "kill":
            sid = params.get("session_id", "")
            if not sid:
                return json.dumps({"success": False, "error": "session_id is required"})
            return json.dumps(manager.kill_session(sid))

        if action == "cleanup":
            max_idle = params.get("max_idle_minutes")
            result = manager.cleanup_idle(max_idle)
            return json.dumps(
                {
                    "success": True,
                    "cleaned": result["count"],
                    "details": result["killed"],
                }
            )

        if action == "prune":
            count = manager.prune_closed()
            return json.dumps(
                {
                    "success": True,
                    "pruned": count,
                    "message": f"Removed {count} closed session(s)",
                }
            )

        return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    return _handle
