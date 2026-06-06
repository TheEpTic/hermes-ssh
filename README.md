# hermes-ssh

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
ln -s ./hermes-ssh/ssh_tools ~/.hermes/plugins/hermes-ssh

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

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `machine` | string | yes | Machine name or alias |
| `command` | string | yes | Command to run |
| `timeout` | integer | no | Seconds before kill (default: 30) |
| `new_session` | boolean | no | Force new connection (default: false) |

### ssh_machines

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | yes | `list`, `add`, `remove`, `inspect`, `test` |
| `name` | string | dep | Machine name |
| `host` | string | dep | IP or hostname |
| `user` | string | no | SSH user (default: root) |
| `port` | integer | no | SSH port (default: 22) |
| `key` | string | no | Path to SSH key |
| `aliases` | array | no | Short aliases |
| `tags` | array | no | Tags for organization |

### ssh_sessions

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | yes | `list`, `kill`, `cleanup`, `prune` |
| `session_id` | string | dep | Session ID (for kill) |
| `max_idle_minutes` | integer | no | Idle threshold (default: 30) |

## Requirements

- Python 3.11+
- OpenSSH client (`ssh`, `scp`)
- Hermes Agent

## License

MIT — see [LICENSE](LICENSE).
