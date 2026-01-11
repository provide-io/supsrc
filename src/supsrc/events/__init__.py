#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Supsrc Events Package.

This package provides a generic event system for supsrc components.
Any component can emit events that implement the Event protocol."""

from supsrc.events.base import BaseEvent
from supsrc.events.collector import EventCollector
from supsrc.events.feed import EventFeed
from supsrc.events.protocol import Event

__all__ = [
    "BaseEvent",
    "Event",
    "EventCollector",
    "EventFeed",
]

# 🔼⚙️🔚
