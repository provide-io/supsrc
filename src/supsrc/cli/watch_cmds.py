#
# supsrc/cli/watch_cmds.py
#

import asyncio
import logging
import signal
from prompt_toolkit.shortcuts import PromptSession, print_formatted_text
from prompt_toolkit.formatted_text import HTML
import sys
from contextlib import suppress
from pathlib import Path

import click
import structlog
from attrs import define, field # Added for ParsedCommand

# --- Rich Imports ---
from rich.console import Console

# Import logging utilities
from supsrc.cli.utils import logging_options, setup_logging_from_context
from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.state import RepositoryState, RepositoryStatus # Added RepositoryState, RepositoryStatus
from supsrc.state import RepositoryStatesMap # Added RepositoryStatesMap (though might be implicitly available via orchestrator type hints)

# Use absolute imports
from supsrc.telemetry import StructLogger

# --- Try importing TUI App Class ---
# (TUI import logic remains the same)
try:
    from supsrc.tui.app import SupsrcTuiApp
    TEXTUAL_AVAILABLE = True
    log_tui = structlog.get_logger("cli.watch.tui_check")
    log_tui.debug("Successfully imported supsrc.tui.app.SupsrcTuiApp.")
except ImportError as e:
    TEXTUAL_AVAILABLE = False
    SupsrcTuiApp = None
    log_tui = structlog.get_logger("cli.watch.tui_check")
    log_tui.debug("Failed to import supsrc.tui.app. Possible missing 'supsrc[tui]' install or error in tui module.", error=str(e))


log: StructLogger = structlog.get_logger("cli.watch")

# --- Global Shutdown Event & Signal Handler ---
_shutdown_requested = asyncio.Event()
async def _handle_signal_async(sig: int):
    signame = signal.Signals(sig).name
    base_log = structlog.get_logger("cli.watch.signal")
    base_log.warning("Received shutdown signal", signal=signame, signal_num=sig)
    if not _shutdown_requested.is_set():
        base_log.info("Setting shutdown requested event.")
        _shutdown_requested.set()
    else:
         base_log.warning("Shutdown already requested, signal ignored.")

# --- REPL Command Parsing ---
@define(frozen=True, slots=True)
class ParsedCommand:
    name: str
    args: tuple[str, ...] = field(converter=tuple)

def parse_command(input_str: str) -> ParsedCommand | None:
    """Parses a raw input string into a command and arguments."""
    stripped_input = input_str.strip()
    if not stripped_input:
        return None

    parts = stripped_input.split()
    command_name = parts[0].lower()
    arguments = tuple(parts[1:])
    return ParsedCommand(name=command_name, args=arguments)

