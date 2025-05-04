#
# supsrc/cli/config_cmds.py
# -*- coding: utf-8 -*-
"""
CLI commands related to configuration management for supsrc.
"""

from pathlib import Path

import click
import structlog

# Use relative imports
try:
    from ..config import load_config
    from ..exceptions import ConfigurationError
except ImportError:
     # Fallback for development if needed
    try:
        from supsrc.config import load_config
        from supsrc.exceptions import ConfigurationError
    except ImportError:
        def load_config(*args, **kwargs): raise RuntimeError("Cannot load config loader.")
        class ConfigurationError(Exception): pass


# Import rich if available for pretty printing
try:
    import rich.pretty
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

log = structlog.get_logger("cli.config")

# Create a command group for config-related commands
@click.group(name="config")
def config_cli():
    """Commands for inspecting and validating configuration."""
    pass


@config_cli.command(name="show")
@click.option(
    '-c', '--config-path',
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"), # Sensible default
    show_default=True,
    help="Path to the supsrc configuration file."
)
@click.pass_context # Get context from the parent group (for log level etc)
def show_config(ctx: click.Context, config_path: Path):
    """Load, validate, and display the configuration."""
    log.info("Executing 'config show' command", config_path=str(config_path))

    try:
        config = load_config(config_path)
        log.debug("Configuration loaded successfully by 'show' command.")

        print("\n--- Loaded Supsrc Configuration ---")
        if RICH_AVAILABLE:
            rich.pretty.pprint(config, expand_all=True)
        else:
            # Basic fallback pretty print
            import pprint
            pprint.pprint(config, indent=2)
        print("--- End of Configuration ---")

        # Check for disabled repos and inform user
        disabled_count = sum(1 for repo in config.repositories.values() if not repo._path_valid)
        if disabled_count > 0:
            log.warning(f"{disabled_count} repository path(s) were invalid and auto-disabled.", count=disabled_count)
        else:
             log.info("All repository paths validated successfully.")


    except ConfigurationError as e:
        log.error("Failed to load or validate configuration", error=str(e), exc_info=True)
        # Use click.echo for consistent CLI output, especially for errors
        click.echo(f"Error: Configuration problem in '{config_path}':\n{e}", err=True)
        ctx.exit(1) # Exit with error code
    except Exception as e:
        log.critical("An unexpected error occurred during 'config show'", error=str(e), exc_info=True)
        click.echo(f"Error: An unexpected issue occurred: {e}", err=True)
        ctx.exit(2)

# 🔼⚙️
