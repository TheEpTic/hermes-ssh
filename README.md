# nexus-plugins

Hermes Agent plugins by Nexus. Monorepo — each plugin is a standalone directory that can be symlinked or copied into `~/.hermes/plugins/`.

## Plugins

| Plugin | Status | Description |
|--------|--------|-------------|
| `ssh-tools` | Planning | SSH terminal, session management, machine registry, idle alerts |
| *(more coming)* | | |

## Structure

```
nexus-plugins/
├── _template/          # Base for new plugins (copy this)
│   ├── plugin.yaml
│   ├── __init__.py
│   ├── schemas.py
│   └── tools.py
├── ssh-tools/          # SSH management plugin
├── deploy.sh           # Symlink plugins into ~/.hermes/plugins/
└── README.md
```

## Quick Start

```bash
# Deploy all plugins (symlinks)
./deploy.sh

# Deploy a specific plugin
./deploy.sh ssh-tools

# Remove deployed plugins
./deploy.sh --clean
```

## Creating a New Plugin

```bash
cp -r _template new-plugin-name
# Edit plugin.yaml, __init__.py, schemas.py, tools.py
./deploy.sh new-plugin-name
```

Each plugin follows the standard Hermes plugin layout:
- `plugin.yaml` — manifest (name, version, description, hooks)
- `__init__.py` — `register(ctx)` entry point
- `schemas.py` — tool schemas the LLM sees
- `tools.py` — actual tool handlers
