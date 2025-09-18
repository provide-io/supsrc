# Supsrc Testing Examples

This directory contains comprehensive testing tools and configurations for the supsrc TUI and monitoring system.

## Quick Start

### 1. Setup Test Repositories

Create test repositories with realistic file structures:

```bash
# Create 5 repositories (default)
./setup_examples.sh

# Create a custom number of repositories
./setup_examples.sh 10
```

### 2. Run TUI Tests with Output Redirection

Use the enhanced test runner to prevent terminal corruption:

```bash
# Run test with 5 repositories for 60 seconds
./test_tui.sh 5 60

# Quick test with 3 repositories for 30 seconds
./test_tui.sh 3 30
```

### 3. Monitor and Debug

Use the debug monitor to analyze what's happening:

```bash
# Monitor the latest test run
./debug_monitor.sh

# Monitor a specific log directory
./debug_monitor.sh /tmp/supsrc_logs_20241218_143022
```

## Files Overview

### Scripts

- **`setup_examples.sh`** - Enhanced repository setup script
  - Creates configurable number of test repositories
  - Adds realistic Python files, configs, and test data
  - Each repository has different content and structure

- **`test_tui.sh`** - Comprehensive TUI test runner
  - Redirects output to prevent terminal corruption
  - Creates detailed log files for analysis
  - Includes file change simulation
  - Configurable timeout and repository count

- **`debug_monitor.sh`** - Interactive debug tool
  - Real-time log monitoring with color coding
  - Repository status checking
  - Error analysis and reporting
  - Log file analysis with statistics

### Configuration Files

- **`supsrc_test.conf`** - Enhanced test configuration
  - Multiple repositories with staggered timers (5s, 7s, 10s, etc.)
  - Debug logging enabled
  - Different commit message templates
  - Mixed auto-push settings for comprehensive testing

- **`supsrc.conf`** - Original simple configuration (3 repositories)

## Test Repository Structure

Each test repository created by `setup_examples.sh` contains:

```
/tmp/supsrc-example-repo{N}/
├── README.md              # Repository documentation
├── app.py                 # Main Python application
├── utils.py               # Utility functions
├── config.yaml           # Configuration file
├── .gitignore            # Git ignore patterns
├── data/                 # Sample data directory
│   ├── sample.json       # JSON data
│   ├── test.csv          # CSV data
│   └── sample.txt        # Text data
└── tests/                # Unit tests
    └── test_app.py       # Test file
```

## Testing Workflow

### 1. Comprehensive Testing

```bash
# Setup 8 repositories for comprehensive testing
./setup_examples.sh 8

# Run extended test session
./test_tui.sh 8 120

# Monitor logs in real-time (in another terminal)
./debug_monitor.sh
```

### 2. Quick Testing

```bash
# Setup minimal test environment
./setup_examples.sh 3

# Quick 30-second test
./test_tui.sh 3 30
```

### 3. Cursor Jumping Investigation

```bash
# Setup repositories with fast timers
./setup_examples.sh 5

# Run test and monitor for cursor jumping
./test_tui.sh 5 60

# In another terminal, watch for cursor jumping patterns
./debug_monitor.sh
# Choose option 3 for real-time monitoring
```

## Log Files

When you run `test_tui.sh`, logs are saved in `/tmp/supsrc_logs_TIMESTAMP/`:

- **`supsrc_main.log`** - Main application output
- **`supsrc_error.log`** - Error messages and exceptions
- **`foundation.log`** - Foundation framework logs
- **`tui_debug.log`** - TUI-specific debug information
- **`changes.log`** - File change simulation log
- **`debug_report.txt`** - Generated analysis report

## File Change Simulation

The test runner includes automatic file change simulation:

- Modifies Python files, configs, and data files
- Creates new test files
- Simulates realistic development workflow
- Configurable change intervals (default: 10 seconds)

## Debugging Features

### Debug Monitor Options

1. **Log Analysis** - Shows line counts, errors, warnings for each log file
2. **Repository Status** - Git status, commit counts, recent changes
3. **Real-time Monitoring** - Color-coded live log streaming
4. **Debug Report** - Comprehensive analysis saved to file
5. **Error Focus** - Shows only recent errors across all logs

### Color Coding

- 🔴 **Red**: Errors and critical issues
- 🟡 **Yellow**: Warnings
- 🟢 **Green**: Info messages and successful operations
- 🔵 **Cyan**: Debug messages
- 🟣 **Magenta**: Critical/fatal errors

## Common Issues and Solutions

### Terminal Corruption

**Problem**: Running supsrc TUI directly corrupts the terminal
**Solution**: Always use `test_tui.sh` which redirects output properly

### Cursor Jumping

**Problem**: Cursor jumps when navigating to bottom of repository list
**Solution**: Use the debug monitor to track state update patterns:

```bash
./debug_monitor.sh
# Choose option 3 for real-time monitoring
# Look for StateUpdate messages and row removal/addition patterns
```

### Log Analysis

**Problem**: Need to understand what's happening during monitoring
**Solution**: Use log analysis features:

```bash
./debug_monitor.sh
# Choose option 1 for log analysis
# Choose option 4 to generate comprehensive report
```

## Environment Variables

You can customize behavior with environment variables:

```bash
export SUPSRC_LOG_LEVEL="DEBUG"
export SUPSRC_DEFAULT_COMMIT_MESSAGE="Custom commit message"
export SUPSRC_DEFAULT_AUTO_PUSH="true"

./test_tui.sh 5 60
```

## Advanced Usage

### Custom Test Scenarios

```bash
# Test with many repositories and long runtime
./setup_examples.sh 15
./test_tui.sh 15 300  # 5 minutes

# Test with fast changes
./setup_examples.sh 5
# Edit the change interval in test_tui.sh to 5 seconds
./test_tui.sh 5 60
```

### Manual Testing

```bash
# Setup repositories
./setup_examples.sh 5

# Run manually with custom config
cd ..  # Go back to project root
PYTHONPATH="../provide-foundation/src:./workenv/wrkenv_darwin_arm64/lib/python3.11/site-packages:./src" \
python -m supsrc.cli.main sui -c examples/supsrc_test.conf \
  > /tmp/manual_test.log 2>&1 &

# Monitor in another terminal
tail -f /tmp/manual_test.log
```

## Troubleshooting

### No Repositories Loading

1. Check repository paths exist: `ls /tmp/supsrc-example-repo*`
2. Verify configuration: `cat supsrc_test.conf`
3. Check logs for setup errors: `./debug_monitor.sh`

### TUI Not Starting

1. Check Python path and dependencies
2. Verify configuration file syntax
3. Check error logs: `./debug_monitor.sh` → option 5

### File Changes Not Detected

1. Verify file change simulation is running
2. Check repository paths in config
3. Monitor change logs: `tail -f /tmp/supsrc_logs_*/changes.log`

## Contributing

When adding new test scenarios or debugging features:

1. Update this README with new functionality
2. Add clear usage examples
3. Include troubleshooting information
4. Test with various repository counts (3, 5, 8, 15)

## Tips

- Use `./debug_monitor.sh` option 3 for real-time monitoring during cursor jumping investigation
- Repository timers are staggered (5s, 7s, 10s, etc.) to create varied testing conditions
- The file change simulator creates realistic workflow patterns
- Log files are timestamped and preserved for historical analysis
- Color coding in real-time monitoring helps identify issues quickly
