# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""CLI command for launching the supsrc TUI dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import io
import logging
import os
from pathlib import Path
import signal
import sys
from typing import Protocol, cast

import click
from provide.foundation.cli.decorators import logging_options
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger


class SupsrcTuiAppProtocol(Protocol):
    def __init__(self, *, config_path: Path, cli_shutdown_event: asyncio.Event) -> None: ...

    def run(self) -> None: ...


try:
    _tui_module = importlib.import_module("supsrc.tui.app")
except ImportError:
    SupsrcTuiApp: type[SupsrcTuiAppProtocol] | None = None
    TEXTUAL_AVAILABLE = False
else:
    SupsrcTuiApp = cast(type[SupsrcTuiAppProtocol], _tui_module.SupsrcTuiApp)
    TEXTUAL_AVAILABLE = True

log: StructLogger = get_logger(__name__)

_shutdown_requested = asyncio.Event()


class _NullIO(io.TextIOWrapper):
    """A null text stream that discards all output.

    This is used to suppress stdout/stderr during TUI operation to prevent
    log messages from corrupting the Textual display.
    """

    def __init__(self) -> None:
        # Open /dev/null as the underlying binary stream
        self._devnull = open(os.devnull, "w")  # noqa: SIM115
        super().__init__(io.BytesIO(), encoding="utf-8", write_through=True)

    def write(self, s: str) -> int:
        """Discard all writes."""
        return len(s)

    def writelines(self, lines: list[str]) -> None:
        """Discard all writes."""

    def flush(self) -> None:
        """No-op flush."""

    def close(self) -> None:
        """Close the underlying /dev/null handle."""
        if hasattr(self, "_devnull") and self._devnull:
            self._devnull.close()


async def _handle_signal_async(sig: int):
    signame = signal.Signals(sig).name
    base_log = get_logger(__name__)
    base_log.warning("Received shutdown signal", signal=signame, signal_num=sig)
    if not _shutdown_requested.is_set():
        base_log.info("Setting shutdown requested event.")
        _shutdown_requested.set()
    else:
        base_log.warning("Shutdown already requested, signal ignored.")


def _get_tui_log_path() -> Path:
    """Get the TUI log file path in ~/.supsrc/log/ directory.

    Returns:
        Path to the TUI log file at ~/.supsrc/log/tui.log
    """
    log_dir = Path.home() / ".supsrc" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "tui.log"


class _TUIFileHandler(logging.FileHandler):
    """File handler that marks itself as a TUI handler for identification."""

    is_tui_handler = True


def _remove_all_console_handlers() -> None:
    """Aggressively remove ALL console/stream handlers from ALL loggers.

    This is called both during setup and periodically to ensure no console
    output can corrupt the TUI display.
    """
    # Remove from root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)

    # Remove from all named loggers
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        try:
            named_logger = logging.getLogger(logger_name)
            for handler in named_logger.handlers[:]:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    named_logger.removeHandler(handler)
        except Exception:
            pass


