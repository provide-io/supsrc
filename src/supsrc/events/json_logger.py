# src/supsrc/events/json_logger.py

"""
JSON event logger for persisting events to structured log files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import attrs
from provide.foundation.logger import get_logger

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

log = get_logger("events.json_logger")


@attrs.define
class JSONEventLogger:
    """Logs events to a JSON file with structured format.

    Each event is written as a single JSON line (JSONL format) for easy parsing
    and streaming consumption.
    """

    file_path: Path
    _file_handle: Any = attrs.field(init=False, default=None)

    def __attrs_post_init__(self) -> None:
        """Initialize the file handle after creation."""
        try:
            # Ensure parent directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Open file in append mode for continuous logging
            self._file_handle = open(self.file_path, "a", encoding="utf-8")
            log.info("JSON event logger initialized", file_path=str(self.file_path))
        except Exception as e:
            log.error(
                "Failed to initialize JSON event logger",
                file_path=str(self.file_path),
                error=str(e),
            )
            raise

    def _serialize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Recursively serialize metadata, converting Path objects to strings."""
        if not isinstance(metadata, dict):
            return metadata

        serialized = {}
        for key, value in metadata.items():
            if isinstance(value, Path):
                serialized[key] = str(value)
            elif isinstance(value, dict):
                serialized[key] = self._serialize_metadata(value)
            elif isinstance(value, (list, tuple)):
                serialized[key] = [
                    str(item) if isinstance(item, Path) else item
                    for item in value
                ]
            else:
                serialized[key] = value
        return serialized

    def log_event(self, event: Event) -> None:
        """Log an event to the JSON file.

        Args:
            event: Event to log
        """
        if not self._file_handle:
            log.warning("JSON event logger not initialized, skipping event")
            return

        try:
            # Create structured event data
            event_data = {
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
                "description": event.description,
                "metadata": self._serialize_metadata(getattr(event, "metadata", {})),
            }

            # Add event-specific fields if available
            for field_name in [
                "repo_id",
                "file_path",
                "change_type",
                "commit_hash",
                "branch",
                "files_changed",
                "action",
                "rule_type",
            ]:
                if hasattr(event, field_name):
                    value = getattr(event, field_name)
                    # Convert Path objects to strings for JSON serialization
                    if isinstance(value, Path):
                        value = str(value)
                    event_data[field_name] = value

            # Write as single JSON line
            json_line = json.dumps(event_data, ensure_ascii=False)
            self._file_handle.write(json_line + "\n")
            self._file_handle.flush()

            log.debug(
                "Event logged to JSON file", source=event.source, description=event.description
            )

        except Exception as e:
            log.error("Failed to log event to JSON file", source=event.source, error=str(e))

    def close(self) -> None:
        """Close the file handle."""
        if self._file_handle:
            try:
                self._file_handle.close()
                log.info("JSON event logger closed")
            except Exception as e:
                log.error("Error closing JSON event logger", error=str(e))
            finally:
                self._file_handle = None

    def __del__(self) -> None:
        """Ensure file handle is closed on cleanup."""
        self.close()
