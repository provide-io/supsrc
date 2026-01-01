# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Worker helper methods for the TUI application."""

from __future__ import annotations

from provide.foundation.logger import get_logger
from textual.worker import Worker, WorkerState

from supsrc.tui.messages import RepoDetailUpdate

log = get_logger(__name__)


class WorkerHelperMixin:
    """Mixin containing worker helper methods for the TUI."""

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes, and exit the app when the main worker is done."""
        log.debug("Worker state changed", worker=event.worker.name, state=event.state)
        # Only act on terminal states: SUCCESS or ERROR. Ignore PENDING and RUNNING.
        if event.worker == self._worker and event.state in (WorkerState.SUCCESS, WorkerState.ERROR):
            log.info(
                f"Orchestrator worker has finished with state: {event.state!r}.",
            )
            # If the app is already shutting down, this is expected. We can exit cleanly.
            if self._is_shutting_down:
                self.exit(0)
            else:
                # Worker stopped unexpectedly - we should also exit
                log.warning("Orchestrator worker stopped unexpectedly. Exiting.")
                self._orchestrator = None
                self.exit(1)

    async def _fetch_repo_details_worker(self, repo_id: str) -> None:
        """Worker to fetch repository details."""
        if not self._orchestrator:
            return

        try:
            log.debug("Fetching repository details", repo_id=repo_id)
            details = await self._orchestrator.get_repository_details(repo_id)
            self.post_message(RepoDetailUpdate(repo_id, details))
        except Exception as e:
            log.error(
                "Error fetching repository details",
                repo_id=repo_id,
                error=str(e),
            )
            # Escape error message to prevent Rich markup issues
            error_str = str(e).replace("[", "\\[")
            error_details = {"commit_history": [f"[bold red]Error loading details: {error_str}[/bold red]"]}
            self.post_message(RepoDetailUpdate(repo_id, error_details))


# 🔼⚙️🔚
