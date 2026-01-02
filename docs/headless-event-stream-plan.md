# Headless Event Stream Enhancement Plan

## Overview

This document outlines the plan to make `supsrc watch` (headless mode) as informative as `sui` (TUI mode) by implementing a best-of-breed scrolling event update system.

**Goal**: Transform `supsrc watch` from a basic status reporter into a rich, informative event stream comparable to `sui` but optimized for headless/scripting environments.

---

## Current State Analysis

### What Works
- Basic event collection infrastructure via `EventCollector`
- JSON event logging to `.supsrc/local/logs/events.jsonl`
- Periodic status reporting showing repository states
- Event type definitions (FileChangeEvent, GitCommitEvent, etc.)

### What's Missing
- The `_print_event_to_console()` method in `orchestrator.py:305-317` is stubbed out
- No structured event display in headless mode
- No color coding or emoji indicators
- No real-time event streaming
- Limited terminal responsiveness

---

## 13 Critical Details for Implementation

### **1. Event Display Infrastructure**

**Current State**: The headless mode has a stubbed-out `_print_event_to_console()` method in `orchestrator.py:305-317` that extracts timestamp and repo_id but doesn't actually print anything.

**What's Needed**:
- Implement full event formatting and terminal output using Rich Console
- Support color-coded, emoji-rich event streaming similar to TUI's EventFeedTable
- Ensure proper terminal handling without screen clearing

**Files to Modify**:
- `src/supsrc/runtime/orchestrator.py` - Implement `_print_event_to_console()`
- Create `src/supsrc/output/console_formatter.py` - New formatter class

---

### **2. Event Type Coverage**

**Current State**: The event system has extensive event types but headless mode doesn't handle them distinctively.

**Event Types to Support**:
- `FileChangeEvent` - File system changes
- `GitCommitEvent` - Successful commits
- `GitPushEvent` - Push operations
- `RuleTriggeredEvent` - Rule evaluation triggers
- `ErrorEvent` - Errors and failures
- `ConfigReloadEvent` - Configuration reloads
- `UserActionEvent` - Manual user actions
- `ExternalCommitEvent` - Commits from outside supsrc
- `ConflictDetectedEvent` - Merge conflicts
- `RepositoryFrozenEvent` - Repository frozen due to issues
- `TestFailureEvent` - Test failures
- `LLMVetoEvent` - AI-based vetoes

**What's Needed**:
- Implement event-specific formatting logic for each type
- Port EventFormatter pattern from TUI to headless mode
- Add type-specific metadata extraction

**Files to Create/Modify**:
- `src/supsrc/output/event_formatters.py` - Event-specific formatters
- `src/supsrc/output/console_renderer.py` - Console rendering logic

---

### **3. Structured Event Table Format**

**Current State**: TUI uses a 6-column DataTable (Time, Repo, Emoji, Count, Files, Message). Headless mode has no comparable structure.

**Table Structure**:
```
[HH:MM:SS] [repo-id          ] [🎯] [#  ] [file/path         ] [message               ]
[08:45:23] [my-project       ] [📝] [3  ] [src/main.py       ] [File modified         ]
[08:45:24] [my-project       ] [✅] [3  ] [3 files          ] [Committed changes     ]
[08:45:25] [another-repo     ] [⏳] [5  ] [-                ] [Inactivity rule: 30s  ]
```

**What's Needed**:
- Create terminal-friendly columnar output with proper alignment
- Support dynamic column widths based on terminal size
- Implement truncation with ellipsis for long values
- Add column headers (optional, controlled by flag)

**Column Specifications**:
- **Time**: 8 chars fixed `HH:MM:SS`
- **Repo**: 20 chars (truncate with `...`)
- **Emoji**: 3 chars (operation indicator)
- **Count**: 4 chars (numerical impact)
- **Files**: 20-40 chars (responsive to terminal width)
- **Message**: Remaining space (auto-truncate)

**Files to Create**:
- `src/supsrc/output/table_formatter.py` - Columnar formatting

---

### **4. Live Scrolling Terminal Output**

