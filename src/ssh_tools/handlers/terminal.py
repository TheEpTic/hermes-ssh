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

        # Handle poll for a background session
        poll_session = params.get("poll")
        if poll_session:
            result = manager.poll_session(poll_session)
            return ok(**result)

        # Handle read_output for a completed background session
        read_session = params.get("read_output")
        if read_session:
            result = manager.read_output(read_session)
            return ok(**result)

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
