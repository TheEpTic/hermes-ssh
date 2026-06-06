"""Tool handlers — what runs when the LLM calls a tool.

Each handler receives (params: dict, **kwargs) and must return a JSON string.
kwargs includes: task_id, session_id, agent (the AIAgent instance).
"""

import json


def handle_example(params: dict, **kwargs) -> str:
    """Handle the example_tool call."""
    user_input = params.get("input", "")
    # Do work here
    return json.dumps({"success": True, "result": f"Processed: {user_input}"})
