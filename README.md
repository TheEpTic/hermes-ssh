# hermes-ssh

[![CI](https://github.com/TheEpTic/hermes-ssh/actions/workflows/ci.yml/badge.svg)](https://github.com/TheEpTic/hermes-ssh/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

SSH remote execution plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Run commands on remote servers, track sessions, reuse connections — all from inside Hermes.

```
/ssh web1 uptime
ssh_machines add name=web1 host=192.168.1.50
ssh_sessions list
```

## Quick Start

```bash
# Clone and deploy
git clone https://github.com/TheEpTic/hermes-ssh.git
cd hermes-ssh
./deploy.sh

# Restart Hermes
/reset
```

Or manually:

```bash
git clone https://github.com/TheEpTic/hermes-ssh.git
ln -s ./hermes-ssh/src/ssh_tools ~/.hermes/plugins/hermes-ssh
# Then /reset in Hermes
```

## What It Does

**`ssh_terminal`** — Run any command on a remote machine. Commands run through `bash -c` with `pipefail`, so pipelines work correctly.

**`ssh_machines`** — Register servers once, refer to them by name. Supports aliases, tags, and connectivity tests.

**`ssh_sessions`** — Tracks every command you run. Idle sessions get cleaned up automatically after 30 minutes.

**`/ssh` slash command** — Quick access from chat. Inspect machines, run commands, test connectivity.

### Connection Reuse

SSH connections are reused via `ControlMaster` with a 5-minute persist window. The second command to the same host is instant.

### Examples

```bash
# Add a server
ssh_machines add name=web1 host=192.168.1.50 user=deploy key=~/.ssh/id_ed25519

# Run a command
ssh_terminal machine=web1 command="df -h"

# Via slash command
/ssh web1 uptime
/ssh web1 docker ps

# Check connectivity
/ssh test

# Clean up idle sessions
/ssh cleanup
```

## How It Works

hermes-ssh gives Hermes three tools and one slash command:

| Tool | Purpose |
|------|---------|
| `ssh_terminal` | Run commands on remote machines |
| `ssh_machines` | Manage the machine registry |
| `ssh_sessions` | Track and clean up sessions |
| `/ssh` | Chat-native interface to all of the above |

Machines are stored in `data/machines.json` inside the plugin directory. Sessions are tracked in `data/sessions.json`. ControlMaster sockets live in `data/sockets/`. Everything is local — no external services.

## Configuration

All settings live in `src/ssh_tools/config.py` as `SSHConfig`:

| Setting | Default | What It Does |
|---------|---------|--------------|
| `default_port` | 22 | SSH port for new machines |
| `default_user` | root | SSH user for new machines |
| `connect_timeout` | 5s | How long to wait for SSH handshake |
| `command_timeout` | 30s | How long before a command is killed |
| `idle_timeout_minutes` | 30m | Auto-kill sessions idle longer than this |
| `strict_host_key_checking` | no | Host key verification |

## Security

**`StrictHostKeyChecking=no` is the default.** This makes first-time connections work without manual key verification, but means you're vulnerable to MITM attacks on untrusted networks. For production hosts, set it to `yes` in your SSH config.

Machine credentials (host, user, key path) are stored in plaintext JSON. The data directory is created inside the plugin directory with default filesystem permissions.

See [SECURITY.md](SECURITY.md) for the full picture.

## Requirements

- Python 3.11+
- OpenSSH client (`ssh`)
- [Hermes Agent](https://github.com/NousResearch/hermes-agent)

## Development

```bash
git clone https://github.com/TheEpTic/hermes-ssh.git
cd hermes-ssh
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# Run checks
ruff check src/ssh_tools/ tests/
ruff format --check src/ssh_tools/ tests/
mypy src/ssh_tools/
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and project structure.

## License

MIT — see [LICENSE](LICENSE).
