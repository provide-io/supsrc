#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""This event set provides visual markers and metadata enrichment
for supsrc-specific log fields like repository status and rule types."""

from __future__ import annotations

from provide.foundation import EventMapping, EventSet, FieldMapping

SUPSRC_EVENT_SET = EventSet(
    name="supsrc",
    description="Supsrc repository monitoring event enrichment",
    mappings=[
        EventMapping(
            name="repo_status",
            visual_markers={
                # Repository states
                "idle": "💤",
                "changed": "📝",
                "triggered": "🎯",
                "pushing": "🚀",
                # Error states
                "error": "❌",
                "conflict": "⚠️",
                "failed": "🔥",
                # Paused/stopped states
                "paused": "⏸️",
                "stopped": "🛑",
                "resuming": "▶️",
                # Default
                "default": "📊",
            },
            default_key="default",
        ),
        EventMapping(
            name="rule_type",
            visual_markers={
                "inactivity": "⏳",
                "save_count": "💾",
                "manual": "✋",
                "timer": "⏱️",
            },
            default_key="default",
        ),
        EventMapping(
            name="git_operation",
            visual_markers={
                "status": "🔍",
                "stage": "➕",  # noqa: RUF001
                "push": "🚀",
                "pull": "⬇️",
                "fetch": "📥",
                "branch": "🌿",
                "checkout": "🔀",
                "merge": "🔗",
                "rebase": "🧬",
            },
            default_key="default",
        ),
        EventMapping(
            name="event_grouping",
            visual_markers={
                "simple": "📋",
                "smart": "🧠",
                "off": "⏹️",
                "atomic_rewrite": "✨",
                "batch_operation": "📚",
                "default": "📑",
            },
            default_key="default",
        ),
    ],
    field_mappings=[
        FieldMapping(
            log_key="repo_status",
            description="Current status of repository",
            event_set_name="supsrc",
        ),
        FieldMapping(
            log_key="rule_type",
            description="Type of trigger rule",
            event_set_name="supsrc",
        ),
        FieldMapping(
            log_key="git_operation",
            description="Git operation being performed",
            event_set_name="supsrc",
        ),
        FieldMapping(
            log_key="event_grouping",
            description="Event buffering/grouping mode",
            event_set_name="supsrc",
        ),
    ],
    priority=10,  # Higher than default DAS eventset (priority=0)
)

# 🔼⚙️🔚
