# SupSrc Documentation

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

For complete API documentation, see the [API Reference](api/).

## Core Features

- **Git Operations**: Advanced Git workflow automation
- **Commit Intelligence**: AI-powered commit analysis and generation
- **TUI**: Rich terminal user interface
- **Analysis**: Code change impact assessment