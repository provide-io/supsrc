#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Event collection and dispatching."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

log = get_logger("events.collector")


class EventCollector:
    """Collects and dispatches events to handlers.

    This is a simple, Pythonic event dispatcher that uses callables
    as handlers. It follows the observer pattern without complex abstractions.
    """

    def __init__(self) -> None:
        self._handlers: list[Callable[[Event], None]] = []

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler function to receive events.

        Args:
            handler: Callable that accepts an Event
        """
        self._handlers.append(handler)
        log.debug("Event handler subscribed", handler_count=len(self._handlers))

    def unsubscribe(self, handler: Callable[[Event], None]) -> None:
        """Unsubscribe a handler function.

        Args:
            handler: Handler to remove
        """
        try:
            self._handlers.remove(handler)
            log.debug("Event handler unsubscribed", handler_count=len(self._handlers))
        except ValueError:
            log.warning("Attempted to unsubscribe handler that was not subscribed")

    def emit(self, event: Event) -> None:
        """Emit an event to all subscribed handlers.

        Args:
            event: Event to emit

        Note:
            If a handler raises an exception, it's logged but doesn't
            prevent other handlers from running.
        """
        if len(self._handlers) == 0:
            log.warning(
                "No handlers subscribed to receive event",
                event_source=event.source,
                event_description=event.description,
            )
            return

        log.debug(
            "Emitting event",
            event_source=event.source,
            event_description=event.description,
            handler_count=len(self._handlers),
        )

        for handler in self._handlers:
            try:
                handler(event)
                log.debug("Event handler called successfully", handler=str(handler)[:50])
            except Exception as e:
                log.error(
                    "Event handler failed",
                    handler=str(handler),
                    error=str(e),
                    event_source=event.source,
                    exc_info=True,
                )


# 🔼⚙️🔚
