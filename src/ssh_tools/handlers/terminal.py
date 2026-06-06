"""Handler for the ssh_terminal tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..utils import err, ok, require

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..manager import SSHManager


def handle_ssh_terminal(manager: SSHManager) -> Callable[[dict[str, Any]], str]:
    """Create a handler for ssh_terminal that captures manager via closure."""

    def _handle(params: dict[str, Any], **kwargs: Any) -> str:
        error = require(params, "machine", "command")
        if error:
            return err(error)

        result = manager.run_command(
            machine_name=params["machine"],
            command=params["command"],
            timeout=params.get("timeout"),
            new_session=params.get("new_session", False),
        )
        return ok(**result)

    return _handle