**Current State**: The `_status_reporter()` only prints status lines every 10 seconds when idle or every 1 second during active timers. No continuous event stream.

**What's Needed**:
- Implement continuous, real-time event streaming to stdout
- Events append to terminal (scroll naturally)
- No screen clearing or cursor manipulation (unless `--live` mode)
- Proper line buffering for piping/redirection

**Implementation Options**:
1. **Append Mode** (default): Events print as they arrive, terminal scrolls naturally
2. **Live Mode** (`--live` flag): Use Rich Live display with auto-refresh
3. **Quiet Mode** (`--quiet` flag): Only show errors and critical events

**Files to Modify**:
- `src/supsrc/cli/watch_cmds.py` - Add output mode flags
- `src/supsrc/runtime/orchestrator.py` - Implement streaming logic

---

### **5. Color-Coded Event Severity**

**Current State**: No color coding in headless output. TUI uses rich markup for styling.

**Color Scheme**:
- 🔴 **Red** (`red`): Errors, failures, conflicts
- 🟢 **Green** (`green`): Successful git operations, commits, pushes
- 🟡 **Yellow** (`yellow`): Warnings, conflicts detected, repository frozen
- 🔵 **Blue** (`blue`): Informational events, file changes, monitoring
- 🟣 **Magenta** (`magenta`): User actions, manual operations
- ⚪ **White/Default**: Status updates, neutral events
- 🟠 **Orange** (`dark_orange`): Rule triggers, timers

**What's Needed**:
- Map event types to severity levels
- Use Rich Console styling with fallback for no-color environments
- Respect `NO_COLOR` environment variable
- Add `--no-color` flag for explicit disabling

**Severity Mapping**:
```python
SEVERITY_COLORS = {
    "error": "red",
    "success": "green",
    "warning": "yellow",
    "info": "blue",
    "user": "magenta",
    "rule": "dark_orange",
    "neutral": "white",
}
```

**Files to Create**:
- `src/supsrc/output/color_scheme.py` - Color definitions and mapping

---

### **6. Event Emoji Indicators**

**Current State**: TUI's `EventFormatter.get_event_emoji()` provides rich emoji mapping. Headless mode doesn't use this.

**Emoji Mapping**:
- 📝 **File changes**: modified, created, deleted
- ✅ **Commits**: successful commits
- 🚀 **Push**: push to remote
- ⏳ **Rule triggers**: inactivity, save count
- ❌ **Errors**: general errors, failures
- 🔄 **Config reloads**: configuration changes
- 👤 **User actions**: manual triggers
- ⚠️ **Conflicts**: merge conflicts, external commits
- 🧊 **Repository frozen**: frozen state
- 🧪 **Tests**: test results
- 🤖 **LLM**: AI-based decisions
- 📋 **Monitoring**: start/stop events
- 💾 **Staging**: file staging operations

**What's Needed**:
- Port emoji mapping from `EventFormatter` to headless formatter
- Ensure emoji rendering works in common terminals
- Add fallback ASCII mode for terminals without emoji support (`--ascii` flag)

**ASCII Fallback Table**:
```
📝 -> [M]  (Modified)
✅ -> [✓]  (Success)
❌ -> [✗]  (Error)
⏳ -> [⏱]  (Timer)
🔄 -> [↻]  (Reload)
```

**Files to Create**:
- `src/supsrc/output/emoji_map.py` - Emoji and ASCII mappings

---

### **7. Repository Status Summary Line**

**Current State**: Status reporter shows basic status with change counts and timers, but it's sparse and only updates periodically.

**Enhanced Status Line Format**:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 REPOSITORIES: 3 active | 1 paused | 0 stopped | Queue: 0 events | Last: 08:45:23
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Per-Repository Status**:
```
🟢 my-project: clean (30s) [main]
🟡 another-repo: +3/-1/~5 (15s) [develop] [PAUSED]
🔴 third-repo: error - merge conflict [feature/foo]
```

**What's Needed**:
- Update frequency: Every 1 second when timers active, every 5 seconds when idle
- Show aggregate statistics across all repositories
- Display last event timestamp
- Show queue depth (number of pending events)
- Include pause/suspend/stop states prominently

