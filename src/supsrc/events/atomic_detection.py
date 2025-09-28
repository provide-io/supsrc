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
        log.debug("Starting atomic save detection", event_count=len(events))

        atomic_saves = []
        processed_files = set()

        # Look for delete + create patterns with related filenames
        deletes = [e for e in events if e.change_type == "deleted"]
        creates = [e for e in events if e.change_type == "created"]
        moves = [e for e in events if e.change_type == "moved"]

        log.trace("Event breakdown", deletes=len(deletes), creates=len(creates), moves=len(moves))

        # Pattern 1: Delete + Create (classic atomic save)
        for delete_event in deletes:
            for create_event in creates:
                if create_event.file_path in processed_files or delete_event.file_path in processed_files:
                    continue

                # Check if files are related (same base name)
                if AtomicSaveDetector._files_are_related_simple(
                    delete_event.file_path, create_event.file_path
                ):
                    log.debug("Found delete+create atomic save",
                             deleted=str(delete_event.file_path),
                             created=str(create_event.file_path))

                    atomic_save = AtomicSaveDetector._create_atomic_save_event(
                        delete_event, create_event, "delete+create"
                    )
                    atomic_saves.append(atomic_save)

                    # Mark both files as processed
                    processed_files.add(delete_event.file_path)
                    processed_files.add(create_event.file_path)

        # Pattern 2: Move operations (temp file moves)
        for move_event in moves:
            if move_event.file_path in processed_files:
                continue

            # Check if this is a temp file being moved to final location
            if AtomicSaveDetector._is_temp_file(move_event.file_path):
                log.debug("Found temp file move",
                         temp_file=str(move_event.file_path),
                         repo_id=move_event.repo_id)

                # Create a single-event atomic save for temp file cleanup
                operation_history = [
                    {
                        "path": move_event.file_path,
                        "change_type": "moved",
                        "timestamp": move_event.timestamp,
                        "is_primary": True,
                    }
                ]

                atomic_save = BufferedFileChangeEvent(
                    repo_id=move_event.repo_id,
                    file_paths=[move_event.file_path],
                    operation_type="atomic_rewrite",
                    event_count=1,
                    primary_change_type="modified",
                    operation_history=operation_history,
                )
                atomic_saves.append(atomic_save)
                processed_files.add(move_event.file_path)

        log.debug("Atomic save detection complete",
                 atomic_saves_found=len(atomic_saves),
                 files_processed=len(processed_files))

        return atomic_saves

    @staticmethod
    def _create_atomic_save_event(
        delete_event: FileChangeEvent, create_event: FileChangeEvent, pattern_type: str
    ) -> BufferedFileChangeEvent:
        """Create a BufferedFileChangeEvent for an atomic save operation."""
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

        return BufferedFileChangeEvent(
            repo_id=create_event.repo_id,
            file_paths=[create_event.file_path],  # End-state file
            operation_type="atomic_rewrite",
            event_count=2,
            primary_change_type="modified",  # Atomic save is essentially a modification
            operation_history=operation_history,
        )

    @staticmethod
    def _is_temp_file(path: Path) -> bool:
        """Check if a file path represents a temporary file."""
        name = path.name
        log.trace("Checking if temp file", filename=name)

        # Common temp file patterns
        temp_patterns = [
            # Standard patterns
            name.startswith(".") and name.endswith(".tmp"),
            name.endswith(".tmp"),
            # Numbered temp files like .tmp.84 or .tmp53TM2M
            ".tmp" in name and any(c.isdigit() or c.isupper() for c in name.split(".tmp")[-1]),
            # Vim patterns
            name.startswith(".") and name.endswith(".swp"),
            name.startswith(".") and name.endswith(".swo"),
            # Emacs patterns
            name.startswith("#") and name.endswith("#"),
            name.startswith(".#"),
            # Other common patterns
            name.endswith("~"),
            name.endswith(".bak"),
            name.endswith(".backup"),
        ]

        is_temp = any(temp_patterns)
        log.trace("Temp file check result", filename=name, is_temp=is_temp)
        return is_temp

    @staticmethod
    def _files_are_related_simple(path1: Path, path2: Path) -> bool:
        """Check if two paths are related for atomic save detection."""
        name1, name2 = path1.name, path2.name
        log.trace("Checking file relationship", file1=name1, file2=name2)

        # Same file name -> likely atomic save
        if name1 == name2:
            log.trace("Files have same name", file1=name1, file2=name2)
            return True

        # Pattern 1: One is a temp version of the other (.file.txt.tmp)
        if name1.startswith(".") and name1.endswith(".tmp") and name1[1:-4] == name2:
            log.trace("Pattern 1 match", temp_file=name1, original=name2)
            return True
        if name2.startswith(".") and name2.endswith(".tmp") and name2[1:-4] == name1:
            log.trace("Pattern 1 match", temp_file=name2, original=name1)
            return True

        # Pattern 2: One has .tmp suffix (file.txt.tmp)
        if name1.endswith(".tmp") and name1[:-4] == name2:
            log.trace("Pattern 2 match", temp_file=name1, original=name2)
            return True
        if name2.endswith(".tmp") and name2[:-4] == name1:
            log.trace("Pattern 2 match", temp_file=name2, original=name1)
            return True

        # Pattern 3: Numbered temp files (file.txt.tmp.84)
        if ".tmp." in name1:
            base_name = name1.split(".tmp.")[0]
            if base_name == name2:
                log.trace("Pattern 3 match (numbered temp)", temp_file=name1, original=name2)
                return True
        if ".tmp." in name2:
            base_name = name2.split(".tmp.")[0]
            if base_name == name1:
                log.trace("Pattern 3 match (numbered temp)", temp_file=name2, original=name1)
                return True

        # Pattern 4: Random suffix after base name (file.tmp123)
        if name1.rsplit(".", 1)[0] == name2 and len(name1.rsplit(".", 1)) == 2:
            suffix = name1.rsplit(".", 1)[1]
            if suffix.startswith("tmp") or suffix.startswith("bak"):
                log.trace("Pattern 4 match (random suffix)", temp_file=name1, original=name2)
                return True
        if name2.rsplit(".", 1)[0] == name1 and len(name2.rsplit(".", 1)) == 2:
            suffix = name2.rsplit(".", 1)[1]
            if suffix.startswith("tmp") or suffix.startswith("bak"):
                log.trace("Pattern 4 match (random suffix)", temp_file=name2, original=name1)
                return True

        # Pattern 5: Editor temp patterns (vim: .file.swp, emacs: #file#)
        stem1, stem2 = path1.stem, path2.stem
        if name1.startswith(".") and name1.endswith(".swp") and len(stem1) > 4 and stem1[1:-4] == stem2:
            log.trace("Pattern 5 match (vim swp)", temp_file=name1, original=name2)
            return True
        if name2.startswith(".") and name2.endswith(".swp") and len(stem2) > 4 and stem2[1:-4] == stem1:
            log.trace("Pattern 5 match (vim swp)", temp_file=name2, original=name1)
            return True

        log.trace("No file relationship found", file1=name1, file2=name2)
        return False