# --- REPL Loop ---
async def repl_loop(session: PromptSession, orchestrator: WatchOrchestrator, shutdown_event: asyncio.Event):
    """Asynchronous REPL loop for non-TUI mode."""
    log.info("Starting REPL loop...")
    # Define some simple HTML styles for REPL messages
    # These could be moved to a central place if they grow
    HTML_ERROR = "<tomato>{message}</tomato>"
    HTML_INFO = "<skyblue>{message}</skyblue>"
    HTML_SUCCESS = "<seagreen>{message}</seagreen>"
    # Updated HTML_HELP
    HTML_HELP = "<violet>Available commands:\n" \
                "  help, h, ?        - Show this help message.\n" \
                "  list, repos       - List all configured repositories and their summary status.\n" \
                "  status [repo_id]  - Show detailed status for a specific repository or all repositories.\n" \
                "  pause <repo_id>   - Pause monitoring for a specific repository.\n" \
                "  resume <repo_id>  - Resume monitoring for a specific repository.\n" \
                "  details <repo_id> - Show more detailed information (e.g., commit log).\n" \
                "  quit, exit        - Exit the supsrc watch REPL.</violet>"

    try:
        while not shutdown_event.is_set():
            # Wrap the prompt and command processing with patch_stdout_context
            with session.patch_stdout_context():
                try:
                    command_str = await session.prompt_async("> ")
                    parsed_cmd = parse_command(command_str)

                    if parsed_cmd is None: # Empty input
                        continue

                    match parsed_cmd.name:
                        case "quit" | "exit":
                            print_formatted_text(HTML(HTML_INFO.format(message="Exiting REPL...")))
                            shutdown_event.set()
                            break # Exit the while loop to terminate REPL
                        case "help" | "h" | "?":
                            print_formatted_text(HTML(HTML_HELP))

                        case "list" | "repos":
                            repo_states_map = orchestrator.get_all_repository_states()
                            if not repo_states_map:
                                print_formatted_text(HTML(HTML_INFO.format(message="No repositories configured or found.")))
                            else:
                                lines = ["<bold>Monitored Repositories:</bold>"]
                                for repo_id, state in repo_states_map.items():
                                    status_emoji = state.display_status_emoji or STATUS_EMOJI_MAP.get(state.status, "❓")
                                    lines.append(f"  <skyblue>{repo_id}</skyblue>: {status_emoji} {state.status.name.title()}")
                                print_formatted_text(HTML("\n".join(lines)))

                        case "status":
                            repo_states_map = orchestrator.get_all_repository_states() # Get all for checking existence
                            if not parsed_cmd.args: # No repo_id provided, show all
                                if not repo_states_map:
                                    print_formatted_text(HTML(HTML_INFO.format(message="No repositories configured or found.")))
                                else:
                                    lines = ["<bold>All Repository Statuses:</bold>"]
                                    for repo_id, state in repo_states_map.items():
                                        status_emoji = state.display_status_emoji or STATUS_EMOJI_MAP.get(state.status, "❓")
                                        lines.append(f"  <skyblue>{repo_id}</skyblue>:")
                                        lines.append(f"    Status: {status_emoji} {state.status.name.title()}")
                                        lines.append(f"    Rule: <cyan>{state.active_rule_description or 'N/A'}</cyan> {state.rule_emoji or ''} {state.rule_dynamic_indicator or ''}")
                                        lines.append(f"    Action: <yellow>{state.action_description or 'N/A'}</yellow>")
                                        lines.append(f"    Last Change: {state.last_change_time.strftime('%Y-%m-%d %H:%M:%S %Z') if state.last_change_time else 'N/A'}")
                                        lines.append(f"    Last Commit: {state.last_commit_short_hash or 'N/A'} - {state.last_commit_message_summary or 'N/A'}")
                                    print_formatted_text(HTML("\n".join(lines)))

                            elif len(parsed_cmd.args) == 1:
                                repo_id_arg = parsed_cmd.args[0]
                                state = orchestrator.get_repository_state(repo_id_arg)
                                if state is None:
                                    print_formatted_text(HTML(HTML_ERROR.format(message=f"Repository '{repo_id_arg}' not found.")))
                                else:
                                    status_emoji = state.display_status_emoji or STATUS_EMOJI_MAP.get(state.status, "❓")
                                    lines = [f"<bold>Status for <skyblue>{state.repo_id}</skyblue>:</bold>"]
                                    lines.append(f"  Status: {status_emoji} {state.status.name.title()}")
                                    lines.append(f"  Rule: <cyan>{state.active_rule_description or 'N/A'}</cyan> {state.rule_emoji or ''} {state.rule_dynamic_indicator or ''}")
                                    lines.append(f"  Action: <yellow>{state.action_description or 'N/A'}</yellow>")
                                    if state.action_progress_total is not None:
                                        lines.append(f"    Progress: {state.action_progress_completed or 0}/{state.action_progress_total}")
                                    lines.append(f"  Last Change: {state.last_change_time.strftime('%Y-%m-%d %H:%M:%S %Z') if state.last_change_time else 'N/A'}")
                                    lines.append(f"  Save Count: {state.save_count}")
                                    lines.append(f"  Last Commit: {state.last_commit_short_hash or 'N/A'} - {state.last_commit_message_summary or 'N/A'}")
                                    lines.append(f"  Error: <tomato>{state.error_message or 'None'}</tomato>")
                                    print_formatted_text(HTML("\n".join(lines)))
                            else:
                                print_formatted_text(HTML(HTML_ERROR.format(message="Usage: status [repository_id]")))

                        case "pause":
                            if len(parsed_cmd.args) != 1:
                                print_formatted_text(HTML(HTML_ERROR.format(message="Usage: pause &lt;repository_id&gt;")))
                            else:
                                repo_id_arg = parsed_cmd.args[0]
                                success = orchestrator.pause_repository(repo_id_arg)
                                if success:
                                    print_formatted_text(HTML(HTML_SUCCESS.format(message=f"Repository '{repo_id_arg}' monitoring paused.")))
                                else:
                                    print_formatted_text(HTML(HTML_ERROR.format(message=f"Failed to pause monitoring for '{repo_id_arg}'. May already be paused or not found. Check logs.")))

                        case "resume":
                            if len(parsed_cmd.args) != 1:
                                print_formatted_text(HTML(HTML_ERROR.format(message="Usage: resume &lt;repository_id&gt;")))
                            else:
                                repo_id_arg = parsed_cmd.args[0]
                                success = orchestrator.resume_repository(repo_id_arg)
                                if success:
                                    print_formatted_text(HTML(HTML_SUCCESS.format(message=f"Repository '{repo_id_arg}' monitoring resumed.")))
                                else:
                                    print_formatted_text(HTML(HTML_ERROR.format(message=f"Failed to resume monitoring for '{repo_id_arg}'. May not be paused or not found. Check logs.")))

                        case "details":
                            if len(parsed_cmd.args) != 1:
                                print_formatted_text(HTML(HTML_ERROR.format(message="Usage: details &lt;repository_id&gt;")))
                            else:
                                repo_id_arg = parsed_cmd.args[0]
                                # Make sure to await the async orchestrator method
                                details_dict = await orchestrator.get_repository_details(repo_id_arg)
    
                                if not details_dict or details_dict.get("error"): # Check for error key from orchestrator
                                    error_msg = details_dict.get("error", f"Could not retrieve details for repository '{repo_id_arg}'.")
                                    print_formatted_text(HTML(HTML_ERROR.format(message=error_msg)))
                                elif not details_dict.get("commit_history"):
                                    print_formatted_text(HTML(HTML_INFO.format(message=f"No commit history found for repository '{repo_id_arg}'.")))
                                else:
                                    lines = [f"<bold>Commit History for <skyblue>{repo_id_arg}</skyblue>:</bold>"]
                                    commit_history = details_dict.get("commit_history", [])
                                    if not commit_history: # Should be caught by previous elif, but as a safeguard
                                         lines.append("  <dim>No commits found or history is empty.</dim>")
                                    else:
                                        for entry in commit_history:
                                            # Assuming entry is a string. If it's a dict/object, format accordingly.
                                            # Basic HTML escaping for safety, though prompt_toolkit's HTML might handle some.
                                            safe_entry = str(entry).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                                            lines.append(f"  {safe_entry}")
                                    print_formatted_text(HTML("\n".join(lines)))
    
                        case _:
                            print_formatted_text(HTML(HTML_ERROR.format(message=f"Unknown command: '{parsed_cmd.name}'. Type 'help' for available commands.")))

                except KeyboardInterrupt:
                    # This will be caught outside the 'with' block if it happens during prompt_async itself
                    # or if it's not caught by prompt_toolkit's own handling.
                    # For user pressing Ctrl+C at the prompt, prompt_async itself raises KeyboardInterrupt.
                    print_formatted_text(HTML(HTML_INFO.format(message="Ctrl+C pressed. Type 'quit' or 'exit' to exit or another command.")))
                    # Continue to the next iteration of the while loop, reprompting.
                    continue
                except EOFError: # Ctrl+D
                    print_formatted_text(HTML(HTML_INFO.format(message="Ctrl+D pressed. Exiting REPL...")))
                    shutdown_event.set()
                    break # Exit the while loop
                except Exception as e: # Catch any other unexpected error during REPL interaction
                    # Log the error using structlog
                    repl_log = log.bind(in_repl_loop=True) # Add context to the logger
                    repl_log.error("REPL input processing error", error=str(e), exc_info=True)
                    # Print a user-friendly error message to the REPL
                    print_formatted_text(HTML(HTML_ERROR.format(message=f"REPL Error: {e}")))
            # Removed the bare 'except KeyboardInterrupt' from here as it's handled inside the 'with' block's try/except
            # The outer try/except remains for EOFError and other unexpected errors that might occur
            # outside the 'with session.patch_stdout_context()' if the loop structure were different.
            # Given the current structure, most exceptions related to command processing are inside.
    finally:
        log.info("REPL loop finished.")
        if not shutdown_event.is_set(): # Ensure shutdown is signalled if REPL exits unexpectedly
            log.warning("REPL loop terminated unexpectedly, ensuring shutdown event is set.")
            shutdown_event.set()

