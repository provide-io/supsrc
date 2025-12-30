#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Base TUI application class combining all handler mixins."""

from __future__ import annotations

from textual.app import App

from supsrc.tui.handlers.actions import ActionHandlerMixin
from supsrc.tui.handlers.events import EventHandlerMixin
from supsrc.tui.handlers.repo_actions import RepoActionHandlerMixin
from supsrc.tui.helpers.ui_helpers import UIHelperMixin
from supsrc.tui.helpers.worker_helpers import WorkerHelperMixin


class TuiAppBase(
    ActionHandlerMixin,
    EventHandlerMixin,
    RepoActionHandlerMixin,
    UIHelperMixin,
    WorkerHelperMixin,
    App,
):
    """Base TUI application class combining all handler mixins."""



# 🔼⚙️🔚
