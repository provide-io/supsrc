#
# supsrc/state.py
#
"""
Defines the dynamic state management models for monitored repositories in supsrc.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional

import structlog
from attrs import define, field, mutable

# Logger specific to state management
log: structlog.stdlib.BoundLogger = structlog.get_logger("state")


class RepositoryStatus(Enum):
    """Enumeration of possible operational states for a monitored repository."""

    IDLE = auto()  # No changes detected or operation complete.
    CHANGED = auto()  # Changes detected, awaiting trigger condition.
    TRIGGERED = auto() # Trigger condition met, action pending/queued.
    COMMITTING = auto()  # Git commit operation in progress.
    PUSHING = auto()  # Git push operation in progress.
    ERROR = auto()  # An error occurred, requires attention or clears on next success.


@mutable(slots=True)
class RepositoryState:
    """
    Holds the dynamic state for a single monitored repository.

    This class is mutable because its fields are updated frequently during
    the monitoring process (e.g., last change time, status, timer handles).
    """

    repo_id: str = field()  # The unique identifier for the repository
    status: RepositoryStatus = field(default=RepositoryStatus.IDLE)
    last_change_time: Optional[datetime] = field(default=None) # Timezone-aware (UTC)
    save_count: int = field(default=0)
    error_message: Optional[str] = field(default=None)
    # Holds the handle for the asyncio timer used by inactivity triggers.
    # This allows cancellation if new changes arrive before the timer fires.
    inactivity_timer_handle: Optional[asyncio.TimerHandle] = field(default=None)

    # Consider adding:
    # last_commit_hash: Optional[str] = field(default=None)
    # last_push_time: Optional[datetime] = field(default=None)
    # last_error_time: Optional[datetime] = field(default=None)

    def __attrs_post_init__(self):
        """Log the initial state upon creation."""
        log.debug(
            "Initialized repository state",
            repo_id=self.repo_id,
            initial_status=self.status.name,
        )

    def update_status(self, new_status: RepositoryStatus, error_msg: Optional[str] = None) -> None:
        """ Safely updates the status and optionally logs errors. """
        old_status = self.status
        self.status = new_status
        if new_status == RepositoryStatus.ERROR:
            self.error_message = error_msg or "Unknown error"
            # Optionally set last_error_time here
            log.warning(
                "Repository status changed to ERROR",
                repo_id=self.repo_id,
                previous_status=old_status.name,
                error=self.error_message,
            )
        elif old_status == RepositoryStatus.ERROR and new_status != RepositoryStatus.ERROR:
             log.info(
                 "Repository status recovered from ERROR",
                 repo_id=self.repo_id,
                 new_status=new_status.name,
             )
             self.error_message = None # Clear previous error on recovery
        else:
            log.debug(
                "Repository status changed",
                repo_id=self.repo_id,
                old_status=old_status.name,
                new_status=new_status.name,
            )
        # Reset relevant fields on transition back to IDLE or CHANGED?
        if new_status in (RepositoryStatus.IDLE, RepositoryStatus.CHANGED):
             self.cancel_inactivity_timer() # Ensure timer is cleared if we reset state
             # Consider resetting save_count only after successful commit/push?

    def record_change(self) -> None:
        """Records a file change event, updating time and count."""
        now_utc = datetime.now(timezone.utc)
        self.last_change_time = now_utc
        self.save_count += 1
        self.update_status(RepositoryStatus.CHANGED) # Move to CHANGED state
        log.debug(
            "Recorded file change",
            repo_id=self.repo_id,
            change_time_utc=now_utc.isoformat(),
            new_save_count=self.save_count,
        )
        # Cancel any pending inactivity timer, as a new change just arrived.
        self.cancel_inactivity_timer()

    def reset_after_action(self) -> None:
        """ Resets state after a successful commit/push sequence. """
        log.debug("Resetting state after successful action", repo_id=self.repo_id)
        self.save_count = 0
        self.last_change_time = None # Or keep last successful action time?
        self.cancel_inactivity_timer()
        self.update_status(RepositoryStatus.IDLE)


    def set_inactivity_timer(self, handle: asyncio.TimerHandle) -> None:
        """Stores the handle for a scheduled inactivity timer."""
        # Cancel any previous timer before setting a new one
        self.cancel_inactivity_timer()
        self.inactivity_timer_handle = handle
        log.debug("Inactivity timer set", repo_id=self.repo_id)

    def cancel_inactivity_timer(self) -> None:
        """Cancels the pending inactivity timer, if one exists."""
        if self.inactivity_timer_handle:
            log.debug("Cancelling existing inactivity timer", repo_id=self.repo_id)
            self.inactivity_timer_handle.cancel()
            self.inactivity_timer_handle = None
        else:
            log.debug("No active inactivity timer to cancel", repo_id=self.repo_id)


# 🔼⚙️
