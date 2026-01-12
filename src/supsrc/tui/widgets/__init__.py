# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""TUI widgets package."""

from supsrc.tui.widgets.draggable_splitter import DraggableSplitter
from supsrc.tui.widgets.log_panel import (
    LogPanel,
    TuiLogHandler,
    TuiOutputStream,
    get_tui_log_handler,
    get_tui_output_stream,
    install_tui_log_handler,
    redirect_foundation_to_tui,
    restore_stderr,
    restore_streams,
)

__all__ = [
    "DraggableSplitter",
    "LogPanel",
    "TuiLogHandler",
    "TuiOutputStream",
    "get_tui_log_handler",
    "get_tui_output_stream",
    "install_tui_log_handler",
    "redirect_foundation_to_tui",
    "restore_stderr",
    "restore_streams",
]

# 🔼⚙️🔚
