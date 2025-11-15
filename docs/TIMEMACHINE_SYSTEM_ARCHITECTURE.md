# Git Time Machine - System Architecture Document
**Version:** 1.0
**Date:** 2025-11-13
**Status:** Design Complete, Implementation Starting
**Owner:** Supsrc Team

---

## Executive Summary

The Git Time Machine is a P2P-enabled continuous backup system for Git repositories that creates granular micro-commits for every meaningful change, enabling time-travel recovery to any point in development history without relying on central servers.

**Key Capabilities:**
- Automatic micro-commits every N seconds after changes
- P2P synchronization across trusted devices
- Point-in-time file restoration
- Zero-configuration device discovery
- Git-native storage (no vendor lock-in)

---

## System Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Interface Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   CLI        │  │     TUI      │  │   Web UI     │         │
│  │  (Click)     │  │  (Textual)   │  │  (Future)    │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼─────────────────┐
│         │      Application Service Layer      │                 │
│  ┌──────▼──────────────────▼──────────────────▼─────────┐      │
│  │           Time Machine Orchestrator                   │      │
│  │  - Lifecycle management                               │      │
│  │  - Component coordination                             │      │
│  │  - Configuration management                           │      │
│  └──────┬────────────────────────────────────────────────┘      │
└─────────┼───────────────────────────────────────────────────────┘
          │
┌─────────┼───────────────────────────────────────────────────────┐
│         │         Core Engine Layer                             │
│  ┌──────▼──────────┐  ┌────────────────┐  ┌─────────────────┐ │
│  │ Micro-Commit    │  │   Snapshot      │  │  Time Travel    │ │
│  │    Engine       │  │   Manager       │  │    Browser      │ │
│  │                 │  │                 │  │                 │ │
│  │ - Debouncing    │  │ - Periodic      │  │ - Query         │ │
│  │ - Commit        │  │   snapshots     │  │   timeline      │ │
│  │   creation      │  │ - Retention     │  │ - Restore       │ │
│  │ - Rate limit    │  │   policies      │  │   files         │ │
│  └──────┬──────────┘  └────────┬───────┘  └────────┬────────┘ │
└─────────┼──────────────────────┼──────────────────┼───────────┘
          │                      │                  │
┌─────────┼──────────────────────┼──────────────────┼───────────┐
│         │     P2P Networking Layer                │           │
│  ┌──────▼──────────┐  ┌────────▼───────┐  ┌──────▼────────┐ │
│  │  P2P Sync       │  │   Device       │  │  Transfer     │ │
│  │  Manager        │  │   Discovery    │  │  Protocol     │ │
│  │                 │  │                │  │               │ │
│  │ - Sync loop     │  │ - mDNS/Avahi   │  │ - Git fetch   │ │
│  │ - Conflict      │  │ - Zeroconf     │  │ - Git push    │ │
│  │   detection     │  │ - DHT (future) │  │ - Incremental │ │
│  └──────┬──────────┘  └────────┬───────┘  └──────┬────────┘ │
└─────────┼──────────────────────┼──────────────────┼───────────┘
          │                      │                  │
┌─────────┼──────────────────────┼──────────────────┼───────────┐
│         │      Storage & Git Layer                │           │
│  ┌──────▼──────────┐  ┌────────▼───────┐  ┌──────▼────────┐ │
│  │  Git Repository │  │  Storage       │  │  Indexing     │ │
│  │     (pygit2)    │  │  Optimizer     │  │  Service      │ │
│  │                 │  │                │  │               │ │
│  │ - Objects       │  │ - Dedup        │  │ - File→Commit │ │
│  │ - Refs          │  │ - Compression  │  │   mapping     │ │
│  │ - Index         │  │ - Packing      │  │ - Fast lookup │ │
│  └─────────────────┘  └────────────────┘  └───────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Micro-Commit Engine

**Purpose:** Create granular commits automatically after file changes

**Responsibilities:**
- Monitor filesystem via watchdog integration
- Debounce file changes (wait for typing pause)
- Create Git commits with metadata
- Manage refs in `refs/timemachine/` namespace
- Enforce rate limiting

