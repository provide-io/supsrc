# supsrc/events/system.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
System and rule events.




"""


@attrs.define(frozen=True)
class RuleTriggeredEvent(BaseEvent):
    """Event emitted when a rule triggers an action."""
