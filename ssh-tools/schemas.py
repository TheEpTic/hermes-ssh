"""SSH tool schemas — what the LLM sees."""

SSH_TERMINAL_SCHEMA = {
    "name": "ssh_terminal",
    "description": "Run a command on a remote machine via SSH. Uses the machine registry — add machines first with ssh_machines.",
    "parameters": {
        "type": "object",
        "properties": {
            "machine": {
                "type": "string",
                "description": "Machine name or alias (e.g. 'elder', 'grid1')",
            },
            "command": {
                "type": "string",
                "description": "Command to run on the remote machine",
            },
            "timeout": {
                "type": "integer",
                "description": "Seconds before killing the command (default: 30)",
                "default": 30,
            },
            "new_session": {
                "type": "boolean",
                "description": "Force a new connection instead of reusing existing (default: false)",
                "default": False,
            },
        },
        "required": ["machine", "command"],
    },
}

SSH_MACHINES_SCHEMA = {
    "name": "ssh_machines",
    "description": "Manage the SSH machine registry. Add, remove, list, test, or inspect machines.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "remove", "inspect", "test"],
                "description": "Action to perform",
            },
            "name": {
                "type": "string",
                "description": "Machine name (required for add/remove/inspect/test)",
            },
            "host": {
                "type": "string",
                "description": "IP or hostname (required for add)",
            },
            "user": {
                "type": "string",
                "description": "SSH username (default: root)",
                "default": "root",
            },
            "port": {
                "type": "integer",
                "description": "SSH port (default: 22)",
                "default": 22,
            },
            "key": {
                "type": "string",
                "description": "Path to SSH key (e.g. '~/.ssh/id_ed25519')",
                "default": "",
            },
            "aliases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short aliases for this machine",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for organization",
            },
            "description": {
                "type": "string",
                "description": "Human-readable description",
                "default": "",
            },
        },
        "required": ["action"],
    },
}

SSH_SESSIONS_SCHEMA = {
    "name": "ssh_sessions",
    "description": "Manage active SSH sessions. List, kill, or cleanup idle sessions.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "kill", "cleanup", "prune"],
                "description": "Action to perform",
            },
            "session_id": {
                "type": "string",
                "description": "Session ID (required for kill)",
            },
            "max_idle_minutes": {
                "type": "integer",
                "description": "Max idle minutes before auto-kill (for cleanup, default: 30)",
                "default": 30,
            },
        },
        "required": ["action"],
    },
}
