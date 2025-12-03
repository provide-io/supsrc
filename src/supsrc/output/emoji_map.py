#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from supsrc.events.protocol import Event


class EmojiMapper:
    """Provides emoji and ASCII representations for events."""

    # Event type to emoji mapping
    EVENT_TYPE_EMOJIS: ClassVar[dict[str, str]] = {
        "ExternalCommitEvent": "🤔",  # THINKING FACE
        "ConflictDetectedEvent": "⚠️",  # WARNING SIGN
        "RepositoryFrozenEvent": "🧊",  # ICE CUBE
        "LLMVetoEvent": "🧠",  # BRAIN
        "GitCommitEvent": "📝",  # MEMO
        "GitPushEvent": "🚀",  # ROCKET
        "GitStageEvent": "📋",  # CLIPBOARD
        "GitBranchEvent": "🌿",  # HERB
        "RuleTriggeredEvent": "⏳",  # HOURGLASS
        "ErrorEvent": "❌",  # CROSS MARK
        "ConfigReloadEvent": "🔄",  # RELOAD
        "UserActionEvent": "👤",  # USER
        "TimerUpdateEvent": "⏱️",  # STOPWATCH
    }

    # Change type emojis (for file events)
    CHANGE_TYPE_EMOJIS: ClassVar[dict[str, str]] = {
        "created": "➕",  # HEAVY PLUS SIGN  # noqa: RUF001
        "modified": "✏️",  # PENCIL
        "deleted": "➖",  # HEAVY MINUS SIGN  # noqa: RUF001
        "moved": "🔄",  # COUNTERCLOCKWISE ARROWS BUTTON
    }

    # Source emojis (fallback)
    SOURCE_EMOJIS: ClassVar[dict[str, str]] = {
        "monitor": "👁️",  # EYE
        "rules": "⚡",  # HIGH VOLTAGE SIGN
        "tui": "💻",  # PERSONAL COMPUTER
    }

    # ASCII fallback mappings
    ASCII_FALLBACKS: ClassVar[dict[str, str]] = {
        "🤔": "[?]",
        "⚠️": "[!]",
        "🧊": "[F]",  # Frozen
        "🧠": "[A]",  # AI
        "📝": "[C]",  # Commit
        "🚀": "[P]",  # Push
        "📋": "[S]",  # Stage
        "🌿": "[B]",  # Branch
        "⏳": "[R]",  # Rule
        "❌": "[X]",  # Error
        "🔄": "[R]",  # Reload
        "👤": "[U]",  # User
        "⏱️": "[T]",  # Timer
        "➕": "[+]",  # noqa: RUF001
        "✏️": "[M]",  # Modified
        "➖": "[-]",  # noqa: RUF001
        "👁️": "[W]",  # Watch
        "⚡": "[!]",
        "💻": "[T]",  # TUI
    }

    @staticmethod
    def get_event_emoji(event: Event, use_ascii: bool = False) -> str:
        """Get appropriate emoji or ASCII representation for an event.

        Args:
            event: Event to get emoji for
            use_ascii: If True, return ASCII fallback instead of emoji

        Returns:
            Emoji or ASCII representation
        """
        # Check for specific event types first
        event_type = type(event).__name__
        if event_type in EmojiMapper.EVENT_TYPE_EMOJIS:
            emoji = EmojiMapper.EVENT_TYPE_EMOJIS[event_type]
            return EmojiMapper.ASCII_FALLBACKS.get(emoji, "[?]") if use_ascii else emoji

        # Check for operation type (BufferedFileChangeEvent)
        if hasattr(event, "operation_type"):
            if event.operation_type == "atomic_rewrite":
                emoji = "🔄"
                return EmojiMapper.ASCII_FALLBACKS.get(emoji, "[R]") if use_ascii else emoji
            elif event.operation_type == "batch_operation":
                emoji = "📦"
                return EmojiMapper.ASCII_FALLBACKS.get(emoji, "[M]") if use_ascii else emoji

        # Check for primary change type
        if hasattr(event, "primary_change_type"):
            change_type = event.primary_change_type
            if change_type in EmojiMapper.CHANGE_TYPE_EMOJIS:
                emoji = EmojiMapper.CHANGE_TYPE_EMOJIS[change_type]
                return EmojiMapper.ASCII_FALLBACKS.get(emoji, "[?]") if use_ascii else emoji

        # Fallback to source
        source = getattr(event, "source", "unknown")
        emoji = EmojiMapper.SOURCE_EMOJIS.get(source, "📝")
        return EmojiMapper.ASCII_FALLBACKS.get(emoji, "[?]") if use_ascii else emoji


# 🔼⚙️🔚