**Files to Modify**:
- `src/supsrc/cli/watch_cmds.py` - Enhance `_status_reporter()`
- `src/supsrc/output/status_renderer.py` - New status rendering module

---

### **8. Contextual File Path Display**

**Current State**: No file path display in headless events. TUI shows truncated paths in the "Files" column.

**Path Display Strategies**:
1. **Single File**: Show relative path from repo root
   ```
   src/supsrc/runtime/orchestrator.py
   ```

2. **Long Path**: Truncate middle with ellipsis
   ```
   src/.../deep/nested/file.py
   ```

3. **Multiple Files**: Show count and first file
   ```
   3 files (src/main.py, ...)
   ```

4. **Many Files**: Just show count
   ```
   25 files
   ```

**Truncation Rules**:
- Available width: 20-40 chars (depends on terminal width)
- If path > width: truncate middle, preserve filename
- Preserve extension for context
- Show directory hint if space allows

**What's Needed**:
- Path normalization relative to repository root
- Smart middle truncation algorithm
- Multi-file aggregation logic
- Width-aware rendering

**Files to Create**:
- `src/supsrc/output/path_formatter.py` - Path formatting utilities

---

### **9. Event Metadata Enrichment**

**Current State**: Events have metadata dicts, but headless mode doesn't display them meaningfully.

**Metadata per Event Type**:

**FileChangeEvent**:
- `change_type`: added/modified/deleted
- `file_path`: Path object
- `repo_id`: Repository identifier

**GitCommitEvent**:
- `commit_hash`: Full hash (display first 7 chars)
- `branch`: Branch name
- `files_changed`: Count of files
- `commit_message`: First line (optional)

**RuleTriggeredEvent**:
- `rule_type`: inactivity/save_count/manual
- `threshold`: Trigger threshold value
- `current_value`: Current measured value
- `repo_id`: Target repository

**ErrorEvent**:
- `error_type`: Exception class name
- `error_message`: Error message
- `repo_id`: Affected repository
- `traceback`: Stack trace (truncated)

**What's Needed**:
- Extract relevant metadata per event type
- Format metadata for compact display
- Include key details in message column
- Support verbose mode (`--verbose`) for full metadata

**Display Format Examples**:
```
[08:45:23] [my-project] [📝] [1  ] [src/main.py      ] [Modified]
[08:45:24] [my-project] [✅] [3  ] [3 files         ] [abc123f: "Fix bug"]
[08:45:25] [my-project] [⏳] [-  ] [-               ] [Inactivity: 30/30s]
[08:45:26] [my-project] [❌] [-  ] [-               ] [GitError: Push failed]
```

**Files to Create**:
- `src/supsrc/output/metadata_extractor.py` - Metadata extraction logic

---

### **10. Terminal Width Responsiveness**

**Current State**: No terminal width awareness. Output could overflow or wrap poorly.

**Terminal Size Detection**:
```python
import shutil
width, height = shutil.get_terminal_size(fallback=(80, 24))
```

**Responsive Column Layout**:

**Wide Terminal (≥120 chars)**:
```
[HH:MM:SS] [repository-name     ] [🎯] [#  ] [path/to/file.py              ] [Full message here]
```

**Standard Terminal (80-119 chars)**:
```
[HH:MM:SS] [repo-name  ] [🎯] [# ] [path/file.py    ] [Message]
```

**Narrow Terminal (<80 chars)**:
```
[HH:MM:SS] [repo] [🎯] [msg]
```

**What's Needed**:
- Detect terminal width on startup and on SIGWINCH signal
- Adjust column widths dynamically
- Hide less important columns on narrow terminals
- Ensure minimum usable width (50 chars)
- Support `--width=N` flag to override detection

**Column Priority** (hide in this order when space limited):
1. Count column (4 chars)
2. Files column (20-40 chars)
3. Emoji column (3 chars) - fallback to text prefix
4. Repo column (20 chars) - truncate more aggressively
5. Time and Message always visible

