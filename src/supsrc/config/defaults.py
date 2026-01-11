#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Centralized default values for supsrc configuration.
All defaults are defined here instead of inline in field definitions."""

DEFAULT_WATCH_ACTIVE_INTERVAL = 1.0  # Check every second when timers are active
DEFAULT_WATCH_IDLE_INTERVAL = 10.0  # Check every 10 seconds when idle

# =================================
# Event processor defaults
# =================================
DEFAULT_DEBOUNCE_DELAY = 0.25  # 250 milliseconds

# =================================
# Timer defaults
# =================================
DEFAULT_TIMER_UPDATE_INTERVAL = 1.0  # Update timer countdown every second

# =================================
# Event buffer defaults
# =================================
DEFAULT_EVENT_BUFFER_WINDOW_MS = 500  # Buffer events for 500ms
DEFAULT_EVENT_BUFFER_ENABLED = True  # Enable event buffering by default

# Mode-specific grouping modes (Foundation bugs now fixed!)
DEFAULT_EVENT_BUFFER_GROUPING_MODE_TUI = "smart"  # Clean TUI with atomic detection
DEFAULT_EVENT_BUFFER_GROUPING_MODE_HEADLESS = "simple"  # Reliable headless monitoring

# Legacy fallback for backwards compatibility
DEFAULT_EVENT_BUFFER_GROUPING_MODE = "simple"  # Use simple as safe default

# 🔼⚙️🔚
