#
# supsrc/timemachine/__init__.py
#
"""
Git Time Machine - Continuous micro-commits with P2P backup.

Provides granular version history for every keystroke, enabling time-travel
recovery to any point in development history without central servers.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import attrs

__version__ = "0.1.0"

# --- Data Models ---


@attrs.define(frozen=True, slots=True)
class MicroCommit:
    """Represents a single micro-commit in the time machine."""

    # Identity
    commit_hash: str  # Git SHA-1
    timestamp: datetime  # When created (timezone-aware UTC)

    # Content
    files_changed: list[str] = attrs.field(factory=list)  # Paths of changed files
    diff_summary: str = ""  # Brief description of changes

    # Metadata
    trigger_type: str = "auto"  # "auto", "snapshot", "manual"
    parent_commit: str | None = None  # Previous micro-commit
    snapshot_ref: str | None = None  # Associated snapshot (if any)

    # Stats
    lines_added: int = 0
    lines_removed: int = 0
    file_size_delta: int = 0  # Bytes

    # User context (optional)
    active_file: str | None = None  # File being edited
    cursor_position: tuple[int, int] | None = None  # (line, column)

    def ref_name(self) -> str:
        """Generate Git ref name for this micro-commit."""
        date_str = self.timestamp.strftime("%Y-%m-%d")
        time_str = self.timestamp.strftime("%H-%M-%S-%f")[:15]  # Include microseconds
        return f"refs/timemachine/{date_str}/{time_str}"


@attrs.define(frozen=True, slots=True)
class Snapshot:
    """Periodic full snapshot for faster recovery."""

    commit_hash: str
    timestamp: datetime
    snapshot_type: str  # "hourly", "daily", "weekly", "manual"

    # Aggregated stats since last snapshot
    total_micro_commits: int = 0
    total_files_changed: set[str] = attrs.field(factory=set)
    total_lines_changed: int = 0

    # Retention
    expires_at: datetime | None = None
    protected: bool = False  # User-marked as important

    def ref_name(self) -> str:
        """Generate Git ref name for this snapshot."""
        return f"refs/snapshots/{self.snapshot_type}/{self.timestamp.isoformat()}"


@attrs.define(frozen=True, slots=True)
class CommitRef:
    """Lightweight reference to a commit (for indexing)."""

    hash: str  # Commit SHA-1
    timestamp: datetime  # When committed
    ref: str  # Git ref name


@attrs.define(frozen=True, slots=True)
class TrustedDevice:
    """A device that can sync with this repo (Phase 2)."""

    device_id: str  # Unique identifier
    device_name: str  # Human-readable name (e.g., "Alice's MacBook Pro")
    fingerprint: str  # SSH key fingerprint or certificate hash

    # Network
    last_seen_addr: str | None = None  # "192.168.1.5:9418"
    discovery_method: str = "manual"  # "mdns", "manual", "relay"

    # Sync state
    last_sync: datetime | None = None
    last_known_commit: str | None = None
    sync_enabled: bool = True

    # Trust level
    can_receive: bool = True  # Allow this device to pull
    can_send: bool = True  # Allow this device to push
    auto_sync: bool = True  # Sync automatically when discovered


# --- Public API ---

__all__ = [
    "MicroCommit",
    "Snapshot",
    "CommitRef",
    "TrustedDevice",
    "__version__",
]

# 🕰️ Time Machine
