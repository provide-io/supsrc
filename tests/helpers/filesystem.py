#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Filesystem helpers for tests that delete trees git has written into."""

from __future__ import annotations

from pathlib import Path
import shutil
import stat

__all__ = ["remove_tree"]


def remove_tree(path: Path) -> None:
    """Delete a directory tree, including read-only files.

    Git writes loose objects under ``.git/objects`` with the read-only bit set.
    Windows refuses ``os.unlink`` on such a file, while POSIX unlink depends only
    on write access to the containing directory. Clearing the bit first makes the
    removal behave the same on both.
    """
    for child in path.rglob("*"):
        if child.is_file():
            child.chmod(child.stat().st_mode | stat.S_IWRITE)
    shutil.rmtree(path)