**Key Classes:**
```python
class MicroCommitEngine:
    - on_file_change(file_path: Path) -> None
    - _create_micro_commit() -> str  # Returns commit hash
    - _should_commit() -> bool
    - _generate_commit_message(timestamp) -> str
    - _get_last_timemachine_commit() -> Oid | None
```

**Data Flow:**
```
File Change → Debounce Timer → Rate Limit Check →
→ Stage Files → Create Commit → Create Ref → Notify P2P
```

**Configuration:**
- `debounce_seconds`: Default 30
- `min_commit_interval_seconds`: Default 10
- `max_pending_changes`: Default 50

**Storage:**
- Refs: `refs/timemachine/YYYY-MM-DD/HH-MM-SS-ffffff`
- Commit message format:
  ```
  🕐 Time Machine: HH:MM:SS

  Changed files: file1.py, file2.py

  [timemachine] Auto-saved checkpoint
  ```

---

### 2. Snapshot Manager

**Purpose:** Create periodic full snapshots and enforce retention policies

**Responsibilities:**
- Create hourly/daily/weekly snapshots
- Tag commits as snapshots
- Enforce retention policies
- Promote snapshots (hourly → daily → weekly)
- Protect user-marked snapshots

**Key Classes:**
```python
class SnapshotManager:
    - run_periodic_snapshots() -> None  # Background task
    - _create_hourly_snapshot() -> str
    - _create_daily_snapshot() -> str
    - _create_manual_snapshot(message: str) -> str
    - _enforce_retention() -> None
    - _promote_snapshot(from_type: str, to_type: str) -> None
```

**Snapshot Types:**
- `hourly`: Every hour, keep 24
- `daily`: Every 24h, keep 7
- `weekly`: Every 7d, keep 4
- `manual`: User-created, never auto-deleted
- `protected`: User-marked, never auto-deleted

**Storage:**
- Refs: `refs/snapshots/{type}/{timestamp}`
- Metadata in commit message

**Retention Policy:**
```
Keep:
- Last 24 hourly snapshots
- Last 7 daily snapshots
- Last 4 weekly snapshots
- All manual snapshots
- All protected snapshots

Delete:
- Hourly older than 24 (unless promoted)
- Daily older than 7 days (unless promoted)
- Weekly older than 4 weeks
```

---

### 3. Time Travel Browser

**Purpose:** Query and restore files from any point in history

**Responsibilities:**
- Build timeline index
- Query commits by file/time
- Restore files to specific state
- Show diffs between points in time
- Provide interactive TUI

**Key Classes:**
```python
class TimeTravelBrowser:
    - get_timeline(file_path, start_time, end_time, limit) -> list[MicroCommit]
    - restore_file(file_path, commit_hash, output_path) -> None
    - get_file_content_at_time(file_path, timestamp) -> bytes | None
    - diff_between_times(file_path, time1, time2) -> str

class TimelineIndex:
    - build_index() -> None
    - get_commits_for_file(file_path, limit) -> list[CommitRef]
    - _parse_timestamp_from_ref(ref_name) -> datetime
```

**Optimization:**
- In-memory index: `file_path → [commits]`
- Lazy loading of commit details
- Binary search for time ranges

---

### 4. P2P Sync Manager

**Purpose:** Discover and synchronize with trusted devices

**Responsibilities:**
- Announce service on local network (mDNS)
- Discover peers
- Verify device trust
- Incremental sync (fetch/push)
- Conflict detection

**Key Classes:**
```python
class P2PSyncManager:
    - start() -> None
    - _announce_service() -> None
    - _on_service_discovered(service_info) -> None
    - _sync_loop() -> None
    - _sync_with_peer(peer: TrustedDevice) -> None
    - _is_trusted_device(device_id: str) -> bool
```

**Network Protocol:**
```
Discovery: mDNS (_timemachine._tcp.local.)
Transport: Git protocol (git://)
Authentication: SSH key fingerprints
Sync: Git fetch/push with custom refspecs
```

**Trust Model:**
- Each device has unique device_id
- SSH key fingerprint as identity
- Manual pairing process
- Trusted device registry in config

---

### 5. Device Discovery

**Purpose:** Zero-config discovery of peer devices

**Responsibilities:**
- Announce via mDNS/Zeroconf
- Listen for peer announcements
- Parse service info
- Maintain peer list

