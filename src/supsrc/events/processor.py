# supsrc/events/processor.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Consumes filesystem events, checks rules, manages timers, and triggers actions.



if TYPE_CHECKING:

log = get_logger("runtime.event_processor")


"""


class EventProcessor:
    """Consumes events, checks rules, and delegates actions."""
