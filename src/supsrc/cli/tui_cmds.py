#
# supsrc/cli/tui_cmds.py
#
"""
CLI command to launch the Textual User Interface.
"""

import asyncio
import sys
from pathlib import Path

import click
import structlog

# Import logging utilities from the new cli.utils module
from supsrc.cli.utils import setup_logging_from_context, logging_options
from supsrc.tui.app import SupsrcTuiApp

log = structlog.get_logger("cli.tui")

@click.command("tui")
@click.option(
    "-c", "--config", "config_path_str",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Path to the supsrc configuration file.",
    required=True, # Make it required for now for simplicity
)
@logging_options # Reuse logging options
@click.pass_context
def tui_cli(
    ctx: click.Context,
    config_path_str: str,
    log_level: str | None,    # Explicitly define
    log_file: str | None,     # Explicitly define
    json_logs: bool | None,   # Explicitly define
    file_only_logs: bool | None # Explicitly define (added by @logging_options)
    # **kwargs removed as all known options from @logging_options are now explicit
):
    """Launch the Supsrc Textual User Interface."""

    # Setup logging using the utility function with explicitly passed parameters.
    # Determine the effective file_only_logs for TUI mode.
    # If --file-only-logs is passed to `supsrc tui`, use that.
    # Else, if --log-file (either global or local to `tui`) is specified, default to True for TUI.
    effective_file_only_logs: bool
    if file_only_logs is not None:
        effective_file_only_logs = file_only_logs
    else:
        # Check if a log file is active either from this command's options or global context
        # local_log_file (now `log_file` parameter) takes precedence.
        active_log_file = log_file or ctx.obj.get("LOG_FILE")
        effective_file_only_logs = bool(active_log_file)

    setup_logging_from_context(
        ctx,
        local_log_level=log_level,
        local_log_file=log_file,
        local_json_logs=json_logs,
        local_file_only_logs=effective_file_only_logs,
        default_log_level="INFO" # Default for TUI operations if no global level set
    )

    config_path = Path(config_path_str)
    log.info("TUI command invoked", config_path=str(config_path))

    # Ensure TUI's own logging (if any internal to Textual) doesn't conflict.
    # Textual has its own log handling; our setup is for supsrc's structured logs.

    try:
        # Create an asyncio Event for shutdown signaling if needed by the app
        # This is a simplified example; the actual app might need more complex setup.
        cli_shutdown_event = asyncio.Event()

        # Instantiate and run the TUI app
        # Pass necessary parameters like config_path and shutdown_event
        app = SupsrcTuiApp(
            config_path=config_path,
            cli_shutdown_event=cli_shutdown_event
            # Add other necessary parameters here if SupsrcTuiApp constructor requires them
        )
        app.run()
        log.info("TUI finished.")

    except Exception as e:
        log.error("Failed to launch or run TUI", error=str(e), exc_info=True)
        # Ensure a clean exit code on error
        sys.exit(1)

if __name__ == '__main__':
    # This allows running `python -m src.supsrc.cli.tui_cmds` for testing this command directly
    # For actual use, it's registered with the main CLI group.
    # A minimal context object for standalone testing:
    class MinimalContext:
        obj = {"LOG_LEVEL": "INFO", "LOG_FILE": None, "JSON_LOGS": False}

    minimal_ctx = MinimalContext()

    # Example direct call (requires a dummy config):
    # Create a dummy config for direct testing if needed
    # Path("dummy_supsrc.conf").write_text("# Dummy config\n")
    # tui_cli.main(args=['--config', 'dummy_supsrc.conf'], standalone_mode=False, ctx=minimal_ctx)

    click.echo("To test this command, ensure you have a valid supsrc config file.")
    click.echo("Example: python -m src.supsrc.cli.tui_cmds --config examples/supsrc.conf")

# 🖥️✨
