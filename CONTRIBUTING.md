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
- **No `on_session_end` hook.** It exists but is disabled — idle cleanup is handled by the background checker instead.
- Run `ruff check` and `mypy` before pushing. CI will catch it if you don't.

## Project Structure

```
ssh_tools/
├── __init__.py      # Plugin registration + slash command
├── config.py        # SSHConfig dataclass
├── manager.py       # SSHManager — machines, sessions, execution
├── schemas.py       # Tool schemas (what the LLM sees)
├── tools.py         # Tool handlers (thin wrappers)
└── plugin.yaml      # Plugin manifest
tests/
├── test_config.py
├── test_manager.py
└── test_tools.py
```
