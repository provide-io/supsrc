# supsrc/engines/git/operations.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Git operation helpers and utilities for the GitEngine.



log = get_logger(__name__)

# --- Constants for Change Summary ---
MAX_SUMMARY_FILES = 10
SUMMARY_ADDED_PREFIX = "A "
SUMMARY_MODIFIED_PREFIX = "M "
SUMMARY_DELETED_PREFIX = "D "
SUMMARY_RENAMED_PREFIX = "R "  # R old -> new
SUMMARY_TYPECHANGE_PREFIX = "T "


"""


class GitOperationsHelper:
    """Helper class for Git repository operations and utilities."""