**Technology:**
- **mDNS (Multicast DNS)**: Local network discovery
- **Zeroconf**: Service announcement/browsing
- **Service Type**: `_timemachine._tcp.local.`

**Service Info:**
```
Service: alice-laptop._timemachine._tcp.local.
Port: 9418 (git daemon)
Properties:
  - device_id=laptop-alice-2024
  - repo_hash=sha256:abc123...
  - version=1.0
```

**Discovery Flow:**
```
1. Device A starts → Announces on mDNS
2. Device B hears announcement → Checks repo_hash
3. If same repo → Check trust registry
4. If trusted → Add to peer list → Start sync
```

---

### 6. Storage Optimizer

**Purpose:** Minimize disk usage despite frequent commits

**Responsibilities:**
- Trigger Git garbage collection
- Pack loose objects
- Compress packfiles
- Report storage statistics

**Key Classes:**
```python
class StorageOptimizer:
    - optimize() -> None
    - _pack_objects() -> None
    - _prune_old_objects() -> None
    - _repack_with_compression() -> None
    - estimate_storage_savings() -> dict
```

**Optimization Strategy:**
```
Git's Native Features:
- Object deduplication (same file = same blob)
- Delta compression (diffs between versions)
- Packfile compression (zlib)

Our Additions:
- Periodic git gc --auto
- Custom gc triggers (after N commits)
- Retention policy enforcement
```

**Expected Savings:**
```
Example: 1000 commits of 10MB repo
- Naive: 10MB × 1000 = 10GB
- With dedup: ~200MB (98% savings)
```

---

## Data Model

### Commit Metadata Structure

```python
@dataclass
class MicroCommit:
    commit_hash: str                    # Git SHA-1
    timestamp: datetime                 # Creation time
    files_changed: list[str]            # Changed files
    diff_summary: str                   # Brief description
    trigger_type: str                   # "auto", "snapshot", "manual"
    parent_commit: str | None           # Previous commit
    snapshot_ref: str | None            # Associated snapshot
    lines_added: int
    lines_removed: int
    file_size_delta: int
    active_file: str | None             # File being edited
    cursor_position: tuple[int, int] | None
```

### Device Registry

```python
@dataclass
class TrustedDevice:
    device_id: str                      # Unique ID
    device_name: str                    # Human-readable
    fingerprint: str                    # SSH key fingerprint
    last_seen_addr: str | None          # IP:port
    discovery_method: str               # "mdns", "manual"
    last_sync: datetime | None
    last_known_commit: str | None
    sync_enabled: bool
    can_receive: bool                   # Allow pulls
    can_send: bool                      # Allow pushes
    auto_sync: bool
```

### Git Ref Namespace

```
refs/
├── heads/
│   └── main                           # Normal branch (unchanged)
├── timemachine/                       # Micro-commits
│   ├── 2025-11-13/
│   │   ├── 14-30-45-123456
│   │   ├── 14-31-02-234567
│   │   └── 14-31-15-345678
│   └── 2025-11-14/
│       └── ...
├── snapshots/                         # Periodic snapshots
│   ├── hourly/
│   │   ├── 2025-11-13T14:00:00
│   │   └── 2025-11-13T15:00:00
│   ├── daily/
│   │   └── 2025-11-13T00:00:00
│   └── manual/
│       └── 2025-11-13T16:30:00
└── remotes/                           # Peer replicas
    ├── laptop-alice-2024/
    │   └── timemachine/...
    └── desktop-home-2024/
        └── timemachine/...
```

---

## API Interfaces

### Internal Python API

```python
# Micro-Commit Engine
engine = MicroCommitEngine(repo_path, config)
await engine.on_file_change(Path("src/main.py"))

# Time Travel Browser
browser = TimeTravelBrowser(repo)
commits = browser.get_timeline(
    file_path="src/main.py",
    start_time=datetime.now() - timedelta(hours=1),
    limit=100
)
browser.restore_file("src/main.py", commits[5].commit_hash)

# P2P Sync
sync_mgr = P2PSyncManager(repo_path, config)
await sync_mgr.start()

# Snapshots
snapshot_mgr = SnapshotManager(repo, config)
await snapshot_mgr.create_manual_snapshot("Before refactor")
```