# --- Click Command Definition ---
@click.command(name="watch")
@click.option(
    "-c", "--config-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True, envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).", show_envvar=True,
)
@click.option(
    "--tui", is_flag=True, default=False,
    help="Run with an interactive Text User Interface (requires 'supsrc[tui]')."
)
@logging_options # Add decorator
@click.pass_context
def watch_cli(ctx: click.Context, config_path: Path, tui: bool, **kwargs): # Add **kwargs
    """Monitor configured repositories for changes and trigger actions."""
    # Setup logging for this command
    # For TUI mode, this setup will apply unless SupsrcTuiApp overrides it.
    # The TUI part of watch_cli instantiates SupsrcTuiApp directly.
    # The separate `tui_cli` command also does this but has its own explicit setup.
    # We aim for consistency.
    log_file_in_ctx = ctx.obj.get("LOG_FILE") # Check if global --log-file was set
    # If watch --tui is used, and a log file is specified (globally or locally for watch),
    # then default file_only_logs to True for the TUI part.
    effective_file_only_logs = kwargs.get("file_only_logs")
    if tui and log_file_in_ctx and effective_file_only_logs is None: # if tui, log_file is set, and local file_only not set
        effective_file_only_logs = True
    elif effective_file_only_logs is None: # if not the tui-specific case above, ensure it's False if not set
        effective_file_only_logs = False


    setup_logging_from_context(
        ctx,
        local_log_level=kwargs.get("log_level"),
        local_log_file=kwargs.get("log_file"), # Allows watch to have its own log file
        local_json_logs=kwargs.get("json_logs"),
        local_file_only_logs=effective_file_only_logs
    )

    # def _cli_safe_log(level: str, msg: str, **kwargs): # Replaced with direct console prints or structlog
    #     with suppress(Exception): getattr(log, level)(msg, **kwargs)

    if tui:
        # (TUI logic remains the same)
        if not TEXTUAL_AVAILABLE or SupsrcTuiApp is None:
            click.echo("Error: TUI mode requires 'supsrc[tui]' to be installed and importable.", err=True)
            click.echo("Hint: pip install 'supsrc[tui]' or check for errors in src/supsrc/tui/app.py", err=True)
            ctx.exit(1)
        log.info("Initializing TUI mode...")
        app = SupsrcTuiApp(config_path=config_path, cli_shutdown_event=_shutdown_requested)
        app.run()
        log.info("TUI application finished.")

    else:
        # --- Standard Mode Logic ---
        console = Console() # Create Rich Console instance for non-REPL messages
        console.print("[dim]INFO:[/] Initializing standard 'watch' command (non-TUI with REPL)...")

        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            if loop.is_closed(): loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        except RuntimeError: loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)

        signals_to_handle = (signal.SIGINT, signal.SIGTERM); handlers_added = False
        log.debug(f"Adding signal handlers to loop {id(loop)}")
        try:
            for sig in signals_to_handle:
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_handle_signal_async(s)))
            handlers_added = True
            log.debug("Added signal handlers")
        except Exception as e:
            log.error("Failed to add signal handlers", error=str(e), exc_info=True)

        orchestrator = WatchOrchestrator(config_path=config_path, shutdown_event=_shutdown_requested, app=None, console=console)
        session = PromptSession()
        exit_code = 0

        orchestrator_task: asyncio.Task | None = None
        repl_task: asyncio.Task | None = None

        try:
            log.debug("Creating orchestrator and REPL tasks...")
            orchestrator_task = loop.create_task(orchestrator.run(), name="OrchestratorRun")
            repl_task = loop.create_task(repl_loop(session, orchestrator, _shutdown_requested), name="ReplLoop")

            log.debug(f"Running event loop {id(loop)} with orchestrator and REPL...")
            # Run both tasks concurrently
            # loop.run_until_complete(asyncio.gather(orchestrator_task, repl_task, return_exceptions=True))

            # More robust way to run and handle results/exceptions from gather
            # This structure allows us to determine which task failed if any.
            results = loop.run_until_complete(
                asyncio.gather(orchestrator_task, repl_task, return_exceptions=True)
            )

            for i, result in enumerate(results):
                task_name = "Orchestrator" if i == 0 else "REPL"
                if isinstance(result, Exception):
                    if isinstance(result, asyncio.CancelledError):
                        log.warning(f"{task_name} task was cancelled.")
                    else:
                        log.error(f"{task_name} task raised an exception", error=result, exc_info=result)
                        # Potentially set exit_code here if a specific task failure should cause non-zero exit
                        # For now, any exception in gather will lead to the generic exception block below
                else:
                    log.debug(f"{task_name} task completed normally with result: {result}")


            log.debug("All tasks (orchestrator, REPL) completed.")

        except KeyboardInterrupt:
            console.print("[bold yellow]KEYBOARD INTERRUPT:[/] Signal received. Initiating graceful shutdown...", highlight=False)
            log.warning("KeyboardInterrupt caught in main watch_cli. Signalling shutdown.")
            _shutdown_requested.set()
            exit_code = 130 # Standard exit code for Ctrl+C
        except asyncio.CancelledError: # Should ideally be caught by tasks themselves or by gather
            log.warning("Main gather operation was cancelled.")
            _shutdown_requested.set() # Ensure shutdown is signalled
            exit_code = 1
        except Exception as e: # Catch-all for other unexpected errors during setup or gather
            log.critical("High-level run failed (e.g., in asyncio.gather or task setup)", error=str(e), exc_info=True)
            console.print(f"[bold red]CRITICAL:[/] Orchestrator/REPL run failed: {e}", highlight=False)
            _shutdown_requested.set() # Ensure shutdown is signalled
            exit_code = 1
        finally:
            log.debug(f"watch_cli (non-TUI/REPL) finally block starting. Loop closed: {loop.is_closed()}")

            # --- Task Cleanup ---
            # Ensure shutdown_event is set to stop loops that might still be running
            if not _shutdown_requested.is_set():
                log.info("Ensuring shutdown_requested is set in finally block.")
                _shutdown_requested.set()

            tasks_to_cleanup = [t for t in [orchestrator_task, repl_task] if t and not t.done()]
            if tasks_to_cleanup:
                log.debug(f"Cancelling {len(tasks_to_cleanup)} outstanding tasks...")
                for task in tasks_to_cleanup:
                    task.cancel()
                # Give them a moment to process cancellation
                if not loop.is_closed():
                    loop.run_until_complete(asyncio.gather(*tasks_to_cleanup, return_exceptions=True))
                log.debug("Outstanding tasks cancellation processed.")

            # Gather any other remaining tasks (though orchestrator and repl should be the main ones)
            if not loop.is_closed():
                try:
                    all_remaining_tasks = [t for t in asyncio.all_tasks(loop=loop) if t is not asyncio.current_task(loop=loop) and not t.done()]
                    if all_remaining_tasks:
                        log.debug(f"Cleaning up {len(all_remaining_tasks)} other remaining tasks...")
                        for task in all_remaining_tasks: task.cancel()
                        loop.run_until_complete(asyncio.gather(*all_remaining_tasks, return_exceptions=True))
                        log.debug("Other remaining tasks cleanup processed.")
                except Exception as task_cleanup_exc:
                    log.error("Error during final other task cleanup", error=str(task_cleanup_exc))

            # --- Signal Handler and Logging Cleanup (similar to before) ---
            if handlers_added and not loop.is_closed():
                 log.debug("Removing signal handlers")
                 for sig in signals_to_handle:
                      with suppress(ValueError, RuntimeError, Exception): # Add general Exception
                           loop.remove_signal_handler(sig)
                           log.debug(f"Removed signal handler for {signal.Signals(sig).name}")

            log.debug("Shutting down standard logging...")
            with suppress(Exception): logging.shutdown() # Suppress errors during logging shutdown

            log.debug(f"Closing event loop {id(loop)}")
            if not loop.is_closed():
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    log.debug("Async generators shut down.")
                    loop.close()
                    log.info("Event loop closed.")
                except RuntimeError as e: # Specific handling for common shutdown error
                    if "cannot schedule new futures after shutdown" in str(e):
                        log.warning("Loop shutdown encountered scheduling issue, likely benign after cleanup.")
                    else: # Re-raise or log other RuntimeErrors
                        log.error("Runtime error during final event loop close", error=str(e), exc_info=True)
                except Exception as e: # Catch other unexpected errors
                     log.error("Error during final event loop close", error=str(e), exc_info=True)
            else:
                 log.warning("Event loop was already closed before final cleanup.")

        console.print("[dim]INFO:[/] 'watch' command with REPL finished.")
        if exit_code != 0:
            # Ensure console output is flushed before exiting with error
            console.file.flush() # For stdout/stderr if Console writes there
            sys.stdout.flush()
            sys.stderr.flush()
            sys.exit(exit_code)

# 🔼⚙️