**Files to Create**:
- `src/supsrc/output/terminal_detector.py` - Terminal size detection
- `src/supsrc/output/responsive_layout.py` - Layout calculation

---

### **11. Event Rate Limiting & Batching**

**Current State**: Every event would be printed immediately, potentially flooding the terminal during high-activity periods.

**Batching Strategies**:

**1. Time-Based Batching**:
- Collect events in 100ms windows
- If >1 event in window, show summary
```
[08:45:23] [my-project] [📝] [25 ] [multiple files   ] [Batch: 25 file changes]
```

**2. Event Type Grouping**:
- Group consecutive events of same type
```
[08:45:23] [my-project] [📝] [10 ] [src/**/*.py      ] [10 Python files modified]
```

**3. Rate Limiting**:
- Max events per second: 10 (configurable)
- Show overflow indicator
```
[08:45:23] [my-project] [📝] [50+] [multiple files   ] [High activity... (50+ events)]
```

**4. Smart Suppression**:
- During git operations, buffer file change events
- Show them as single summary after commit
```
[08:45:23] [my-project] [✅] [15 ] [src/            ] [Committed 15 files]
```

**What's Needed**:
- Event queue with time-window batching
- Configurable batch window size (default 100ms)
- Configurable max rate (default 10/sec)
- Smart grouping by event type and repository
- Overflow detection and summary display

**Configuration**:
```toml
[output]
batch_window_ms = 100
max_events_per_second = 10
enable_batching = true
batch_threshold = 5  # Minimum events to trigger batching
```

**Files to Create**:
- `src/supsrc/output/event_batcher.py` - Event batching logic
- `src/supsrc/output/rate_limiter.py` - Rate limiting

---

### **12. Historical Event Scrollback**

**Current State**: Events scroll off the terminal history. TUI keeps all events in the DataTable with scrollback support.

**Scrollback Strategies**:

**1. Terminal Scrollback** (default):
- Print events to stdout with proper line endings
- Let terminal handle scrollback naturally
- Events persist in terminal history buffer
- Works with `tmux`, `screen`, terminal scrollback

**2. Ring Buffer Mode** (`--buffer=N`):
- Keep last N events in memory
- Support `supsrc tail` command to view buffer
- Useful for long-running sessions

**3. Live Mode** (`--live`):
- Use Rich Live display
- Clear and redraw screen
- Show fixed window of recent events (e.g., last 50)
- Similar to `tail -f` behavior

**What's Needed**:
- Ensure proper stdout flushing for scrollback
- Implement optional ring buffer for event history
- Add `--buffer=N` flag to control buffer size
- Create `supsrc tail` command to view recent events
- Support `--follow` mode for real-time tailing

**Buffer Storage**:
```python
# In-memory ring buffer (optional)
MAX_BUFFER_SIZE = 1000  # Configurable
event_buffer: deque[Event] = deque(maxlen=MAX_BUFFER_SIZE)
```

**Files to Create**:
- `src/supsrc/output/event_buffer.py` - In-memory event buffer
- `src/supsrc/cli/tail_cmds.py` - Tail command (if not exists)

---

### **13. JSON Log Correlation**

**Current State**: JSON event logger writes to `.supsrc/local/logs/events.jsonl` separately. Console output is disconnected.

**Synchronization Requirements**:
1. **Same Timestamp Format**: ISO 8601 in both outputs
2. **Same Event Ordering**: Events appear in identical order
3. **Cross-Reference**: Console shows log file path on startup
4. **Unique Event IDs**: Add correlation ID to both outputs

**Startup Message**:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 Supsrc Watch - Event Stream Mode
📁 Monitoring: 3 repositories
📝 Event Log: /path/to/.supsrc/local/logs/events.jsonl
📋 App Log: /tmp/supsrc_app.log
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Event Correlation ID**:
```json
{
  "event_id": "evt_20250109_084523_abc123",
  "timestamp": "2025-01-09T08:45:23.123456",
  "source": "git",
  "description": "Committed changes"
}
```

