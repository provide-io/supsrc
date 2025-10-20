# supsrc/events/__init__.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Supsrc Events Package.

This package provides a generic event system for supsrc components.
Any component can emit events that implement the Event protocol.

"""

__all__ = [
    "BaseEvent",
    "Event",
    "EventCollector",
    "EventFeed",
]
# 🔼⚙️📦🪄
