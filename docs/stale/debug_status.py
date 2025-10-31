#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Debug script to monitor status changes and detect red X appearances.
Run this to help identify when and why the red X appears."""

import sys
from pathlib import Path

# Add the source directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from supsrc.state.runtime import STATUS_EMOJI_MAP


def monitor_status_changes():
    """Print all possible status transitions to help debug."""
    print("🔍 Debugging Status Emojis:")
    print("=" * 50)

    for status, emoji in STATUS_EMOJI_MAP.items():
        print(f"{indicator} {status.name:25} -> {emoji}")

    print("\n📋 When you see the red X, check the logs for:")
    print("- 'Status check failed during action'")
    print("- 'Repository is clean during action - external commit detected'")
    print("- Any ERROR status transitions")
    print("- The specific RepositoryStatus that triggered the ❌")


if __name__ == "__main__":
    monitor_status_changes()

# 🔼⚙️🔚
