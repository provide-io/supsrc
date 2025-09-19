# Implementation Plan: .supsrc/ Directory Structure

## Overview
This document provides a detailed implementation plan for standardizing supsrc's file organization using a `.supsrc/` directory structure, similar to how `.git/` organizes repository metadata.

## Current State Analysis

### Existing File Organization
- **State files**: Currently uses `.supsrc.state` in repository root
- **Logs**: No standardized location (logs go to stdout/stderr or temp files)
- **Config**: Uses `~/.config/supsrc/` for global config, no repo-specific config location
- **Priority order for state files**:
  1. `{repo_path}/.supsrc.state` - Repository-specific
  2. `~/.config/supsrc/state.json` - User-global
  3. `/tmp/supsrc-global.state` - System-wide temporary

### Problems with Current Approach
- Repository root gets cluttered with `.supsrc.state` files
- No clear separation between shareable and local-only data
- No standard location for logs
- State files may accidentally get committed to git
- No repository-specific configuration option

## Proposed Directory Structure

```
<repository>/
├── .supsrc/                    # Tracked in git (configuration & shareable state)
│   ├── config.toml             # Repository-specific configuration (optional)
│   └── state.json              # Shareable state (paused status, rule overrides)
│
├── .supsrc/local/              # Gitignored (machine-specific data)
│   ├── state.local.json        # Local-only state (PID, machine-specific settings)
│   └── logs/                   # Application logs
│       ├── events.jsonl        # Event stream logs (JSON lines format)
│       ├── supsrc.log          # General application logs
│       └── debug.log           # Debug-level logs (when debug mode enabled)
│
└── .gitignore                  # Should include: .supsrc/local/
```

## Implementation Checklist

### Phase 1: Core Infrastructure

#### 1. Create Directory Management Module
**File**: `src/supsrc/utils/directories.py` (NEW)

```python
from __future__ import annotations
from pathlib import Path
from typing import Any
import structlog

log = structlog.get_logger("utils.directories")

class SupsrcDirectories:
    """Manages .supsrc/ directory structure for repositories."""

    SUPSRC_DIR = ".supsrc"
    LOCAL_DIR = "local"
    LOGS_DIR = "logs"

    @classmethod
    def ensure_structure(cls, repo_path: Path) -> dict[str, Path]:
        """Create and return all standard directory paths.

        Returns dict with keys:
        - config_dir: .supsrc/
        - local_dir: .supsrc/local/
        - logs_dir: .supsrc/local/logs/
        - state_file: .supsrc/state.json
        - local_state_file: .supsrc/local/state.local.json
        """
        # Implementation here

    @classmethod
    def get_log_dir(cls, repo_path: Path) -> Path:
        """Get or create log directory: .supsrc/local/logs/"""

    @classmethod
    def get_state_file(cls, repo_path: Path, local: bool = False) -> Path:
        """Get path for state file (creates parent dirs if needed)"""

    @classmethod
    def get_config_file(cls, repo_path: Path) -> Path:
        """Get path for repository config: .supsrc/config.toml"""
```

#### 2. Update .gitignore Patterns
**File**: `.gitignore` (APPEND)

```gitignore
# Supsrc local data (machine-specific, not shareable)
.supsrc/local/

# Legacy state files (for backwards compatibility during migration)
.supsrc.state
```

### Phase 2: State File Management

#### 3. Update State File Module
**File**: `src/supsrc/state/file.py` (MODIFY)

Changes needed:
- Update `STATE_FILENAME` from `".supsrc.state"` to `".supsrc/state.json"`
- Add `LOCAL_STATE_FILENAME = ".supsrc/local/state.local.json"`
- Split `StateData` into two classes:
  - `SharedStateData`: Data that can be shared (pause status, rules)
  - `LocalStateData`: Machine-specific data (PID, local paths)
- Update `find_state_file()` method to check new locations:
  ```python
  def find_state_file(cls, repo_path: Path | None = None, local: bool = False) -> Path | None:
      """Find state file with new priority order:

      Local=False (shareable state):
      1. {repo_path}/.supsrc/state.json
      2. {repo_path}/.supsrc.state (legacy, migrate if found)
      3. ~/.config/supsrc/state.json

      Local=True (machine-specific):
      1. {repo_path}/.supsrc/local/state.local.json
      2. /tmp/supsrc-{repo_id}.state
      """
  ```

