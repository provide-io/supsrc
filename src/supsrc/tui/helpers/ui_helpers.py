# src/supsrc/tui/helpers/ui_helpers.py

"""
UI helper methods for the TUI application.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger("tui.ui_helpers")


class UIHelperMixin:
    """Mixin containing UI helper methods for the TUI."""

    def _check_external_shutdown(self) -> None:
        """Check for external shutdown signals and quit if detected."""
        if self._cli_shutdown_event.is_set() and not self._is_shutting_down:
            log.warning("External shutdown detected (CLI signal). Triggering quit.")
            self.action_quit()

    def _update_countdown_display(self) -> None:
        """Update countdown displays for all repositories."""
        try:
            # Add diagnostic logging to verify this method is being called
            log.debug("Periodic countdown update called")

            if hasattr(self, "_orchestrator") and self._orchestrator:
                # Update countdown for each repository state
                active_timers = 0
                for repo_state in self._orchestrator.repo_states.values():
                    repo_state.update_timer_countdown()
                    if repo_state.timer_seconds_left is not None:
                        active_timers += 1
                        log.debug(f"Active timer: {repo_state.repo_id} = {repo_state.timer_seconds_left}s")

                log.debug(f"Updated {len(self._orchestrator.repo_states)} repo states, {active_timers} active timers")

                # Update only the timer column directly to avoid cursor jumping
                self._update_timer_columns_only()
            else:
                log.warning("No orchestrator available for countdown update")
        except Exception as e:
            # Use warning level to make errors more visible during debugging
            log.warning(f"Error updating countdown display: {e}", exc_info=True)

    def _update_timer_columns_only(self) -> None:
        """Update only the timer column for all repositories to avoid cursor jumping."""
        try:
            from textual.widgets import DataTable

            from supsrc.tui.utils import get_countdown_display

            table = self.query_one("#repository_table", DataTable)

            if hasattr(self, "_orchestrator") and self._orchestrator:
                for repo_id_str, repo_state in self._orchestrator.repo_states.items():
                    if str(repo_id_str) in table.rows:
                        try:
                            row_index = table.get_row_index(str(repo_id_str))
                            timer_display = get_countdown_display(repo_state.timer_seconds_left)
                            # Update only column 1 (timer column) to avoid full row refresh
                            table.update_cell(row_index, 1, timer_display)
                            log.debug(
                                "Updated timer column",
                                repo_id=str(repo_id_str),
                                timer_seconds_left=repo_state.timer_seconds_left,
                                timer_display=repr(timer_display),
                                row_index=row_index,
                            )
                        except Exception as e:
                            # Log the error but DO NOT fall back to StateUpdate to prevent cursor jumping
                            log.warning(f"Failed to update timer cell for {repo_id_str}, skipping update: {e}", exc_info=True)
                            # Continue to next repository instead of breaking/posting StateUpdate
                            continue
        except Exception as e:
            # Log the error but DO NOT fall back to StateUpdate to prevent cursor jumping
            log.warning(f"Error in timer column update, skipping timer updates: {e}", exc_info=True)

    def _update_sub_title(self, text: str) -> None:
        """Update subtitle safely."""
        try:
            self.sub_title = text
        except Exception as e:
            log.warning("Failed to update TUI sub-title", error=str(e))

    def _get_level_style(self, level_name: str) -> str:
        """Get style for log level."""
        level = level_name.upper()
        styles = {
            "CRITICAL": "bold white on red",
            "ERROR": "bold red",
            "WARNING": "yellow",
            "INFO": "green",
            "DEBUG": "dim blue",
            "SUCCESS": "bold green",
        }
        return styles.get(level, "white")
