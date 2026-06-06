"""SSH tool handlers — what runs when the LLM calls a tool."""
from __future__ import annotations

import json
from typing import Any, Dict

from . import registry, sessions, ssh


def handle_ssh_terminal(params: Dict[str, Any], **kwargs) -> str:
    """Handle ssh_terminal tool calls."""
    machine = params.get("machine", "")
    command = params.get("command", "")
    timeout = params.get("timeout", 30)
    new_session = params.get("new_session", False)

    if not machine:
        return json.dumps({"success": False, "error": "machine is required"})
    if not command:
        return json.dumps({"success": False, "error": "command is required"})

    result = ssh.run_command(
        machine_name=machine,
        command=command,
        timeout=timeout,
        new_session=new_session,
    )
    return json.dumps(result)


def handle_ssh_machines(params: Dict[str, Any], **kwargs) -> str:
    """Handle ssh_machines tool calls."""
    action = params.get("action", "list")

    if action == "list":
        machines = registry.list_machines()
        return json.dumps({
            "success": True,
            "machines": {
                name: {
                    "host": m["host"],
                    "user": m["user"],
                    "port": m["port"],
                    "aliases": m.get("aliases", []),
                    "tags": m.get("tags", []),
                    "description": m.get("description", ""),
                }
                for name, m in machines.items()
            },
            "count": len(machines),
        })

    if action == "add":
        name = params.get("name", "")
        host = params.get("host", "")
        if not name or not host:
            return json.dumps({"success": False, "error": "name and host are required"})
        machine = registry.add_machine(
            name=name,
            host=host,
            user=params.get("user", "root"),
            port=params.get("port", 22),
            key=params.get("key", ""),
            aliases=params.get("aliases", []),
            tags=params.get("tags", []),
            description=params.get("description", ""),
        )
        return json.dumps({"success": True, "machine": machine})

    if action == "remove":
        name = params.get("name", "")
        if not name:
            return json.dumps({"success": False, "error": "name is required"})
        removed = registry.remove_machine(name)
        return json.dumps({
            "success": removed,
            "message": f"Removed '{name}'" if removed else f"'{name}' not found",
        })

    if action == "inspect":
        name = params.get("name", "")
        if not name:
            return json.dumps({"success": False, "error": "name is required"})
        machine = registry.get_machine(name)
        if not machine:
            return json.dumps({"success": False, "error": f"Machine '{name}' not found"})
        canonical = registry.resolve_name(name)
        return json.dumps({
            "success": True,
            "name": canonical,
            "machine": machine,
        })

    if action == "test":
        name = params.get("name", "")
        if not name:
            return json.dumps({"success": False, "error": "name is required"})
        result = registry.test_machine(name)
        return json.dumps(result)

    return json.dumps({"success": False, "error": f"Unknown action: {action}"})


def handle_ssh_sessions(params: Dict[str, Any], **kwargs) -> str:
    """Handle ssh_sessions tool calls."""
    action = params.get("action", "list")

    if action == "list":
        active = sessions.list_sessions("active")
        # Enrich with idle time
        enriched = {}
        for sid, session in active.items():
            idle = sessions.idle_seconds(sid)
            enriched[sid] = {
                **session,
                "idle_secs": idle,
                "idle_human": _fmt_idle(idle),
            }
        return json.dumps({
            "success": True,
            "sessions": enriched,
            "count": len(enriched),
        })

    if action == "kill":
        sid = params.get("session_id", "")
        if not sid:
            return json.dumps({"success": False, "error": "session_id is required"})
        result = sessions.kill_session(sid)
        return json.dumps(result)

    if action == "cleanup":
        max_idle = params.get("max_idle_minutes", 30)
        result = sessions.cleanup_idle(max_idle)
        return json.dumps({
            "success": True,
            "cleaned": result["count"],
            "details": result["killed"],
        })

    if action == "prune":
        count = sessions.prune_closed()
        return json.dumps({
            "success": True,
            "pruned": count,
            "message": f"Removed {count} closed session(s)",
        })

    return json.dumps({"success": False, "error": f"Unknown action: {action}"})


def _fmt_idle(idle_secs: int | None) -> str:
    """Format idle seconds into human-readable string."""
    if idle_secs is None:
        return "unknown"
    if idle_secs < 60:
        return f"{idle_secs}s"
    if idle_secs < 3600:
        return f"{idle_secs // 60}m {idle_secs % 60}s"
    hours = idle_secs // 3600
    mins = (idle_secs % 3600) // 60
    return f"{hours}h {mins}m"
