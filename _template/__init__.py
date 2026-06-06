"""Template plugin — register(ctx) entry point.

Hermes calls register(ctx) once at startup. Use ctx to register:
  - ctx.register_tool()      — add a tool the LLM can call
  - ctx.register_hook()      — lifecycle callbacks
  - ctx.register_command()   — slash commands
  - ctx.register_skill()     — bundle skills with the plugin
  - ctx.register_cli_command() — hermes <plugin> <sub> CLI commands
"""
