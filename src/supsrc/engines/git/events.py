# supsrc/engines/git/events.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Git-specific events for repository operations.




"""


@attrs.define(frozen=True)
class GitCommitEvent(BaseEvent):
    """Event emitted when a git commit is performed."""
