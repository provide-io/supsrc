#
# supsrc/timemachine/config.py
#
"""
Configuration models for Git Time Machine.
"""

from pathlib import Path
from typing import Any

import attrs
from attrs import field, validators

from supsrc.timemachine.exceptions import ConfigurationError


# --- Validators ---


def _validate_positive_int(instance: Any, attribute: Any, value: int) -> None:
    """Validator for positive integers."""
    if not isinstance(value, int) or value <= 0:
        raise ConfigurationError(
            f"Field '{attribute.name}' must be a positive integer, got {value}"
        )


def _validate_positive_float(instance: Any, attribute: Any, value: float) -> None:
    """Validator for positive floats."""
    if not isinstance(value, (int, float)) or value <= 0:
        raise ConfigurationError(
            f"Field '{attribute.name}' must be a positive number, got {value}"
        )


def _validate_patterns(instance: Any, attribute: Any, value: list[str]) -> None:
    """Validator for glob patterns."""
    if not isinstance(value, list):
        raise ConfigurationError(
            f"Field '{attribute.name}' must be a list of patterns"
        )
    for pattern in value:
        if not isinstance(pattern, str):
            raise ConfigurationError(
                f"Pattern in '{attribute.name}' must be string, got {type(pattern)}"
            )


# --- Configuration Models ---


@attrs.define(slots=True)
class CommitConfig:
    """Configuration for micro-commit behavior."""

    debounce_seconds: float = field(
        default=30.0,
        validator=_validate_positive_float,
        metadata={"description": "Wait time after last change before committing"},
    )

    min_interval_seconds: float = field(
        default=10.0,
        validator=_validate_positive_float,
        metadata={"description": "Minimum time between commits (rate limiting)"},
    )

    max_pending_changes: int = field(
        default=50,
        validator=_validate_positive_int,
        metadata={"description": "Force commit if this many files changed"},
    )

    include_patterns: list[str] = field(
        factory=lambda: ["**/*"],
        validator=_validate_patterns,
        metadata={"description": "Glob patterns for files to track"},
    )

    exclude_patterns: list[str] = field(
        factory=lambda: [
            "*.pyc",
            "__pycache__/**",
            ".venv/**",
            "venv/**",
            "node_modules/**",
            ".git/**",
            "*.log",
            "*.tmp",
            ".DS_Store",
        ],
        validator=_validate_patterns,
        metadata={"description": "Glob patterns for files to ignore"},
    )

    @property
    def should_track_file(self) -> bool:
        """Check if a file should be tracked (placeholder, use pathspec)."""
        return True  # Implement with pathspec in engine


@attrs.define(slots=True)
class SnapshotConfig:
    """Configuration for snapshot behavior."""

    hourly_enabled: bool = field(
        default=True, metadata={"description": "Create hourly snapshots"}
    )

    daily_enabled: bool = field(
        default=True, metadata={"description": "Create daily snapshots"}
    )

    weekly_enabled: bool = field(
        default=True, metadata={"description": "Create weekly snapshots"}
    )

    keep_hourly: int = field(
        default=24,
        validator=_validate_positive_int,
        metadata={"description": "Number of hourly snapshots to retain"},
    )

    keep_daily: int = field(
        default=7,
        validator=_validate_positive_int,
        metadata={"description": "Number of daily snapshots to retain"},
    )

    keep_weekly: int = field(
        default=4,
        validator=_validate_positive_int,
        metadata={"description": "Number of weekly snapshots to retain"},
    )

    keep_all_protected: bool = field(
        default=True,
        metadata={"description": "Never delete protected snapshots"},
    )


@attrs.define(slots=True)
class P2PConfig:
    """Configuration for P2P sync (Phase 2)."""

    enabled: bool = field(
        default=False, metadata={"description": "Enable P2P synchronization"}
    )

    discovery_method: str = field(
        default="mdns",
        validator=validators.in_(["mdns", "manual", "dht"]),
        metadata={"description": "Method for discovering peers"},
    )

    announce_interval_seconds: int = field(
        default=60,
        validator=_validate_positive_int,
        metadata={"description": "How often to announce presence"},
    )

    sync_interval_seconds: int = field(
        default=120,
        validator=_validate_positive_int,
        metadata={"description": "How often to sync with peers"},
    )

    device_name: str = field(
        default="",
        metadata={"description": "Human-readable name for this device"},
    )

    device_id: str = field(
        default="", metadata={"description": "Unique identifier for this device"}
    )

    git_daemon_port: int = field(
        default=9418, metadata={"description": "Port for git daemon"}
    )

    # Trusted devices list (will be populated from config)
    trusted_devices: list[dict[str, Any]] = field(factory=list)


