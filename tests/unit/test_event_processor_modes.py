#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for EventProcessor mode detection and mode-specific buffering."""

from __future__ import annotations

import asyncio

from provide.testkit.mocking import AsyncMock, Mock
import pytest

from supsrc.config import GlobalConfig, SupsrcConfig
from supsrc.config.defaults import (
    DEFAULT_EVENT_BUFFER_GROUPING_MODE_HEADLESS,
    DEFAULT_EVENT_BUFFER_GROUPING_MODE_TUI,
)
from supsrc.events.processor import EventProcessor


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = SupsrcConfig(
        repositories={},
        global_config=GlobalConfig(
            log_level="DEBUG",
            event_buffering_enabled=True,
            event_buffer_window_ms=500,
            event_grouping_mode_tui="smart",
            event_grouping_mode_headless="simple",
            event_grouping_mode="simple",  # Legacy fallback
        ),
    )
    return config


@pytest.fixture
def mock_action_handler():
    """Create a mock action handler."""
    handler = Mock()
    handler.execute_action_sequence = AsyncMock()
    return handler


@pytest.fixture
def mock_tui_interface_with_app():
    """Create a mock TUI interface with app (TUI mode)."""
    tui = Mock()
    tui.app = Mock()  # App exists -> TUI mode
    tui.app.event_collector = Mock()
    tui.app.event_collector.emit = Mock()
    tui.post_state_update = Mock()
    tui.post_log_update = Mock()
    return tui


@pytest.fixture
def mock_tui_interface_without_app():
    """Create a mock TUI interface without app (headless mode)."""
    tui = Mock()
    tui.app = None  # No app -> headless mode
    tui.post_state_update = Mock()
    tui.post_log_update = Mock()
    return tui


class TestModeDetection:
    """Test suite for mode detection logic."""

    def test_tui_mode_detected_when_app_present(
        self, mock_config, mock_action_handler, mock_tui_interface_with_app
    ):
        """Test that TUI mode is detected when app is present."""
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=mock_config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_with_app,
            config_reload_callback=AsyncMock(),
        )

        # Verify TUI grouping mode was selected
        assert processor._event_buffer is not None
        assert processor._event_buffer.grouping_mode == "smart"

    def test_headless_mode_detected_when_app_none(
        self, mock_config, mock_action_handler, mock_tui_interface_without_app
    ):
        """Test that headless mode is detected when app is None."""
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=mock_config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_without_app,
            config_reload_callback=AsyncMock(),
        )

        # Verify headless grouping mode was selected
        assert processor._event_buffer is not None
        assert processor._event_buffer.grouping_mode == "simple"

    def test_headless_mode_detected_when_tui_has_no_app_attribute(self, mock_config, mock_action_handler):
        """Test that headless mode is detected when TUI has no app attribute."""
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        # TUI without app attribute
        tui = Mock(spec=[])  # No attributes
        tui.post_state_update = Mock()

        processor = EventProcessor(
            config=mock_config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=tui,
            config_reload_callback=AsyncMock(),
        )

        # Verify headless grouping mode was selected
        assert processor._event_buffer is not None
        assert processor._event_buffer.grouping_mode == "simple"

    def test_uses_default_tui_mode_from_config(self, mock_action_handler, mock_tui_interface_with_app):
        """Test that default TUI mode from config is used."""
        config = SupsrcConfig(
            repositories={},
            global_config=GlobalConfig(
                log_level="DEBUG",
                event_buffering_enabled=True,
                event_buffer_window_ms=500,
                event_grouping_mode_tui=DEFAULT_EVENT_BUFFER_GROUPING_MODE_TUI,
                event_grouping_mode_headless=DEFAULT_EVENT_BUFFER_GROUPING_MODE_HEADLESS,
            ),
        )

        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_with_app,
            config_reload_callback=AsyncMock(),
        )

        assert processor._event_buffer.grouping_mode == DEFAULT_EVENT_BUFFER_GROUPING_MODE_TUI

    def test_uses_default_headless_mode_from_config(self, mock_action_handler, mock_tui_interface_without_app):
        """Test that default headless mode from config is used."""
        config = SupsrcConfig(
            repositories={},
            global_config=GlobalConfig(
                log_level="DEBUG",
                event_buffering_enabled=True,
                event_buffer_window_ms=500,
                event_grouping_mode_tui=DEFAULT_EVENT_BUFFER_GROUPING_MODE_TUI,
                event_grouping_mode_headless=DEFAULT_EVENT_BUFFER_GROUPING_MODE_HEADLESS,
            ),
        )

        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_without_app,
            config_reload_callback=AsyncMock(),
        )

        assert processor._event_buffer.grouping_mode == DEFAULT_EVENT_BUFFER_GROUPING_MODE_HEADLESS

    def test_buffering_disabled_creates_no_buffer(self, mock_action_handler, mock_tui_interface_with_app):
        """Test that no buffer is created when buffering is disabled."""
        config = SupsrcConfig(
            repositories={},
            global_config=GlobalConfig(
                log_level="DEBUG",
                event_buffering_enabled=False,  # Disabled
                event_buffer_window_ms=500,
                event_grouping_mode_tui="smart",
                event_grouping_mode_headless="simple",
            ),
        )

        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_with_app,
            config_reload_callback=AsyncMock(),
        )

        assert processor._event_buffer is None


class TestModeSpecificBehavior:
    """Test suite for mode-specific buffering behavior."""

    def test_tui_mode_uses_smart_grouping(self, mock_config, mock_action_handler, mock_tui_interface_with_app):
        """Test that TUI mode uses smart grouping by default."""
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=mock_config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_with_app,
            config_reload_callback=AsyncMock(),
        )

        assert processor._event_buffer.grouping_mode == "smart"

    def test_headless_mode_uses_simple_grouping(
        self, mock_config, mock_action_handler, mock_tui_interface_without_app
    ):
        """Test that headless mode uses simple grouping by default."""
        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=mock_config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_without_app,
            config_reload_callback=AsyncMock(),
        )

        assert processor._event_buffer.grouping_mode == "simple"

    def test_config_override_works_for_tui(self, mock_action_handler, mock_tui_interface_with_app):
        """Test that config can override TUI mode grouping."""
        config = SupsrcConfig(
            repositories={},
            global_config=GlobalConfig(
                log_level="DEBUG",
                event_buffering_enabled=True,
                event_buffer_window_ms=500,
                event_grouping_mode_tui="off",  # Override to off
                event_grouping_mode_headless="simple",
            ),
        )

        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_with_app,
            config_reload_callback=AsyncMock(),
        )

        assert processor._event_buffer.grouping_mode == "off"

    def test_config_override_works_for_headless(self, mock_action_handler, mock_tui_interface_without_app):
        """Test that config can override headless mode grouping."""
        config = SupsrcConfig(
            repositories={},
            global_config=GlobalConfig(
                log_level="DEBUG",
                event_buffering_enabled=True,
                event_buffer_window_ms=500,
                event_grouping_mode_tui="smart",
                event_grouping_mode_headless="off",  # Override to off
            ),
        )

        event_queue = asyncio.Queue()
        shutdown_event = asyncio.Event()

        processor = EventProcessor(
            config=config,
            event_queue=event_queue,
            shutdown_event=shutdown_event,
            action_handler=mock_action_handler,
            repo_states={},
            repo_engines={},
            tui=mock_tui_interface_without_app,
            config_reload_callback=AsyncMock(),
        )

        assert processor._event_buffer.grouping_mode == "off"


# 🔼⚙️🔚
