# supsrc/events/monitor.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Filesystem monitoring events.





"""


@attrs.define(frozen=True)
class FileChangeEvent(BaseEvent):
    """Event emitted when a monitored file changes."""