def _setup_tui_logging(log_file_path: Path) -> logging.FileHandler:
    """Configure logging to write ONLY to file, preventing TUI corruption.

    Args:
        log_file_path: Path to the log file

    Returns:
        The file handler that was created
    """
    import json

    from attrs import evolve
    from provide.foundation import LoggingConfig, TelemetryConfig, get_hub
    import structlog

    # Ensure log directory exists
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure Foundation with file-only logging
    base_config = TelemetryConfig.from_env()
    telemetry_config = evolve(
        base_config,
        service_name="supsrc",
        logging=LoggingConfig(
            console_formatter="json",
            default_level="DEBUG",
            das_emoji_prefix_enabled=False,
            logger_name_emoji_prefix_enabled=False,
            log_file=log_file_path,
            foundation_log_output="/dev/null",
        ),
    )
    hub = get_hub()
    hub.initialize_foundation(telemetry_config)

    # Register eventset (ignore errors)
    try:
        from provide.foundation.eventsets.registry import register_event_set

        from supsrc.telemetry import SUPSRC_EVENT_SET

        register_event_set(SUPSRC_EVENT_SET)
    except Exception:
        pass

    # CRITICAL: Force ALL logging to file only - remove console handlers first
    _remove_all_console_handlers()

    # Create single file-only handler with JSON formatting
    class TUIFileFormatter(logging.Formatter):
        """JSON formatter for TUI file logs."""

        def format(self, record: logging.LogRecord) -> str:
            log_data = {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if hasattr(record, "extra") and record.extra:
                log_data["extra"] = record.extra
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_data)

    root_logger = logging.getLogger()

    # Check if we already have a TUI file handler (avoid duplicates)
    has_tui_handler = any(getattr(h, "is_tui_handler", False) for h in root_logger.handlers)

    if not has_tui_handler:
        file_handler = _TUIFileHandler(str(log_file_path), encoding="utf-8", mode="a")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(TUIFileFormatter())
        root_logger.addHandler(file_handler)
    else:
        # Find existing TUI handler
        file_handler = next(h for h in root_logger.handlers if getattr(h, "is_tui_handler", False))

    root_logger.setLevel(logging.DEBUG)

    # Monkey-patch logging.getLogger to strip console handlers from new loggers
    _original_get_logger = logging.getLogger

    def _file_only_get_logger(name: str | None = None) -> logging.Logger:
        """Get logger that only writes to file, not console."""
        logger_obj = _original_get_logger(name)
        for h in logger_obj.handlers[:]:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                logger_obj.removeHandler(h)
        return logger_obj

    logging.getLogger = _file_only_get_logger

    # Configure structlog to use file-only output via stdlib
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,  # Don't cache - we need fresh loggers
    )

    return file_handler


@click.command(name="sui")
@click.option(
    "-c",
    "--config-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=str),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@logging_options
@click.pass_context
def sui_cli(ctx: click.Context, config_path: Path | str, **kwargs):
    """Supsrc User Interface - Interactive dashboard for monitoring repositories."""
    config_path = Path(config_path)
    log_file_path = _get_tui_log_path()

    # Check for TUI dependencies BEFORE suppressing output
    if not TEXTUAL_AVAILABLE or SupsrcTuiApp is None:
        log.error("TUI dependencies not installed for 'sui' command.")
        click.echo(
            "Error: The 'sui' command requires the 'textual' library, provided by the 'tui' extra.",
            err=True,
        )
        click.echo("Hint: pip install 'supsrc[tui]' or uv pip install 'supsrc[tui]'", err=True)
        ctx.exit(1)
        return

    # Save original streams for restoration
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    # Create null streams that persist for entire TUI lifetime
    null_stdout = _NullIO()
    null_stderr = _NullIO()

    try:
        # CRITICAL: Suppress BOTH stdout and stderr to prevent TUI corruption
        # This must happen BEFORE logging setup to catch any initialization output
        sys.stdout = null_stdout
        sys.stderr = null_stderr

        # Set up file-only logging (ignore errors - TUI can run without logging)
        with contextlib.suppress(Exception):
            _setup_tui_logging(log_file_path)

        log.info("Initializing interactive dashboard...")
        log.debug("Launching interactive dashboard", config_path=str(config_path))

        # Restore streams for Textual - it needs real terminal access
        # Textual will manage the terminal itself
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        # Run the TUI app - Textual takes over terminal control
        app = SupsrcTuiApp(config_path=config_path, cli_shutdown_event=_shutdown_requested)
        app.run()

    except KeyboardInterrupt:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        click.echo("\nAborted by user.", err=True)
        ctx.exit(1)
    except Exception as e:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        click.echo(f"\nAn error occurred: {e}", err=True)
        ctx.exit(1)
    finally:
        # Always restore original streams
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        # Clean up null streams
        null_stdout.close()
        null_stderr.close()


# 🔼⚙️🔚
