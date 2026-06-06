"""ssh-tools plugin — SSH session management for Hermes.

Provides:
  - ssh_terminal: Open an SSH session to a registered machine
  - ssh_machines: List/add/remove machines from the registry
  - ssh_sessions: List/kill active SSH sessions
  - /ssh slash command for quick access

Data files:
  - machines.json: Machine registry (host, user, port, key, aliases)
  - sessions.json: Active session tracking (pid, started, last_active, idle_secs)
"""