@attrs.define(slots=True)
class StorageConfig:
    """Configuration for storage optimization."""

    compression: bool = field(
        default=True, metadata={"description": "Enable Git compression"}
    )

    deduplication: bool = field(
        default=True, metadata={"description": "Enable object deduplication (always on in Git)"}
    )

    max_size_mb: int = field(
        default=1000,
        validator=_validate_positive_int,
        metadata={"description": "Alert if storage exceeds this size"},
    )

    auto_gc: bool = field(
        default=True, metadata={"description": "Automatically run git gc"}
    )

    gc_interval_commits: int = field(
        default=1000,
        validator=_validate_positive_int,
        metadata={"description": "Run gc after this many commits"},
    )


@attrs.define(slots=True)
class NotificationConfig:
    """Configuration for notifications."""

    on_first_sync: bool = field(
        default=True, metadata={"description": "Notify on first P2P sync"}
    )

    on_sync_failure: bool = field(
        default=True, metadata={"description": "Notify on sync failures"}
    )

    on_restore: bool = field(
        default=True, metadata={"description": "Notify on file restore"}
    )

    on_storage_warning: bool = field(
        default=True, metadata={"description": "Notify when storage limit approached"}
    )


@attrs.define(slots=True)
class TimeMachineConfig:
    """Root configuration for Git Time Machine."""

    enabled: bool = field(
        default=True, metadata={"description": "Enable time machine for this repo"}
    )

    # Sub-configs
    commits: CommitConfig = field(factory=CommitConfig)
    snapshots: SnapshotConfig = field(factory=SnapshotConfig)
    p2p: P2PConfig = field(factory=P2PConfig)
    storage: StorageConfig = field(factory=StorageConfig)
    notifications: NotificationConfig = field(factory=NotificationConfig)

    # Repository path (set at runtime)
    repo_path: Path | None = field(default=None)

    def validate(self) -> None:
        """Validate the configuration."""
        # Check debounce vs min_interval
        if self.commits.debounce_seconds < self.commits.min_interval_seconds:
            raise ConfigurationError(
                f"debounce_seconds ({self.commits.debounce_seconds}) should be >= "
                f"min_interval_seconds ({self.commits.min_interval_seconds})"
            )

        # Check repo_path if set
        if self.repo_path:
            if not self.repo_path.exists():
                raise ConfigurationError(
                    f"Repository path does not exist: {self.repo_path}"
                )
            if not self.repo_path.is_dir():
                raise ConfigurationError(
                    f"Repository path is not a directory: {self.repo_path}"
                )
            git_dir = self.repo_path / ".git"
            if not git_dir.exists():
                raise ConfigurationError(
                    f"Not a Git repository (no .git directory): {self.repo_path}"
                )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimeMachineConfig":
        """Create config from dictionary (e.g., loaded from TOML)."""
        # Handle nested configs
        commits_data = data.get("commits", {})
        snapshots_data = data.get("snapshots", {})
        p2p_data = data.get("p2p", {})
        storage_data = data.get("storage", {})
        notifications_data = data.get("notifications", {})

        config = cls(
            enabled=data.get("enabled", True),
            commits=CommitConfig(**commits_data),
            snapshots=SnapshotConfig(**snapshots_data),
            p2p=P2PConfig(**p2p_data),
            storage=StorageConfig(**storage_data),
            notifications=NotificationConfig(**notifications_data),
            repo_path=Path(data["repo_path"]) if "repo_path" in data else None,
        )

        config.validate()
        return config

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary (for saving to TOML)."""
        result = {
            "enabled": self.enabled,
            "commits": attrs.asdict(self.commits, filter=lambda a, v: a.name != "should_track_file"),
            "snapshots": attrs.asdict(self.snapshots),
            "p2p": attrs.asdict(self.p2p),
            "storage": attrs.asdict(self.storage),
            "notifications": attrs.asdict(self.notifications),
        }
        # Only include repo_path if it's set
        if self.repo_path:
            result["repo_path"] = str(self.repo_path)
        return result


# --- Config Loading ---


def load_config(config_path: Path) -> TimeMachineConfig:
    """Load configuration from TOML file."""
    import tomllib  # Python 3.11+

    if not config_path.exists():
        raise ConfigurationError(f"Config file not found: {config_path}")

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    # Extract timemachine section
    tm_data = data.get("timemachine", {})

    return TimeMachineConfig.from_dict(tm_data)


def create_default_config(repo_path: Path) -> TimeMachineConfig:
    """Create a default configuration for a repository."""
    config = TimeMachineConfig(repo_path=repo_path)
    config.validate()
    return config


# 🕰️ Time Machine
