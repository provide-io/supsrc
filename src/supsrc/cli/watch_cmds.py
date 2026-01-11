# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


import asyncio
import contextlib
import logging
from pathlib import Path
import sys
import tempfile

import click
from provide.foundation.cli.decorators import logging_options
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.config import load_config
from supsrc.config.defaults import DEFAULT_WATCH_ACTIVE_INTERVAL
from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.utils.directories import SupsrcDirectories

log: StructLogger = get_logger(__name__)


async def _status_reporter(orchestrator: WatchOrchestrator) -> None:
    """Periodically print repository status to stdout."""
    while True:
        try:
            # Always sleep for the active interval to ensure responsive timer updates
            await asyncio.sleep(DEFAULT_WATCH_ACTIVE_INTERVAL)

            if not orchestrator.repo_states:
                continue

            # Update timer countdowns for all repositories and check for active timers
            active_timers = False
            for state in orchestrator.repo_states.values():
                state.update_timer_countdown()
                if state.timer_seconds_left is not None:
                    active_timers = True

            status_lines = []
            for repo_id, state in orchestrator.repo_states.items():
                # Format status line
                status_emoji = state.display_status_emoji
                status_name = state.status.name.lower()

                # Add file change counts if any
                if state.has_uncommitted_changes:
                    change_info = f" (+{state.added_files}/-{state.deleted_files}/~{state.modified_files})"
                else:
                    change_info = " (clean)"

                # Add timer if active
                timer_info = ""
                if state.timer_seconds_left:
                    timer_info = f" ({state.timer_seconds_left}s)"

                # Add pause/stop indicators
                pause_info = ""
                if state.is_stopped:
                    pause_info = " [STOPPED]"
                elif state.is_paused:
                    pause_info = " [PAUSED]"

                # Add circuit breaker indicator
                cb_info = ""
                if state.circuit_breaker_triggered:
                    cb_reason = state.circuit_breaker_reason or "triggered"
                    cb_info = f" [CB: {cb_reason[:40]}...]"  # Truncate long reasons

                status_line = (
                    f"{status_emoji} {repo_id}: {status_name}{change_info}{timer_info}{pause_info}{cb_info}"
                )
                status_lines.append(status_line)

            # Print status summary when there are active timers or periodically when idle
            # Use a counter to print status every 10 seconds when no timers are active
            if not hasattr(_status_reporter, "idle_counter"):
                _status_reporter.idle_counter = 0

            should_print = False
            if active_timers:
                # Always print when timers are active
                should_print = True
                _status_reporter.idle_counter = 0
            else:
                # Print every 10 seconds when idle (10 * 1s intervals)
                _status_reporter.idle_counter += 1
                if _status_reporter.idle_counter >= 10:
                    should_print = True
                    _status_reporter.idle_counter = 0

            if status_lines and should_print:
                pass  # Add blank line for readability

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.debug("Status reporter error", error=str(e))


async def _run_orchestrator_with_status(orchestrator: WatchOrchestrator) -> None:
    """Run orchestrator with periodic status reporting."""
    # Start status reporter task
    status_task = asyncio.create_task(_status_reporter(orchestrator))

    try:
        # Run orchestrator
        await orchestrator.run()
    finally:
        # Cancel status reporter
        status_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await status_task


def _run_headless_orchestrator(orchestrator: WatchOrchestrator) -> int:
    """
    Runs the orchestrator using the standard asyncio.run(), which provides
    robust signal handling and lifecycle management.
    """
    try:
        # Print initial status message

        # asyncio.run() is the preferred, high-level way to run an async application.
        # It creates a new event loop, runs the coroutine until it completes,
        # and handles cleanup. Crucially, it also adds its own signal handlers
        # for SIGINT and SIGTERM that will correctly cancel the main task.
        asyncio.run(_run_orchestrator_with_status(orchestrator))
        return 0
    except KeyboardInterrupt:
        # This block is entered when CTRL-C is pressed.
        # The finally block within orchestrator.run() will have already been
        # executed by the time we get here, due to the task cancellation
        # handled by asyncio.run().
        log.warning("Shutdown initiated by KeyboardInterrupt (CTRL-C).")
        return 130  # Standard exit code for SIGINT
    except Exception:
        # This catches any other unhandled exceptions from the orchestrator.
        log.critical("Orchestrator exited with an unhandled exception.", exc_info=True)
        return 1
    finally:
        # Final log message after the event loop is closed.
        logging.shutdown()


@click.command(name="watch")
@click.option(
    "-c",
    "--config-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@click.option(
    "--app-log",
    type=click.Path(path_type=Path),
    default=Path(tempfile.gettempdir()) / "supsrc_app.log",
    show_default=True,
    help="Path to write application debug logs.",
)
@click.option(
    "--event-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to write structured event logs in JSON format. Defaults to .supsrc/local/logs/events.jsonl in the first repository.",
)
@click.option(
    "--no-color",
    is_flag=True,
    default=False,
    help="Disable color output in event stream.",
)
@click.option(
    "--ascii",
    "use_ascii",
    is_flag=True,
    default=False,
    help="Use ASCII characters instead of emojis in event stream.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Show verbose event details including event IDs and full metadata.",
)
@click.option(
    "--verbose-format",
    type=click.Choice(["table", "compact"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Format for verbose output: 'table' (structured with box drawing) or 'compact' (key=value style).",
)
@logging_options
@click.pass_context
def watch_cli(
    ctx: click.Context,
    config_path: Path,
    app_log: Path,
    event_log: Path | None,
    no_color: bool,
    use_ascii: bool,
    verbose: bool,
    verbose_format: str,
    **kwargs,
):
    """Watch repository changes and trigger actions (non-interactive mode)."""
    # The shutdown event is still necessary to signal between async components.
    # asyncio.run() will manage propagating the initial cancellation.
    shutdown_event = asyncio.Event()

    # Foundation's CLI framework handles logging setup via decorators

    log.info("Initializing watch command...")

    # Determine event log path if not provided
    if event_log is None:
        try:
            config = load_config(config_path)
            # Find first enabled repository
            for repo_id, repo_config in config.repositories.items():
                if repo_config.enabled and repo_config._path_valid:
                    event_log = SupsrcDirectories.get_log_dir(repo_config.path) / "events.jsonl"
                    log.info("Using repository log directory", repo_id=repo_id, event_log=str(event_log))
                    break
            else:
                # No repositories found, use temp directory
                event_log = Path(tempfile.gettempdir()) / "supsrc_events.json"
                log.warning("No enabled repositories found, using temp directory for logs")
        except Exception as e:
            log.warning("Failed to determine log directory", error=str(e))
            event_log = Path(tempfile.gettempdir()) / "supsrc_events.json"

    # Create Rich console for headless output
    from rich.console import Console

    console = Console(no_color=no_color, force_terminal=not no_color)

    orchestrator = WatchOrchestrator(
        config_path=config_path,
        shutdown_event=shutdown_event,
        app=None,  # No TUI
        console=console,
        event_log_path=event_log,
        use_color=not no_color,
        use_ascii=use_ascii,
        verbose=verbose,
        verbose_format=verbose_format,
        app_log_path=app_log,
    )

    exit_code = _run_headless_orchestrator(orchestrator)

    log.info("'watch' command finished.")
    if exit_code != 0:
        sys.exit(exit_code)


# 🔼⚙️🔚
