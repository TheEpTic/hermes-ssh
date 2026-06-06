# hermes-ssh

[![CI](https://github.com/TheEpTic/hermes-ssh/actions/workflows/ci.yml/badge.svg)](https://github.com/TheEpTic/hermes-ssh/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

SSH remote execution plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Gives Hermes first-class SSH tools with machine registry, session tracking, and connection reuse.

## Features

- **`ssh_terminal`** — run commands on remote machines via SSH
- **`ssh_machines`** — machine registry with aliases, tags, and connectivity tests
- **`ssh_sessions`** — session tracking with idle detection and cleanup
- **ControlMaster** — persistent SSH connections with 5-minute reuse window
- **bash wrapping** — commands run through `bash -c` with `pipefail` enabled, so pipeline exit codes are always correct
- **`/ssh` slash command** — quick machine inspection and command execution from chat

## Install

```bash
# Clone and symlink into ~/.hermes/plugins/
git clone https://github.com/TheEpTic/hermes-ssh.git
ln -s ./hermes-ssh/src/ssh_tools ~/.hermes/plugins/hermes-ssh

# Or use the deploy script
./deploy.sh hermes-ssh
```

Then restart Hermes (`/reset` or `gateway restart`).

## Usage

### Add a machine

```
/ssh test myserver          # test connectivity
ssh_machines add            # via tool call
```

### Run a command

```
/ssh myserver uptime        # via slash command
ssh_terminal                # via tool call
```

### Manage sessions

```
/ssh cleanup                # kill idle sessions
ssh_sessions list           # via tool call
```

## Tool Reference

### ssh_terminal

Run a command on a remote machine via SSH. Uses the machine registry — add machines first with ssh_machines.

- **`machine`** (string, required) — Machine name or alias
- **`command`** (string, required) — Command to run
- **`timeout`** (integer, optional) — Seconds before kill (default: 30)
- **`new_session`** (boolean, optional) — Force new connection (default: false)

### ssh_machines

Manage the SSH machine registry.

- **`action`** (string, required) — `list`, `add`, `remove`, `inspect`, `test`
- **`name`** (string, required for add/remove/inspect/test) — Machine name
- **`host`** (string, required for add) — IP or hostname
- **`user`** (string, optional) — SSH user (default: root)
- **`port`** (integer, optional) — SSH port (default: 22)
- **`key`** (string, optional) — Path to SSH key
- **`aliases`** (array, optional) — Short aliases
- **`tags`** (array, optional) — Tags for organization

### ssh_sessions

Manage active SSH sessions.

- **`action`** (string, required) — `list`, `kill`, `cleanup`, `prune`
- **`session_id`** (string, required for kill) — Session ID
- **`max_idle_minutes`** (integer, optional) — Idle threshold (default: 30)

## Configuration

All config is handled via the `SSHConfig` dataclass in `config.py`. Key defaults:

| Setting | Default | Description |
|---------|---------|-------------|
| `default_port` | 22 | SSH port for new machines |
| `default_user` | root | SSH user for new machines |
| `connect_timeout` | 5s | Connection timeout |
| `command_timeout` | 30s | Command execution timeout |
| `idle_timeout_minutes` | 30m | Auto-kill idle sessions |
| `strict_host_key_checking` | no | SSH host key verification |

### Runtime data

Machine and session data is stored in `data/` relative to the plugin directory:

- `data/machines.json` — registered machines
- `data/sessions.json` — active/closed sessions
- `data/sockets/` — ControlMaster Unix sockets

These files are created automatically on first use. Add `data/` to your `.gitignore` if forking.

## Security

**⚠️ `StrictHostKeyChecking=no` is the default.** This prevents connection failures on first use but makes connections vulnerable to MITM attacks. For production hosts over untrusted networks, set `StrictHostKeyChecking=yes` in your SSH config.

See [SECURITY.md](SECURITY.md) for full security considerations.

## Requirements

- Python 3.11+
- OpenSSH client (`ssh`)
- Hermes Agent

## License

MIT — see [LICENSE](LICENSE).
