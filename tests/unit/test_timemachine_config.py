#
# tests/unit/test_timemachine_config.py
#
"""
Unit tests for Time Machine configuration models.
"""

import tempfile
from pathlib import Path

import pytest

from supsrc.timemachine.config import (
    CommitConfig,
    NotificationConfig,
    P2PConfig,
    SnapshotConfig,
    StorageConfig,
    TimeMachineConfig,
    create_default_config,
    load_config,
)
from supsrc.timemachine.exceptions import ConfigurationError


class TestCommitConfig:
    """Tests for CommitConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CommitConfig()

        assert config.debounce_seconds == 30.0
        assert config.min_interval_seconds == 10.0
        assert config.max_pending_changes == 50
        assert config.include_patterns == ["**/*"]
        assert "*.pyc" in config.exclude_patterns
        assert "__pycache__/**" in config.exclude_patterns

    def test_custom_values(self):
        """Test custom configuration values."""
        config = CommitConfig(
            debounce_seconds=60.0,
            min_interval_seconds=20.0,
            max_pending_changes=100,
            include_patterns=["src/**", "tests/**"],
            exclude_patterns=["*.log"],
        )

        assert config.debounce_seconds == 60.0
        assert config.min_interval_seconds == 20.0
        assert config.max_pending_changes == 100
        assert config.include_patterns == ["src/**", "tests/**"]
        assert config.exclude_patterns == ["*.log"]

    def test_invalid_debounce_seconds(self):
        """Test validation of debounce_seconds."""
        with pytest.raises(ConfigurationError, match="positive number"):
            CommitConfig(debounce_seconds=-1.0)

        with pytest.raises(ConfigurationError, match="positive number"):
            CommitConfig(debounce_seconds=0.0)

    def test_invalid_min_interval_seconds(self):
        """Test validation of min_interval_seconds."""
        with pytest.raises(ConfigurationError, match="positive number"):
            CommitConfig(min_interval_seconds=-5.0)

    def test_invalid_max_pending_changes(self):
        """Test validation of max_pending_changes."""
        with pytest.raises(ConfigurationError, match="positive integer"):
            CommitConfig(max_pending_changes=0)

        with pytest.raises(ConfigurationError, match="positive integer"):
            CommitConfig(max_pending_changes=-10)

    def test_invalid_patterns(self):
        """Test validation of patterns."""
        with pytest.raises(ConfigurationError, match="must be a list"):
            CommitConfig(include_patterns="not a list")  # type: ignore

        with pytest.raises(ConfigurationError, match="must be string"):
            CommitConfig(include_patterns=[123, 456])  # type: ignore


class TestSnapshotConfig:
    """Tests for SnapshotConfig."""

    def test_default_values(self):
        """Test default snapshot configuration."""
        config = SnapshotConfig()

        assert config.hourly_enabled is True
        assert config.daily_enabled is True
        assert config.weekly_enabled is True
        assert config.keep_hourly == 24
        assert config.keep_daily == 7
        assert config.keep_weekly == 4
        assert config.keep_all_protected is True

    def test_custom_values(self):
        """Test custom snapshot configuration."""
        config = SnapshotConfig(
            hourly_enabled=False,
            keep_hourly=48,
            keep_daily=14,
        )

        assert config.hourly_enabled is False
        assert config.keep_hourly == 48
        assert config.keep_daily == 14

    def test_invalid_keep_values(self):
        """Test validation of retention counts."""
        with pytest.raises(ConfigurationError, match="positive integer"):
            SnapshotConfig(keep_hourly=0)

        with pytest.raises(ConfigurationError, match="positive integer"):
            SnapshotConfig(keep_daily=-1)


class TestP2PConfig:
    """Tests for P2PConfig."""

    def test_default_values(self):
        """Test default P2P configuration."""
        config = P2PConfig()

        assert config.enabled is False  # Disabled by default in Phase 1
        assert config.discovery_method == "mdns"
        assert config.announce_interval_seconds == 60
        assert config.sync_interval_seconds == 120
        assert config.git_daemon_port == 9418

    def test_custom_values(self):
        """Test custom P2P configuration."""
        config = P2PConfig(
            enabled=True,
            discovery_method="manual",
            device_name="Test Device",
            device_id="test-123",
        )

        assert config.enabled is True
        assert config.discovery_method == "manual"
        assert config.device_name == "Test Device"
        assert config.device_id == "test-123"

    def test_invalid_discovery_method(self):
        """Test validation of discovery method."""
        with pytest.raises(ValueError, match="must be in"):
            P2PConfig(discovery_method="invalid")  # type: ignore


class TestStorageConfig:
    """Tests for StorageConfig."""

    def test_default_values(self):
        """Test default storage configuration."""
        config = StorageConfig()

        assert config.compression is True
        assert config.deduplication is True
        assert config.max_size_mb == 1000
        assert config.auto_gc is True
        assert config.gc_interval_commits == 1000

    def test_custom_values(self):
        """Test custom storage configuration."""
        config = StorageConfig(
            max_size_mb=5000,
            auto_gc=False,
        )

        assert config.max_size_mb == 5000
        assert config.auto_gc is False


class TestNotificationConfig:
    """Tests for NotificationConfig."""

    def test_default_values(self):
        """Test default notification configuration."""
        config = NotificationConfig()

        assert config.on_first_sync is True
        assert config.on_sync_failure is True
        assert config.on_restore is True
        assert config.on_storage_warning is True


class TestTimeMachineConfig:
    """Tests for TimeMachineConfig (root config)."""

    def test_default_values(self):
        """Test default time machine configuration."""
        config = TimeMachineConfig()

        assert config.enabled is True
        assert isinstance(config.commits, CommitConfig)
        assert isinstance(config.snapshots, SnapshotConfig)
        assert isinstance(config.p2p, P2PConfig)
        assert isinstance(config.storage, StorageConfig)
        assert isinstance(config.notifications, NotificationConfig)
        assert config.repo_path is None

    def test_custom_nested_configs(self):
        """Test custom nested configurations."""
        commits = CommitConfig(debounce_seconds=60.0)
        snapshots = SnapshotConfig(keep_hourly=48)

        config = TimeMachineConfig(
            commits=commits,
            snapshots=snapshots,
        )

        assert config.commits.debounce_seconds == 60.0
        assert config.snapshots.keep_hourly == 48

    def test_validate_debounce_min_interval(self):
        """Test validation of debounce vs min_interval."""
        commits = CommitConfig(
            debounce_seconds=5.0,
            min_interval_seconds=10.0,
        )

        config = TimeMachineConfig(commits=commits)

        with pytest.raises(
            ConfigurationError, match="debounce_seconds.*should be >= min_interval_seconds"
        ):
            config.validate()

    def test_validate_repo_path_not_exists(self):
        """Test validation when repo_path doesn't exist."""
        config = TimeMachineConfig(repo_path=Path("/nonexistent/path"))

        with pytest.raises(ConfigurationError, match="does not exist"):
            config.validate()

    def test_validate_repo_path_not_directory(self, tmp_path):
        """Test validation when repo_path is not a directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        config = TimeMachineConfig(repo_path=test_file)

        with pytest.raises(ConfigurationError, match="not a directory"):
            config.validate()

    def test_validate_repo_path_not_git_repo(self, tmp_path):
        """Test validation when repo_path is not a Git repository."""
        config = TimeMachineConfig(repo_path=tmp_path)

        with pytest.raises(ConfigurationError, match="Not a Git repository"):
            config.validate()

    def test_validate_valid_git_repo(self, tmp_path):
        """Test validation with valid Git repository."""
        # Create a Git repository
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        config = TimeMachineConfig(repo_path=tmp_path)
        config.validate()  # Should not raise

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "enabled": True,
            "commits": {
                "debounce_seconds": 45.0,
                "max_pending_changes": 75,
            },
            "snapshots": {
                "keep_hourly": 36,
            },
            "p2p": {
                "enabled": False,
            },
        }

        config = TimeMachineConfig.from_dict(data)

        assert config.enabled is True
        assert config.commits.debounce_seconds == 45.0
        assert config.commits.max_pending_changes == 75
        assert config.snapshots.keep_hourly == 36
        assert config.p2p.enabled is False

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = TimeMachineConfig()
        config_dict = config.to_dict()

        assert config_dict["enabled"] is True
        assert "commits" in config_dict
        assert "snapshots" in config_dict
        assert "p2p" in config_dict
        assert config_dict["commits"]["debounce_seconds"] == 30.0

    def test_round_trip_dict(self):
        """Test from_dict → to_dict round trip."""
        original = TimeMachineConfig(
            commits=CommitConfig(debounce_seconds=60.0),
            snapshots=SnapshotConfig(keep_hourly=48),
        )

        dict_form = original.to_dict()
        restored = TimeMachineConfig.from_dict(dict_form)

        assert restored.commits.debounce_seconds == 60.0
        assert restored.snapshots.keep_hourly == 48


class TestConfigLoading:
    """Tests for config loading from files."""

    def test_load_config_file_not_found(self):
        """Test loading config when file doesn't exist."""
        with pytest.raises(ConfigurationError, match="Config file not found"):
            load_config(Path("/nonexistent/config.toml"))

    def test_load_config_valid_toml(self, tmp_path):
        """Test loading valid TOML configuration."""
        config_file = tmp_path / "timemachine.toml"
        config_content = """
[timemachine]
enabled = true

[timemachine.commits]
debounce_seconds = 45.0
max_pending_changes = 100

[timemachine.snapshots]
keep_hourly = 48
keep_daily = 14

[timemachine.p2p]
enabled = false
device_name = "Test Device"
"""
        config_file.write_text(config_content)

        config = load_config(config_file)

        assert config.enabled is True
        assert config.commits.debounce_seconds == 45.0
        assert config.commits.max_pending_changes == 100
        assert config.snapshots.keep_hourly == 48
        assert config.snapshots.keep_daily == 14
        assert config.p2p.enabled is False
        assert config.p2p.device_name == "Test Device"

    def test_load_config_minimal_toml(self, tmp_path):
        """Test loading minimal TOML with defaults."""
        config_file = tmp_path / "timemachine.toml"
        config_content = """
[timemachine]
enabled = true
"""
        config_file.write_text(config_content)

        config = load_config(config_file)

        # Should use defaults
        assert config.enabled is True
        assert config.commits.debounce_seconds == 30.0
        assert config.snapshots.keep_hourly == 24

    def test_create_default_config(self, tmp_path):
        """Test creating default configuration for a repo."""
        # Create a Git repository
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        config = create_default_config(tmp_path)

        assert config.repo_path == tmp_path
        assert config.enabled is True
        assert config.commits.debounce_seconds == 30.0

    def test_create_default_config_invalid_repo(self, tmp_path):
        """Test creating default config for invalid repo."""
        with pytest.raises(ConfigurationError, match="Not a Git repository"):
            create_default_config(tmp_path)


# 🕰️ Time Machine