**Console Output**:
```
[08:45:23] [my-project] [✅] [3  ] [3 files] [Committed changes] [evt_...abc123]
```

**What's Needed**:
- Generate unique event IDs (timestamp + random suffix)
- Add event ID to JSON logs
- Optionally show event ID in console (verbose mode)
- Ensure atomic writes to JSON log before console output
- Add `--events-only` flag to suppress status lines
- Add `--json-only` flag to skip console formatting

**Flags**:
- `--events-only`: Show only events, no status summaries
- `--json-only`: Write only to JSON log, no console output
- `--no-log`: Disable JSON logging, console only
- `--verbose`: Show event IDs and full metadata

**Files to Modify**:
- `src/supsrc/events/json_logger.py` - Add event ID support
- `src/supsrc/runtime/orchestrator.py` - Add correlation logic
- `src/supsrc/cli/watch_cmds.py` - Add output control flags

---

## Implementation Plan

### Phase 1: Core Event Display (Week 1)

**Goal**: Get basic structured event display working

#### Tasks:
1. **Create output module structure**
   - Create `src/supsrc/output/__init__.py`
   - Create `src/supsrc/output/console_formatter.py`
   - Create `src/supsrc/output/event_formatters.py`
   - Create `src/supsrc/output/emoji_map.py`

2. **Implement basic event formatting**
   - Port EventFormatter logic from TUI
   - Implement emoji mapping with ASCII fallback
   - Create formatter for each event type

3. **Implement console output in orchestrator**
   - Complete `_print_event_to_console()` method
   - Use Rich Console for output
   - Ensure proper event subscription

4. **Add basic table formatting**
   - Create `table_formatter.py`
   - Implement fixed-width columnar output
   - Add proper alignment and truncation

#### Success Criteria:
- Events print to console with emojis
- Basic table structure is visible
- All event types have distinct formatting
- No crashes or exceptions

#### Files Created/Modified:
- `src/supsrc/output/console_formatter.py` (new)
- `src/supsrc/output/event_formatters.py` (new)
- `src/supsrc/output/emoji_map.py` (new)
- `src/supsrc/output/table_formatter.py` (new)
- `src/supsrc/runtime/orchestrator.py` (modify)

---

### Phase 2: Polish & Color (Week 2)

**Goal**: Add real-time updates, colors, and metadata enrichment

#### Tasks:
1. **Implement color scheme**
   - Create `color_scheme.py`
   - Map event types to severity colors
   - Respect NO_COLOR environment variable
   - Add `--no-color` flag

2. **Add metadata extraction**
   - Create `metadata_extractor.py`
   - Extract relevant metadata per event type
   - Format metadata for display
   - Add `--verbose` flag for full metadata

3. **Enhance status reporter**
   - Create `status_renderer.py`
   - Improve status line formatting
   - Add aggregate statistics
   - Update frequency adjustment

4. **Add real-time streaming**
   - Ensure continuous event output
   - Proper stdout flushing
   - No screen clearing (append mode)

#### Success Criteria:
- Events are color-coded by severity
- Metadata displays correctly per event type
- Status lines are informative and update regularly
- Events stream in real-time without lag

#### Files Created/Modified:
- `src/supsrc/output/color_scheme.py` (new)
- `src/supsrc/output/metadata_extractor.py` (new)
- `src/supsrc/output/status_renderer.py` (new)
- `src/supsrc/cli/watch_cmds.py` (modify - add flags)

---

### Phase 3: Terminal Responsiveness (Week 3)

**Goal**: Make output responsive to terminal width and handle high event rates

#### Tasks:
1. **Terminal size detection**
   - Create `terminal_detector.py`
   - Detect width on startup
   - Handle SIGWINCH for resize events
   - Add `--width=N` override flag

2. **Responsive layout**
   - Create `responsive_layout.py`
   - Calculate column widths based on terminal size
   - Implement column hiding for narrow terminals
   - Adjust truncation dynamically

3. **Path formatting**
   - Create `path_formatter.py`
   - Implement smart path truncation
   - Handle multiple files display
   - Width-aware rendering

