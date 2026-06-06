# Changelog

## 0.1.0 — Initial release

- `ssh_terminal` — run commands on remote machines via SSH
- `ssh_machines` — machine registry with aliases, tags, and connectivity tests
- `ssh_sessions` — session tracking with idle detection and cleanup
- `ControlMaster` — persistent SSH connections with 5-minute reuse window
- `bash -c` wrapping with `pipefail` for reliable pipeline exit codes
- `/ssh` slash command for quick machine inspection and command execution
- Background idle checker with configurable timeout
- Atomic JSON writes with temp files for crash safety
- Thread-safe operations via locks
- 77 tests covering config, manager, tool handlers, and edge cases
- CI with ruff, mypy, and pytest across Python 3.11–3.13
