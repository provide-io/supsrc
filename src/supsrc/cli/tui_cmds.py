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
def tui_cli(ctx: click.Context, config_path_str: str, **kwargs):
    """Launch the Supsrc Textual User Interface."""

    # Setup logging using the utility function.
    # TUI might prefer logs to go to a file by default and not clutter the console,
    # so we set local_file_only_logs=True if a log_file is specified.
    # The TUI itself will also handle its internal logging separate from CLI verbosity.
    log_file_in_ctx = ctx.obj.get("LOG_FILE")
    # Default TUI to file-only logging if a log file is active from global options
    # or if this command were to add its own --log-file option.
    # If no log file, console logs are fine.
    tui_file_only_default = bool(log_file_in_ctx)

    setup_logging_from_context(
        ctx,
        local_log_level=kwargs.get("log_level"), # Pass through if tui_cli has its own level
        local_json_logs=kwargs.get("json_logs"),
        local_file_only_logs=kwargs.get("file_only_logs", tui_file_only_default), # TUI specific default for file_only
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