4. **Event batching**
   - Create `event_batcher.py`
   - Implement time-window batching
   - Group events by type and repo
   - Add configuration options

5. **Rate limiting**
   - Create `rate_limiter.py`
   - Implement max events/second limit
   - Show overflow indicators
   - Smart suppression during git ops

#### Success Criteria:
- Output adapts to terminal width changes
- Long paths truncate intelligently
- High-activity periods show batched summaries
- No terminal flooding during mass operations

#### Files Created/Modified:
- `src/supsrc/output/terminal_detector.py` (new)
- `src/supsrc/output/responsive_layout.py` (new)
- `src/supsrc/output/path_formatter.py` (new)
- `src/supsrc/output/event_batcher.py` (new)
- `src/supsrc/output/rate_limiter.py` (new)

---

### Phase 4: Integration & Advanced Features (Week 4)

**Goal**: JSON log correlation, scrollback support, and advanced modes

#### Tasks:
1. **Event correlation IDs**
   - Add unique ID generation
   - Modify JSONEventLogger to include IDs
   - Show IDs in verbose mode
   - Ensure synchronization

2. **JSON log correlation**
   - Show log file path on startup
   - Ensure atomic write ordering
   - Add cross-reference support
   - Implement `--events-only` and `--json-only` flags

3. **Event buffer (optional)**
   - Create `event_buffer.py`
   - Implement ring buffer for history
   - Add `--buffer=N` flag
   - Support for `supsrc tail` command

4. **Live mode (optional)**
   - Implement `--live` mode using Rich Live
   - Fixed-window display
   - Auto-refresh logic

5. **Documentation and testing**
   - Update README with new flags
   - Create usage examples
   - Write unit tests for formatters
   - Write integration tests for output

#### Success Criteria:
- JSON logs and console output are synchronized
- Event IDs enable correlation
- Optional buffer and live modes work
- All flags documented and tested

#### Files Created/Modified:
- `src/supsrc/events/json_logger.py` (modify)
- `src/supsrc/output/event_buffer.py` (new, optional)
- `src/supsrc/cli/watch_cmds.py` (modify - add all flags)
- `docs/headless-mode.md` (new - usage documentation)
- `tests/unit/output/test_*.py` (new - unit tests)

---

## Configuration Schema

Add new section to `supsrc.conf`:

```toml
[output]
# Event output configuration for headless mode

# Enable color output (can be overridden by NO_COLOR env var)
color = true

# Use emoji indicators (false = ASCII fallback)
emoji = true

# Event batching configuration
enable_batching = true
batch_window_ms = 100        # Time window for batching events
batch_threshold = 5          # Minimum events to trigger batching
max_events_per_second = 10   # Rate limit for event display

# Table formatting
show_column_headers = false  # Show column headers at startup
min_terminal_width = 50      # Minimum supported terminal width

# Event buffer
enable_buffer = false        # Keep events in memory
buffer_size = 1000          # Maximum events to buffer

# Verbosity
show_event_ids = false      # Show correlation IDs (verbose mode)
show_metadata = false       # Show full event metadata (verbose mode)

# Output modes
events_only = false         # Suppress status lines
json_only = false          # No console output, JSON only
```

---

## CLI Flags Summary

### New Flags for `supsrc watch`

```bash
# Output control
--no-color              # Disable color output
--ascii                 # Use ASCII instead of emojis
--events-only           # Show only events, no status summaries
--json-only             # Write only to JSON log, no console
--no-log                # Disable JSON logging
--verbose, -v           # Show event IDs and full metadata

# Display modes
--live                  # Use live refresh mode (like watch command)
--width=N               # Override terminal width detection

# Event processing
--no-batch              # Disable event batching
--max-rate=N            # Max events per second (default: 10)
--buffer=N              # Enable event buffer with size N

# Debugging
--show-headers          # Show column headers
--debug-events          # Show raw event data
```

### Usage Examples

