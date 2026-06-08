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
        # Handle poll/read_output first — these don't need machine/command
        if params.get("poll"):
            return ok(**manager.poll_session(params["poll"]))
        if params.get("read_output"):
            return ok(**manager.read_output(params["read_output"]))

        error = require(params, "machine", "command")
        if error:
            return err(error)

        background = params.get("background", False)
        result = manager.run_command(
            machine_name=params["machine"],
            command=params["command"],
            timeout=params.get("timeout"),
            new_session=params.get("new_session", False),
            background=background,
            max_output_chars=params.get("max_output_chars", 50_000),
        )

        if background and isinstance(result, dict) and "session_id" in result:
            return ok(
                session_id=result["session_id"],
                pid=result.get("pid"),
                machine=result.get("machine", params["machine"]),
                status="running",
                message="Command started in background. Use poll or read_output to check status.",
            )

        return ok(**result)

    return _handle