### CLI Interface

```bash
# Initialize
supsrc timemachine init [--device-name NAME]

# Watch for changes
supsrc timemachine watch [--daemon] [--tui]

# Browse history
supsrc timemachine log [FILE] [--last DURATION] [--limit N]

# Restore files
supsrc timemachine restore FILE --time TIME [--output PATH]

# Snapshots
supsrc timemachine snapshot create [--message MSG]
supsrc timemachine snapshot list
supsrc timemachine snapshot protect REF

# Devices
supsrc timemachine devices list
supsrc timemachine devices add [--name NAME] [--fingerprint FP]
supsrc timemachine devices remove DEVICE_ID

# Utilities
supsrc timemachine stats
supsrc timemachine optimize
```

---

## Configuration Schema

```toml
# ~/.config/supsrc/timemachine.toml

[timemachine]
enabled = true

[timemachine.commits]
debounce_seconds = 30
min_interval_seconds = 10
max_pending_changes = 50
include_patterns = ["src/**", "tests/**", "*.md"]
exclude_patterns = ["*.pyc", "__pycache__/**", ".venv/**"]

[timemachine.snapshots]
hourly_enabled = true
daily_enabled = true
weekly_enabled = true
keep_hourly = 24
keep_daily = 7
keep_weekly = 4
keep_all_protected = true

[timemachine.p2p]
enabled = true
discovery_method = "mdns"
announce_interval_seconds = 60
sync_interval_seconds = 120
device_name = "Alice's Laptop"
device_id = "laptop-alice-2024"

[[timemachine.p2p.devices]]
name = "home-desktop"
device_id = "desktop-home-2024"
fingerprint = "SHA256:abc123..."
auto_sync = true
can_receive = true
can_send = true

[timemachine.storage]
compression = true
deduplication = true
max_size_mb = 1000

[timemachine.notifications]
on_first_sync = true
on_sync_failure = true
on_restore = true
```

---

## Security Architecture

### Threat Model

| Threat | Mitigation |
|--------|-----------|
| **Untrusted peer** | Device fingerprint verification |
| **MITM attack** | SSH key-based authentication |
| **Data corruption** | Git's SHA-1 integrity checks |
| **Malicious commits** | Trust model (only paired devices) |
| **Privacy leak** | Local network only (Phase 1) |

### Trust Establishment

```
Device Pairing Flow:

1. Device A: Generate pairing code
   - Random 6-character code
   - Valid for 5 minutes
   - Display QR code

2. Device B: Enter pairing code
   - Connect to Device A
   - Exchange public keys
   - Verify fingerprints

3. Both devices: Store peer in trust registry
   - device_id
   - fingerprint
   - permissions
```

### Cryptographic Components

- **Device Identity**: Ed25519 keypair per device
- **Fingerprint**: SHA-256 of public key
- **Commit Verification**: Optional GPG signing
- **Transport**: Git protocol (can use SSH)

---

## Performance Characteristics

### Scalability Limits

| Metric | Target | Maximum Tested |
|--------|--------|----------------|
| **Commits per day** | 1,000 | TBD (Phase 1) |
| **Total commits** | 10,000 | TBD (Phase 1) |
| **Repository size** | 1 GB | TBD (Phase 1) |
| **Synced devices** | 3 | TBD (Phase 2) |
| **Files tracked** | 1,000 | TBD (Phase 1) |

### Performance Targets

| Operation | Target Latency | Notes |
|-----------|----------------|-------|
| **Micro-commit** | <200ms | From file save to commit |
| **Timeline query** | <1s | Display 1000 commits |
| **File restore** | <2s | Single file |
| **P2P sync** | <30s | 100 new commits |
| **Index rebuild** | <10s | 10,000 commits |

### Resource Usage

| Resource | Target | Monitoring |
|----------|--------|-----------|
| **CPU (idle)** | <1% | ps/top |
| **CPU (active)** | <10% | During commit |
| **Memory** | <100 MB | RSS |
| **Disk I/O** | <1 MB/s | iostat |
| **Network** | <100 KB/s | During sync |

---

## Deployment Architecture

### Single Device (Phase 1)