```bash
# Standard mode with color and emojis
supsrc watch

# Plain mode for logging/scripting
supsrc watch --no-color --ascii

# High-verbosity mode for debugging
supsrc watch --verbose --show-headers

# Events-only mode (no status lines)
supsrc watch --events-only

# JSON logging only (silent console)
supsrc watch --json-only

# Live refresh mode
supsrc watch --live

# Narrow terminal optimization
supsrc watch --width=60
```

---

## Testing Strategy

### Unit Tests

1. **Formatter Tests**
   - `test_console_formatter.py` - Console formatting logic
   - `test_event_formatters.py` - Event-specific formatters
   - `test_emoji_map.py` - Emoji and ASCII mapping
   - `test_color_scheme.py` - Color assignment
   - `test_table_formatter.py` - Table layout
   - `test_path_formatter.py` - Path truncation

2. **Layout Tests**
   - `test_terminal_detector.py` - Terminal size detection
   - `test_responsive_layout.py` - Column width calculation

3. **Event Processing Tests**
   - `test_event_batcher.py` - Batching logic
   - `test_rate_limiter.py` - Rate limiting
   - `test_metadata_extractor.py` - Metadata extraction

### Integration Tests

1. **End-to-End Event Flow**
   - Create test repository
   - Trigger various events
   - Verify console output format
   - Verify JSON log correlation

2. **Terminal Width Scenarios**
   - Test wide terminal (120+ chars)
   - Test standard terminal (80 chars)
   - Test narrow terminal (60 chars)
   - Test resize handling

3. **High-Activity Scenarios**
   - Mass file operations (50+ files)
   - Rapid event generation
   - Verify batching behavior
   - Verify rate limiting

### Manual Testing

1. **Visual Verification**
   - Run in various terminal emulators
   - Verify emoji rendering
   - Verify color scheme
   - Check layout at different widths

2. **Performance Testing**
   - Monitor CPU usage during high activity
   - Verify no event loss during batching
   - Check memory usage with large buffer

---

## Success Metrics

### Functional Requirements
- ✅ All event types display with appropriate formatting
- ✅ Color coding works across major terminals
- ✅ Emojis render correctly (with ASCII fallback)
- ✅ Layout adapts to terminal width
- ✅ Event batching prevents terminal flooding
- ✅ JSON logs correlate with console output

### Performance Requirements
- Events display within 50ms of occurrence (non-batched)
- CPU overhead <5% for event formatting
- Memory usage <10MB for event buffer
- No lag during high-activity periods (100+ events/sec)

### User Experience
- Output is readable at 80-char terminal width
- Status updates are non-intrusive
- Event stream can be piped/redirected
- `--help` provides clear flag documentation

---

## Exploratory Enhancements

### Phase 5+ (Optional)

1. **Interactive Filtering**
   - `--filter-repo=REGEX` - Filter by repository
   - `--filter-type=TYPE` - Filter by event type
   - `--filter-level=LEVEL` - Filter by severity

2. **Event Search**
   - `supsrc events search QUERY` - Search event history
   - Support for regex patterns
   - Time range filtering

3. **Export Formats**
   - `--format=json|csv|html` - Export format
   - HTML report generation
   - CSV for spreadsheet import

4. **Remote Streaming**
   - WebSocket server mode
   - Web dashboard for remote monitoring
   - Multi-repository aggregation

5. **Performance Metrics**
   - Event throughput statistics
   - Repository health scores
   - Performance trending

---

## References

### Existing Code to Reference

- **TUI Event Display**: `src/supsrc/events/feed_table/widget.py`
- **Event Formatters**: `src/supsrc/events/feed_table/formatters.py`
- **JSON Logger**: `src/supsrc/events/json_logger.py`
- **Event Collector**: `src/supsrc/events/collector.py`
- **Event Types**: `src/supsrc/events/*.py`
- **Orchestrator**: `src/supsrc/runtime/orchestrator.py`

### External Libraries

- **Rich**: Terminal formatting, color, layout
  - `Console` for output
  - `Table` for structured display
  - `Text` for styled text
  - `Live` for live refresh mode

- **Standard Library**:
  - `shutil.get_terminal_size()` for width detection
  - `signal.SIGWINCH` for resize handling
  - `collections.deque` for ring buffer

