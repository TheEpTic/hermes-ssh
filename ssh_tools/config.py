"""Centralized configuration for ssh-tools plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
DEFAULT_DATA_DIR = PLUGIN_DIR / "data"


@dataclass(frozen=True)
class SSHConfig:
    """Immutable plugin configuration."""

    data_dir: Path = field(default=DEFAULT_DATA_DIR)

    # SSH defaults
    default_port: int = 22
    default_user: str = "root"
    connect_timeout: int = 5
    command_timeout: int = 30
    strict_host_key_checking: str = "no"

    # Session management
    idle_check_interval: int = 60  # seconds between idle checks
    idle_timeout_minutes: int = 30  # auto-kill after this
    closed_prune_hours: int = 24  # remove closed sessions after this

    # Paths (derived from data_dir)
    @property
    def machines_file(self) -> Path:
        return self.data_dir / "machines.json"

    @property
    def sessions_file(self) -> Path:
        return self.data_dir / "sessions.json"

    @property
    def socket_dir(self) -> Path:
        return self.data_dir / "sockets"

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.socket_dir.mkdir(parents=True, exist_ok=True)


# Module-level default — importable, overridable for tests
DEFAULT_CONFIG = SSHConfig()
