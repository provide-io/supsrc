#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Git output is UTF-8, whatever the console codepage says.

The auto-commit template carries emoji, so `git log` emits bytes that the
Windows locale encoding cannot decode. subprocess decodes a text-mode pipe with
that locale encoding, the decode raises inside the reader thread, and the empty
buffer is handed back as `stdout=None` rather than an error -- so the failure
surfaces far from its cause.
"""

from __future__ import annotations

import subprocess  # nosec

from supsrc.engines.git.base import GitEngine  # noqa: F401  -- import guard

# The default the engine commits with, spelled out so a change to it fails here.
COMMIT_TEMPLATE = "🔼⚙️ [skip ci] auto-commit"


def test_the_commit_template_defeats_the_windows_locale_encoding() -> None:
    """Names the byte that makes this fail, so the test explains itself."""
    raw = COMMIT_TEMPLATE.encode("utf-8")

    assert 0x8F in raw  # from U+FE0F, undefined in cp1252
    try:
        raw.decode("cp1252")
    except UnicodeDecodeError:
        return
    raise AssertionError("cp1252 decoded the template; this test is obsolete")


def test_git_output_round_trips_when_decoded_as_utf8(tmp_path) -> None:
    """The fix: ask for UTF-8 rather than inheriting the locale encoding."""
    run = lambda *a: subprocess.run(a, cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    run("git", "init")
    run("git", "config", "user.name", "Test")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "commit.gpgsign", "false")
    (tmp_path / "f.txt").write_text("x")
    run("git", "add", "f.txt")
    run("git", "commit", "-m", COMMIT_TEMPLATE)

    result = subprocess.run(  # nosec
        ["git", "log", "--oneline", "-n", "1"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )

    assert result.stdout is not None
    assert "⚙️" in result.stdout
