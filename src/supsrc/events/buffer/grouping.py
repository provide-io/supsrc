# supsrc/events/buffer/grouping.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
"""
Event grouping strategies for simple time-window buffering.




log = get_logger("events.buffer.grouping")


def group_events_simple(events: list[FileChangeEvent]) -> list[BufferedFileChangeEvent]:
    """Group events using simple file-based grouping.

"""