```
┌─────────────────────────────┐
│   Developer's Laptop        │
│                             │
│  ┌───────────────────────┐ │
│  │ supsrc timemachine    │ │
│  │   (daemon)            │ │
│  └───────────┬───────────┘ │
│              │              │
│  ┌───────────▼───────────┐ │
│  │ Git Repository        │ │
│  │ - Working tree        │ │
│  │ - .git/               │ │
│  │   - refs/timemachine/ │ │
│  │   - refs/snapshots/   │ │
│  └───────────────────────┘ │
└─────────────────────────────┘
```

### Multi-Device P2P (Phase 2)

```
┌──────────────────┐         ┌──────────────────┐
│   Laptop         │         │   Desktop        │
│                  │         │                  │
│  supsrc tm       │◄───────►│  supsrc tm       │
│  (daemon)        │  mDNS   │  (daemon)        │
│                  │  sync   │                  │
│  Git Repo        │         │  Git Repo        │
│  - timemachine/  │         │  - timemachine/  │
│  - remotes/      │         │  - remotes/      │
│    laptop/       │         │    desktop/      │
└──────────────────┘         └──────────────────┘
         │                            │
         │       ┌──────────────────┐ │
         └──────►│  Lab Workstation │◄┘
                 │                  │
                 │  supsrc tm       │
                 │  (daemon)        │
                 │                  │
                 │  Git Repo        │
                 │  - timemachine/  │
                 │  - remotes/      │
                 │    laptop/       │
                 │    desktop/      │
                 └──────────────────┘
```

---

## Monitoring & Observability

### Logging Strategy

```python
# Structured logging with context
log.info(
    "Micro-commit created",
    commit_hash=hash[:7],
    files_changed=len(files),
    debounce_time=elapsed,
    repo_id=repo_id,
    device_id=device_id
)
```

**Log Levels:**
- `DEBUG`: Detailed flow (debounce timers, ref creation)
- `INFO`: Key operations (commits, syncs, restores)
- `WARNING`: Anomalies (slow operations, skipped commits)
- `ERROR`: Failures (commit errors, sync failures)
- `CRITICAL`: Fatal errors (repo corruption, config errors)

### Metrics to Track

```yaml
Counters:
  - timemachine_commits_total{trigger_type}
  - timemachine_syncs_total{peer_id, status}
  - timemachine_restores_total
  - timemachine_errors_total{component}

Gauges:
  - timemachine_pending_changes
  - timemachine_total_commits
  - timemachine_storage_bytes
  - timemachine_connected_peers

Histograms:
  - timemachine_commit_duration_seconds
  - timemachine_sync_duration_seconds
  - timemachine_restore_duration_seconds
```

### Health Checks

```python
class TimeMachineHealthCheck:
    def check_health() -> dict:
        return {
            "status": "healthy",  # or "degraded", "unhealthy"
            "last_commit": "2 minutes ago",
            "pending_changes": 0,
            "connected_peers": 2,
            "storage_usage_mb": 127,
            "errors_last_hour": 0,
        }
```

---

## Error Handling Strategy

### Error Categories

| Category | Response | User Impact |
|----------|----------|-------------|
| **Transient** | Retry with backoff | None (auto-recovery) |
| **Recoverable** | Pause + notify user | Manual intervention |
| **Fatal** | Stop daemon | Require restart |

### Specific Error Scenarios

```python
# 1. Commit failure (disk full)
try:
    create_commit()
except pygit2.GitError as e:
    if "disk full" in str(e):
        log.critical("Disk full, pausing time machine")
        pause_monitoring()
        notify_user("Time machine paused: disk full")

# 2. Sync failure (network down)
try:
    sync_with_peer(peer)
except ConnectionError:
    log.warning("Peer unreachable, will retry")
    schedule_retry(peer, backoff=60)

# 3. Corrupt repository
try:
    validate_repo()
except RepoCorruptionError:
    log.critical("Repository corruption detected")
    notify_user("CRITICAL: Time machine corruption")
    create_emergency_backup()
    exit(1)
```

---

## Testing Strategy

### Unit Tests

