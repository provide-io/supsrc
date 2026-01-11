#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""CLI utilities - now uses provide-foundation's CLI framework.

All logging options and decorators are now provided by:
- provide.foundation.cli.decorators.logging_options
- provide.foundation.cli.decorators.error_handler
- provide.foundation.context.CLIContext"""

from __future__ import annotations

# Re-export Foundation's CLI utilities for backwards compatibility
from provide.foundation.cli.decorators import (  # noqa: F401
    error_handler,
    logging_options,
)
from provide.foundation.context import CLIContext  # noqa: F401
from provide.foundation.logger import get_logger

# No custom setup needed - Foundation handles everything
log = get_logger(__name__)

# 🔼⚙️🔚
