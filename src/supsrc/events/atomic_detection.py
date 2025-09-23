# src/supsrc/events/atomic_detection.py

"""
Atomic save pattern detection for the event buffering system.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

from provide.foundation.logger import get_logger

from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent

log = get_logger("events.atomic_detection")


class AtomicSaveDetector:
    """Detects atomic save patterns in file change events."""

    @staticmethod
    def detect_simple_atomic_saves(
        events: list[FileChangeEvent],
    ) -> list[BufferedFileChangeEvent]:
        """Detect atomic save patterns using simple heuristics."""
        atomic_saves = []

        # Look for delete + create patterns with related filenames
        deletes = [e for e in events if e.change_type == "deleted"]
        creates = [e for e in events if e.change_type == "created"]

        for delete_event in deletes:
            for create_event in creates:
                # Check if files are related (same base name)
                if AtomicSaveDetector._files_are_related_simple(
                    delete_event.file_path, create_event.file_path
                ):
                    # This looks like an atomic save operation
                    operation_history = [
                        {
                            "path": delete_event.file_path,
                            "change_type": "deleted",
                            "timestamp": delete_event.timestamp,
                            "is_primary": False,
                        },
                        {
                            "path": create_event.file_path,
                            "change_type": "created",
                            "timestamp": create_event.timestamp,
                            "is_primary": True,
                        },
                    ]

                    # Sort by timestamp
                    operation_history.sort(key=lambda x: cast(datetime, x["timestamp"]))

                    atomic_save = BufferedFileChangeEvent(
                        repo_id=create_event.repo_id,
                        file_paths=[create_event.file_path],  # End-state file
                        operation_type="atomic_rewrite",
                        event_count=2,
                        primary_change_type="modified",  # Atomic save is essentially a modification
                        operation_history=operation_history,
                    )
                    atomic_saves.append(atomic_save)

        return atomic_saves

    @staticmethod
    def _files_are_related_simple(path1: Path, path2: Path) -> bool:
        """Check if two paths are related for atomic save detection."""
        # Same file name -> likely atomic save
        if path1.name == path2.name:
            return True

        # Check for temp file patterns
        name1, name2 = path1.name, path2.name

        # Common temp file patterns:
        # file.txt -> .file.txt.tmp
        # file.txt -> file.txt.tmp
        # file.txt -> file.tmp123

        # Pattern 1: One is a temp version of the other
        if name1.startswith(".") and name1.endswith(".tmp") and name1[1:-4] == name2:
            return True
        if name2.startswith(".") and name2.endswith(".tmp") and name2[1:-4] == name1:
            return True

        # Pattern 2: One has .tmp suffix
        if name1.endswith(".tmp") and name1[:-4] == name2:
            return True
        if name2.endswith(".tmp") and name2[:-4] == name1:
            return True

        # Pattern 3: One has random suffix (like .tmp123)
        if name1.rsplit(".", 1)[0] == name2 and len(name1.rsplit(".", 1)) == 2:
            suffix = name1.rsplit(".", 1)[1]
            if suffix.startswith("tmp") or suffix.startswith("bak"):
                return True
        if name2.rsplit(".", 1)[0] == name1 and len(name2.rsplit(".", 1)) == 2:
            suffix = name2.rsplit(".", 1)[1]
            if suffix.startswith("tmp") or suffix.startswith("bak"):
                return True

        # Pattern 4: Common editor temp patterns
        # vim: .file.swp
        # emacs: #file#, .#file
        stem1, stem2 = path1.stem, path2.stem
        if name1.startswith(".") and name1.endswith(".swp") and stem1[1:-4] == stem2:
            return True
        return bool(name2.startswith(".") and name2.endswith(".swp") and stem2[1:-4] == stem1)