#### 4. Create State Data Separation
**File**: `src/supsrc/state/control.py` (MODIFY)

Split state data:
```python
@define
class SharedStateData:
    """State data that can be shared across machines (committed to git)."""
    paused: bool = field(default=False)
    paused_until: datetime | None = field(default=None)
    pause_reason: str | None = field(default=None)
    repositories: dict[str, RepositoryStateOverride] = field(factory=dict)
    version: str = field(default="2.0.0")  # Bump version

@define
class LocalStateData:
    """Machine-specific state data (never committed)."""
    pid: int | None = field(default=None)
    paused_by: str | None = field(default=None)  # Username/hostname
    updated_at: datetime = field(factory=lambda: datetime.now(UTC))
    updated_by: str | None = field(default=None)
    local_overrides: dict[str, Any] = field(factory=dict)
```

### Phase 3: Logging Infrastructure

#### 5. Update JSON Event Logger
**File**: `src/supsrc/events/json_logger.py` (MODIFY)

Changes:
- Import `SupsrcDirectories` from `supsrc.utils.directories`
- Update default log path:
  ```python
  def __init__(self, repo_path: Path, file_name: str = "events.jsonl"):
      log_dir = SupsrcDirectories.get_log_dir(repo_path)
      self.file_path = log_dir / file_name
  ```
- Add log rotation support (optional):
  ```python
  def rotate_if_needed(self, max_size: int = 10_000_000):  # 10MB
      """Rotate log file if it exceeds max_size."""
  ```

#### 6. Add File Logging Support
**File**: `src/supsrc/utils/logging.py` (NEW)

```python
from __future__ import annotations
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_file_logging(repo_path: Path, log_level: str = "INFO") -> None:
    """Set up file logging in .supsrc/local/logs/"""
    from supsrc.utils.directories import SupsrcDirectories

    log_dir = SupsrcDirectories.get_log_dir(repo_path)

    # Main application log
    app_handler = RotatingFileHandler(
        log_dir / "supsrc.log",
        maxBytes=5_000_000,  # 5MB
        backupCount=3
    )

    # Debug log (if debug mode)
    if log_level == "DEBUG":
        debug_handler = RotatingFileHandler(
            log_dir / "debug.log",
            maxBytes=10_000_000,  # 10MB
            backupCount=1
        )
```

### Phase 4: Configuration Updates

#### 7. Update Configuration Module
**File**: `src/supsrc/config.py` (MODIFY)

Add new configuration options:
```python
@define(frozen=True, slots=True)
class GlobalConfig:
    """Global default settings for supsrc."""
    log_level: str = field(default="INFO", validator=_validate_log_level)
    log_to_file: bool = field(default=True)
    log_dir: Path | None = field(default=None)  # None = use .supsrc/local/logs
    use_supsrc_dir: bool = field(default=True)  # Enable new directory structure
    migrate_legacy_files: bool = field(default=True)  # Auto-migrate old files
```

#### 8. Add Repository-Specific Config Loading
**File**: `src/supsrc/config.py` (MODIFY)

Add function to load repo-specific config:
```python
def load_repository_config(repo_path: Path) -> dict[str, Any] | None:
    """Load repository-specific config from .supsrc/config.toml if it exists."""
    config_file = repo_path / ".supsrc" / "config.toml"
    if config_file.exists():
        import toml
        return toml.load(config_file)
    return None
```

### Phase 5: Migration Support

#### 9. Create Migration Module
**File**: `src/supsrc/utils/migration.py` (NEW)

```python
from __future__ import annotations
import shutil
from pathlib import Path
import structlog

log = structlog.get_logger("utils.migration")

class LegacyMigration:
    """Handles migration from old file structure to new .supsrc/ structure."""

    @classmethod
    def migrate_state_file(cls, repo_path: Path) -> bool:
        """Migrate .supsrc.state to .supsrc/state.json

        Returns True if migration was performed, False if not needed.
        """
        old_file = repo_path / ".supsrc.state"
        if not old_file.exists():
            return False

        new_file = repo_path / ".supsrc" / "state.json"
        new_file.parent.mkdir(parents=True, exist_ok=True)

        # Read old file, convert format if needed, write to new location
        # Keep backup of old file as .supsrc.state.backup

    @classmethod
    def check_and_migrate(cls, repo_path: Path) -> None:
        """Check for legacy files and migrate if needed."""
        if cls.migrate_state_file(repo_path):
            log.info("Migrated legacy state file", repo=str(repo_path))
```

