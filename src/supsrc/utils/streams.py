#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Stream utilities for supsrc.

Provides custom stream implementations for managing output redirection."""

from __future__ import annotations

import io
from typing import Any


class NoOpStream:
    """A stream that discards all output.

    Used to suppress console logging while preserving file logging functionality.
    Implements the minimal TextIO interface required by structlog and Foundation logger.
    """

    def write(self, data: str) -> int:
        """Discard all written data."""
        return len(data)

    def flush(self) -> None:
        """No-op flush operation."""

    def fileno(self) -> int:
        """Raise UnsupportedOperation as NoOpStream has no file descriptor."""
        raise io.UnsupportedOperation("NoOpStream has no file descriptor")

    def isatty(self) -> bool:
        """Return False as NoOpStream is not a terminal."""
        return False

    def readable(self) -> bool:
        """Return False as NoOpStream is not readable."""
        return False

    def writable(self) -> bool:
        """Return True as NoOpStream accepts writes (but discards them)."""
        return True

    def seekable(self) -> bool:
        """Return False as NoOpStream is not seekable."""
        return False

    def close(self) -> None:
        """No-op close operation."""

    def closed(self) -> bool:
        """Return False as NoOpStream is always open."""
        return False

    def __enter__(self) -> NoOpStream:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""


# 🔼⚙️🔚
