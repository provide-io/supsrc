#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Base protocol for verbose event formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from supsrc.events.protocol import Event


class VerboseFormatter(Protocol):
    """Protocol for verbose event detail formatters."""

    def format_verbose_details(self, event: Event) -> list[str]:
        """Format verbose details for an event.

        Args:
            event: Event to format

        Returns:
            List of strings to print (one per line)
        """
        ...


# 🔼⚙️🔚
