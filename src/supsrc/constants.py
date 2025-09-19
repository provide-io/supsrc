#
# constants.py
#
"""
Default values and constants for supsrc.
"""

from __future__ import annotations

# Watch command defaults
DEFAULT_WATCH_ACTIVE_INTERVAL = 1.0  # Check every second when timers are active
DEFAULT_WATCH_IDLE_INTERVAL = 10.0  # Check every 10 seconds when idle

# Event processor defaults
DEFAULT_DEBOUNCE_DELAY = 0.25  # 250 milliseconds

# Timer defaults
DEFAULT_TIMER_UPDATE_INTERVAL = 1.0  # Update timer countdown every second
