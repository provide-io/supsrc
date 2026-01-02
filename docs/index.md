# SupSrc Documentation

!!! warning "Pre-release"
    This documentation covers a pre-release. APIs and features may change, and some documented or roadmap items are exploratory and may change or be removed.


Welcome to SupSrc - Automated Git workflow and commit management for intelligent source code operations.

## Features

SupSrc provides:

- **Intelligent Commits**: AI-powered commit message generation and optimization
- **Workflow Automation**: Automated Git workflows and branch management
- **Code Analysis**: Smart analysis of code changes and impact assessment
- **Integration Tools**: Seamless integration with CI/CD and development tools
- **History Management**: Advanced Git history analysis and manipulation
- **Terminal UI**: Rich terminal interface for interactive Git operations

## Quick Start

### Installation

<div class="termy">

```console
$ pip install supsrc
// Installing supsrc...
Successfully installed supsrc

$ supsrc --version
supsrc, version 0.1.0
```

</div>

### Watch a Repository

<div class="termy">

```console
$ supsrc watch
// Starting repository monitoring...
✓ Watching: /home/user/my-project
✓ Auto-commit enabled (after 60s inactivity)
✓ Auto-push enabled

Monitoring repository for changes...
Press Ctrl+C to stop
```

</div>

### Interactive Terminal UI

<div class="termy">

```console
$ supsrc sui
// Launching terminal UI...

╭─────────────────────────────────────────────────╮
│ SupSrc - Git Workflow Manager                  │
├─────────────────────────────────────────────────┤
│ Repository: my-project                          │
│ Branch: main                                    │
│ Status: ✓ Clean                                 │
│                                                 │
│ Recent Activity:                                │
│  ✓ 15:32 - Auto-committed 3 files              │
│  ✓ 15:30 - Pushed to origin/main               │
│  ✓ 15:28 - Auto-committed 1 file               │
│                                                 │
│ [W]atch [C]ommit [P]ush [Q]uit                │
╰─────────────────────────────────────────────────╯
```

</div>

### Configure Workflow Rules

<div class="termy">

```console
$ supsrc config show
// Loading configuration...

Repository Rules:
  Inactivity timeout: 60s
  Save count trigger: 5 saves
  Auto-push: enabled
  Commit template: "chore: {summary}"

Branch Protection:
  main: protected (no auto-push)
  develop: auto-push enabled

$ supsrc config set inactivity-timeout 120
✓ Configuration updated
```

</div>

### Manual Commit Operations

<div class="termy">

```console
$ supsrc commit --analyze
// Analyzing changes...
Found 3 modified files:
  - src/api/routes.py (15 lines added)
  - tests/test_api.py (8 lines added)
  - docs/README.md (2 lines changed)

Suggested commit message:
  "feat: add new API routes with tests"

Commit with this message? [Y/n] y
// Creating commit...
✓ Committed successfully
✓ Pushed to origin/main
```

</div>

### Python API Usage

```python
from supsrc import GitManager, CommitAnalyzer

# Analyze and create intelligent commits
git = GitManager()
analyzer = CommitAnalyzer()

# Generate smart commit messages
changes = git.get_staged_changes()
message = analyzer.generate_message(changes)
git.commit(message)
```

## API Reference

For complete API documentation, see the [API Reference](api/index/).

## Core Features

- **Git Operations**: Advanced Git workflow automation
- **Commit Intelligence**: AI-powered commit analysis and generation
- **TUI**: Rich terminal user interface
- **Analysis**: Code change impact assessment
