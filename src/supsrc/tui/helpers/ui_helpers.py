# src/supsrc/tui/helpers/ui_helpers.py

"""
UI helper methods for the TUI application.
"""

from __future__ import annotations

import structlog
from textual.containers import Container

from supsrc.tui.messages import StateUpdate

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
            if hasattr(self, "_orchestrator") and self._orchestrator:
                # Update countdown for each repository state
                for repo_state in self._orchestrator.repo_states.values():
                    repo_state.update_timer_countdown()

                # Trigger a state update to refresh the display with actual state objects
                self.post_message(StateUpdate(self._orchestrator.repo_states))
        except Exception as e:
            log.debug(f"Error updating countdown: {e}")

    def watch_show_detail_pane(self, show_detail: bool) -> None:
        """Update layout when detail pane visibility changes."""
        try:
            detail_pane_container = self.query_one("#detail_pane_container", Container)  # New ID

            if show_detail:
                detail_pane_container.styles.display = "block"
            else:
                detail_pane_container.styles.display = "none"
        except Exception as e:
            log.error("Error updating detail pane visibility", error=str(e))  # Updated log message

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
