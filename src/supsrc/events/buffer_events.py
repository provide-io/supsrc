# supsrc/events/buffer_events.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Buffered event types for the event buffering system.





"""


@attrs.define(frozen=True)
class BufferedFileChangeEvent(Event):
    """A buffered/grouped file change event for cleaner TUI display."""
