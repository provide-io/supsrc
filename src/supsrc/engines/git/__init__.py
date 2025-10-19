# supsrc/engines/git/__init__.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# engines/git/__init__.py
#
"""
Git Engine implementation for supsrc.
"""

from .base import GitEngine
from .info import GitRepoSummary

__all__ = ["GitEngine", "GitRepoSummary"]

# 🔼⚙️
# 🔼⚙️📦🪄
