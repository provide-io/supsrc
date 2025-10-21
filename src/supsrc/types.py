# supsrc/types.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# supsrc/types.py
#
"""Common type definitions to avoid circular imports."""

from typing import TypeAlias

from supsrc.state import RepositoryState

# Type alias for repository states mapping
RepositoryStatesMap: TypeAlias = dict[str, RepositoryState]


# 🔼⚙️
# 🔼⚙️🧱🪄