---

## Appendix: Example Output

### Standard Mode (Color + Emoji)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 Supsrc Watch - Event Stream Mode
📁 Monitoring: 3 repositories
📝 Event Log: /Users/tim/code/gh/provide-io/supsrc/.supsrc/local/logs/events.jsonl
📋 App Log: /tmp/supsrc_app.log
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[08:45:20] [my-project       ] [📋] [-  ] [-                ] [Monitoring started]
[08:45:23] [my-project       ] [📝] [1  ] [src/main.py      ] [File modified]
[08:45:24] [my-project       ] [📝] [2  ] [src/utils.py     ] [File modified]
[08:45:25] [my-project       ] [📝] [1  ] [tests/test.py    ] [File created]
[08:45:26] [my-project       ] [⏳] [3  ] [-                ] [Save count rule: 3/3]
[08:45:27] [my-project       ] [✅] [3  ] [3 files         ] [abc123f: "Add feature"]
[08:45:28] [my-project       ] [🚀] [3  ] [origin/main     ] [Pushed to remote]
[08:46:15] [another-repo     ] [📝] [5  ] [multiple files  ] [Batch: 5 files changed]
[08:46:17] [another-repo     ] [⏳] [5  ] [-                ] [Inactivity: 30/30s]
[08:46:18] [another-repo     ] [✅] [5  ] [5 files         ] [def456a: "Update deps"]
[08:47:30] [third-repo       ] [⚠️] [-  ] [-                ] [External commit detected]
[08:47:31] [third-repo       ] [🔄] [-  ] [-                ] [Refreshing status...]
[08:47:32] [third-repo       ] [❌] [-  ] [-                ] [ConflictError: Merge conflict]
[08:47:33] [third-repo       ] [🧊] [-  ] [-                ] [Repository frozen]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 STATUS: 2 active | 0 paused | 1 frozen | Queue: 0 | Last: 08:47:33
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 my-project: clean [main]
🟢 another-repo: clean [develop]
🔴 third-repo: frozen - merge conflict [feature/foo]
```

### Plain Mode (--no-color --ascii)

```
================================================================================
>> Supsrc Watch - Event Stream Mode
>> Monitoring: 3 repositories
>> Event Log: /Users/tim/code/gh/provide-io/supsrc/.supsrc/local/logs/events.jsonl
>> App Log: /tmp/supsrc_app.log
================================================================================

[08:45:20] [my-project       ] [>>] [-  ] [-                ] [Monitoring started]
[08:45:23] [my-project       ] [M ] [1  ] [src/main.py      ] [File modified]
[08:45:24] [my-project       ] [M ] [2  ] [src/utils.py     ] [File modified]
[08:45:25] [my-project       ] [A ] [1  ] [tests/test.py    ] [File created]
[08:45:26] [my-project       ] [T ] [3  ] [-                ] [Save count rule: 3/3]
[08:45:27] [my-project       ] [OK] [3  ] [3 files         ] [abc123f: "Add feature"]
[08:45:28] [my-project       ] [^^] [3  ] [origin/main     ] [Pushed to remote]
```

### Narrow Terminal (<80 chars)

```
[08:45:23] [my-proj] [📝] [File modified: src/main.py]
[08:45:24] [my-proj] [📝] [File modified: src/utils.py]
[08:45:27] [my-proj] [✅] [Committed 3 files]
```

---

## Timeline Summary

- **Week 1**: Core event display infrastructure
- **Week 2**: Colors, metadata, real-time streaming
- **Week 3**: Terminal responsiveness, batching, rate limiting
- **Week 4**: JSON correlation, advanced features, documentation

**Total Estimated Effort**: 4 weeks (160 hours)

---

## Conclusion

This plan transforms `supsrc watch` from a basic periodic status reporter into a rich, real-time event stream that rivals the TUI mode while maintaining compatibility with headless environments, scripting, and log aggregation systems.

The phased approach ensures incremental value delivery while maintaining code quality and test coverage throughout the implementation.
