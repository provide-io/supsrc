#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Default configurations for event processing and atomic save detection."""

from __future__ import annotations

# Time windows for event grouping (milliseconds)
DEFAULT_BUFFER_WINDOW_MS = 100  # Reduced from 500ms for better TUI responsiveness
DEFAULT_ATOMIC_DETECTION_WINDOW_MS = 100  # Similar to chokidar's approach

# Confidence thresholds for operation detection
DEFAULT_MIN_CONFIDENCE = 0.7
DEFAULT_ATOMIC_SAVE_CONFIDENCE = 0.9

# Temporary file patterns for atomic save detection
# These patterns are used to identify temporary files created during atomic saves
DEFAULT_TEMP_FILE_PATTERNS = [
    # VSCode, Sublime Text patterns
    r"\..*\.tmp\.\w+$",  # .file.tmp.xxxxx
    r".*\.tmp\.\d+$",  # file.tmp.12345
    # Vim patterns
    r".*~$",  # file~
    r"\..*\.sw[po]$",  # .file.swp, .file.swo
    # Emacs patterns
    r"^#.*#$",  # #file#
    r"^\.#.*",  # .#file...
    # Generic backup and temp patterns
    r".*\.bak$",  # file.bak
    r".*\.backup$",  # file.backup
    r".*\.orig$",  # file.orig
    r".*\.tmp$",  # file.tmp
    # Editor-specific patterns
    r".*\.tmpNSURD.*",  # Some macOS editors
    r".*\.temp$",  # file.temp
]

# Base name extraction patterns for relating temp files to originals
# Format: (pattern, capture_group_or_function)
DEFAULT_BASE_NAME_PATTERNS = [
    (r"^\.(.*)\.tmp\.\w+$", 1),  # .file.tmp.xxxxx -> file
    (r"^(.*)\.tmp\.\d+$", 1),  # file.tmp.12345 -> file
    (r"^(.*)~$", 1),  # file~ -> file
    (r"^\.(.*)\.sw[po]$", 1),  # .file.swp -> file (but keep the leading dot)
    (r"^#(.*)#$", 1),  # #file# -> file
    (r"^\.#(.*)$", 1),  # .#file... -> file
    (r"^(.*)\.bak$", 1),  # file.bak -> file
    (r"^(.*)\.backup$", 1),  # file.backup -> file
    (r"^(.*)\.orig$", 1),  # file.orig -> file
    (r"^(.*)\.tmp$", 1),  # file.tmp -> file
    (r"^(.*)\.temp$", 1),  # file.temp -> file
]

# Operation types for display in event feed
DEFAULT_OPERATION_DISPLAY_NAMES = {
    "atomic_rewrite": "Updated",
    "single_file": "Modified",
    "batch_operation": "Batch Updated",
    "backup_operation": "Backed Up",
}

# Event grouping modes
GROUPING_MODE_OFF = "off"
GROUPING_MODE_SIMPLE = "simple"
GROUPING_MODE_SMART = "smart"

DEFAULT_GROUPING_MODE = GROUPING_MODE_SMART

# 🔼⚙️🔚
