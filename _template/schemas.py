"""Tool schemas — what the LLM sees.

Each schema is a dict matching OpenAI's function-calling format:
{
    "name": "tool_name",
    "description": "What it does.",
    "parameters": {
        "type": "object",
        "properties": { ... },
        "required": [ ... ]
    }
}
"""

EXAMPLE_SCHEMA = {
    "name": "example_tool",
    "description": "Does something useful. Describe what it does clearly.",
    "parameters": {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "What to process",
            },
        },
        "required": ["input"],
    },
}
