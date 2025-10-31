#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Timer management for the TUI application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger
from textual.timer import Timer

if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp

log = get_logger(__name__)


class TimerManager:
    """Manages application timers with proper lifecycle handling."""

    def __init__(self, app: SupsrcTuiApp) -> None:
        self.app = app
        self._timers: dict[str, Timer] = {}
        self._logger = log.bind(component="TimerManager")

    def create_timer(
        self, name: str, interval: float, callback: callable, repeat: bool = True
    ) -> Timer:
        """Create a new timer with proper tracking."""
        if name in self._timers:
            self.stop_timer(name)

        timer = self.app.set_interval(interval, callback, name=name)
        self._timers[name] = timer
        self._logger.debug("Timer created", name=name, interval=interval)
        return timer

    def stop_timer(self, name: str) -> bool:
        """Stop a specific timer."""
        if name not in self._timers:
            return False

        timer = self._timers[name]
        success = True
        try:
            # Check if the timer is active by inspecting its internal handle
            if hasattr(timer, "_Timer__handle") and timer._Timer__handle is not None:
                timer.stop()
        except Exception as e:
            self._logger.error("Error stopping timer", name=name, error=str(e))
            success = False
        finally:
            if name in self._timers:
                del self._timers[name]
            self._logger.debug("Timer stopped or already inactive", name=name)
        return success

    def stop_all_timers(self) -> None:
        """Stop all managed timers."""
        timer_names = list(self._timers.keys())
        for name in timer_names:
            self.stop_timer(name)
        self._logger.debug("All timers stopped", count=len(timer_names))


# 🔼⚙️🔚
