# supsrc/events/buffer/core.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
"""
Core event buffer orchestration for reducing TUI event log spam.



    DEFAULT_BUFFER_WINDOW_MS,
    DEFAULT_GROUPING_MODE,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_TEMP_FILE_PATTERNS,
    GROUPING_MODE_OFF,
    GROUPING_MODE_SIMPLE,
    GROUPING_MODE_SMART,
)

log = get_logger("events.buffer.core")


class EventBuffer:
    """Buffers and groups filesystem events to reduce TUI log spam.

"""