### Phase 6: Integration Updates

#### 10. Update Orchestrator
**File**: `src/supsrc/runtime/orchestrator.py` (MODIFY)

- Import `SupsrcDirectories` and `LegacyMigration`
- In `__init__` or startup:
  ```python
  # Ensure directory structure exists
  for repo_path in self.repository_paths:
      SupsrcDirectories.ensure_structure(repo_path)
      LegacyMigration.check_and_migrate(repo_path)
  ```
- Update state file loading to use new paths
- Initialize file logging if configured

#### 11. Update CLI Commands
**Files**: `src/supsrc/cli/watch_cmds.py`, `src/supsrc/cli/sui_cmds.py` (MODIFY)

- Add `--no-migrate` flag to skip automatic migration
- Add `--log-dir` flag to override log directory
- Update state file operations to use new paths

### Phase 7: Testing

#### 12. Update Unit Tests
**File**: `tests/unit/test_state.py` (MODIFY)

- Update tests to expect new file paths
- Add tests for state file separation (shared vs local)
- Test migration from legacy paths

#### 13. Create Directory Management Tests
**File**: `tests/unit/test_directories.py` (NEW)

Test cases:
- Directory structure creation
- Path resolution for different file types
- Permission handling
- Edge cases (read-only filesystem, etc.)

#### 14. Create Migration Tests
**File**: `tests/unit/test_migration.py` (NEW)

Test cases:
- Legacy state file migration
- Format conversion if needed
- Backup creation
- Error handling

### Phase 8: Documentation

#### 15. Update README
**File**: `README.md` (MODIFY)

Add section explaining the directory structure:
```markdown
## File Organization

Supsrc uses a `.supsrc/` directory to organize its files:

- `.supsrc/` - Configuration and shareable state (can be committed to git)
  - `config.toml` - Repository-specific configuration
  - `state.json` - Shareable state (pause status, etc.)
- `.supsrc/local/` - Machine-specific data (gitignored)
  - `state.local.json` - Local state (PID, etc.)
  - `logs/` - Application logs
```

#### 16. Create Migration Guide
**File**: `docs/MIGRATION_GUIDE.md` (NEW)

Document:
- What changes for users
- Automatic migration behavior
- How to manually migrate if needed
- Rollback procedure if issues occur

## Implementation Order

1. **Start with infrastructure** (Phases 1-2): Directory management and state file updates
2. **Add logging** (Phase 3): Move logs to new location
3. **Update configuration** (Phase 4): Add new config options
4. **Implement migration** (Phase 5): Handle legacy files
5. **Integrate changes** (Phase 6): Update orchestrator and CLI
6. **Test thoroughly** (Phase 7): Ensure everything works
7. **Document** (Phase 8): Help users understand changes

## Backwards Compatibility

- Automatic migration of `.supsrc.state` files
- Fallback to legacy paths if new structure doesn't exist
- Configuration option to disable new structure (`use_supsrc_dir: false`)
- Keep support for legacy paths for 2-3 versions before removal

## Benefits

1. **Cleaner repository root** - Single `.supsrc/` directory instead of multiple files
2. **Clear separation** - Obvious what's shareable vs local-only
3. **Better git integration** - Easy to gitignore local data
4. **Centralized logs** - All logs in one predictable location
5. **Repository-specific config** - Can commit repo-specific settings
6. **Easier cleanup** - Delete `.supsrc/` to remove all supsrc data
7. **Follows conventions** - Similar to `.git/`, `.vscode/`, etc.

## Potential Issues & Solutions

| Issue | Solution |
|-------|----------|
| Read-only filesystems | Gracefully fall back to temp directories |
| Permission issues | Clear error messages, fallback paths |
| Migration failures | Keep backups, provide manual migration docs |
| Large log files | Implement log rotation |
| Config conflicts | Clear precedence rules (CLI > repo > global) |

## Success Criteria

- [ ] All existing tests pass
- [ ] New directory structure created automatically
- [ ] Legacy files migrated seamlessly
- [ ] Logs written to new location
- [ ] State files properly separated (shared vs local)
- [ ] Repository-specific config works
- [ ] Documentation updated
- [ ] No breaking changes for existing users