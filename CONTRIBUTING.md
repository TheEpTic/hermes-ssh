# Contributing

PRs welcome. Here's the workflow:

## Setup

```bash
git clone https://github.com/TheEpTic/hermes-ssh.git
cd hermes-ssh
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

## Development

```bash
# Lint
ruff check ssh_tools/ tests/

# Format
ruff format ssh_tools/ tests/

# Type check
mypy ssh_tools/

# Tests
pytest
```

## Guidelines

- **Tests required for bug fixes.** Each fix gets a test that reproduces the issue.
- **Separate PRs for separate concerns.** Don't bundle unrelated changes.
- Run `ruff check` and `mypy` before pushing. CI will catch it if you don't.

## Project Structure

```
ssh_tools/
├── __init__.py      # Plugin registration + slash command
├── config.py        # SSHConfig dataclass
├── manager.py       # SSHManager — machines, sessions, execution
├── schemas.py       # Tool schemas (what the LLM sees)
├── tools.py         # Tool handlers (thin wrappers)
├── plugin.yaml      # Plugin manifest
└── py.typed         # PEP 561 marker
tests/
├── conftest.py      # Shared fixtures
├── test_config.py
├── test_manager.py
└── test_tools.py
```

## Architecture

- **`SSHManager`** owns all state (machines, sessions, connections). Thread-safe.
- **Tool handlers** are thin wrappers — validation + dispatch to manager.
- **Schemas** define what the LLM sees. Keep descriptions clear and concise.
- **`/ssh` slash command** provides a chat-native interface to the same manager.
- **Idle checker** runs as a background daemon thread, cleaning up stale sessions.