```python
# test_micro_commit_engine.py
def test_debounce_timer():
    """Verify commits wait for typing pause"""

def test_rate_limiting():
    """Verify min interval between commits"""

def test_ref_naming():
    """Verify ref names are valid and unique"""
```

### Integration Tests

```python
# test_p2p_sync.py
def test_device_discovery():
    """Verify mDNS discovery between two instances"""

def test_incremental_sync():
    """Verify only new commits are synced"""

def test_conflict_detection():
    """Verify conflicts are detected and handled"""
```

### Performance Tests

```python
# test_performance.py
def test_1000_commits():
    """Create 1000 commits, verify <100ms each"""

def test_storage_efficiency():
    """Verify >95% storage savings vs naive"""

def test_timeline_query_speed():
    """Query 10,000 commits in <1s"""
```

### End-to-End Tests

```bash
# test_e2e.sh
1. Initialize time machine
2. Make 100 file edits
3. Verify 100 micro-commits created
4. Restore file from 50th commit
5. Verify file content matches
```

---

## Migration & Compatibility

### Backward Compatibility

- **Existing supsrc users**: Time machine is opt-in feature
- **Standard Git**: Repos remain standard Git repos
- **Ref namespace**: `refs/timemachine/` doesn't interfere with normal refs
- **Export**: Can delete time machine refs, repo still works

### Version Migration

```python
# Future version upgrades
class TimeMachineMigration:
    def migrate_v1_to_v2():
        """Migrate from v1.0 to v2.0"""
        # Update ref format
        # Update config schema
        # Preserve all commits
```

---

## Disaster Recovery

### Data Loss Scenarios

| Scenario | Recovery Strategy |
|----------|------------------|
| **Laptop stolen** | Restore from synced peers |
| **Accidental deletion** | Restore from time machine |
| **Disk corruption** | Restore from peer backups |
| **Time machine corruption** | Fallback to main branch |

### Backup Strategy

```
Primary: Time machine commits on local disk
Secondary: P2P replicas on trusted devices
Tertiary: (Optional) Remote Git server backup
```

### Recovery Procedures

```bash
# 1. Restore from peer
supsrc timemachine sync --force-pull --from peer-id

# 2. Rebuild index
supsrc timemachine rebuild-index

# 3. Verify integrity
supsrc timemachine verify

# 4. Emergency: Extract to standard branch
git branch recover-timemachine refs/timemachine/latest
```

---

## Future Enhancements

### Phase 3: Cloud Relay (Optional)

```
Enable sync between devices not on same network
- TURN/STUN relay servers
- End-to-end encryption
- Paid tier for relay hosting
```

### Phase 4: Intelligent Features

```
- AI-powered commit grouping
- Anomaly detection (unusual patterns)
- Smart snapshot timing (before risky operations)
- Semantic diff visualization
```

### Phase 5: IDE Integration

```
- VS Code extension
- JetBrains plugin
- Real-time timeline sidebar
- Visual time travel
```

---

## Appendix

### Technology Stack

| Component | Technology | Version | License |
|-----------|-----------|---------|---------|
| **Language** | Python | 3.11+ | PSF |
| **Git** | pygit2 | 1.18+ | GPL + linking exception |
| **Filesystem** | watchdog | 6.0+ | Apache 2.0 |
| **Networking** | zeroconf | 0.131+ | LGPL |
| **Logging** | structlog | 25.3+ | MIT/Apache 2.0 |
| **CLI** | click | 8.1+ | BSD-3-Clause |
| **TUI** | textual | 0.70+ | MIT |
| **Data** | attrs | 25.3+ | MIT |

### Glossary

- **Micro-commit**: Automatic fine-grained Git commit
- **Snapshot**: Periodic full checkpoint
- **Time machine ref**: Git ref in `refs/timemachine/`
- **P2P sync**: Peer-to-peer synchronization
- **Device pairing**: Establishing trust between devices
- **Debouncing**: Waiting for typing pause before commit
- **Retention policy**: Rules for deleting old commits

### References

- Git internals: https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain
- pygit2 docs: https://www.pygit2.org/
- mDNS/Zeroconf: https://python-zeroconf.readthedocs.io/
- macOS Time Machine: https://support.apple.com/en-us/HT201250

---

**Document End**

*Next: Implementation Handoff Plan*
