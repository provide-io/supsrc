#!/bin/bash

# Enhanced setup script for supsrc example repositories
# Usage: ./setup_examples.sh [number_of_repos]

NUM_REPOS=${1:-3}  # Default to 3 repositories if no argument provided
PWD=$(pwd)
repo_prefix=/tmp/supsrc-example-repo

echo "================================================================================"
echo "🚀 Setting up ${NUM_REPOS} example repositories for supsrc testing"
echo "================================================================================"

for i in $(seq 1 ${NUM_REPOS}); do (
    repo_dir=${repo_prefix}${i}
    echo ""
    echo "================================================================================"
    echo "🗄️ Repository ${i}/${NUM_REPOS}: ${repo_dir}"
    echo "================================================================================"

    echo "${repo_dir}: removing existing example repos."
    # Safer removal - check if it's a git repo first
    if [ -d "${repo_dir}/.git" ]; then
        rm -rf "${repo_dir}"
    elif [ -d "${repo_dir}" ]; then
        echo "Warning: ${repo_dir} exists but is not a git repo, removing anyway"
        rm -rf "${repo_dir}"
    fi

    echo "--------------------------------------------------------------------------------"
    echo "🎬 ${repo_dir}: init repo"
    echo "--------------------------------------------------------------------------------"
    mkdir -p ${repo_dir}
    cd ${repo_dir}
    git init .

    # Configure Git user for examples (disable GPG signing to avoid issues)
    git config user.name "Example Bot ${i}"
    git config user.email "example${i}@supsrc.example.com"
    # Disable GPG signing to prevent examples from failing if user has global GPG config
    git config commit.gpgsign false
    git config gpg.program ""

    echo "--------------------------------------------------------------------------------"
    echo "📝 ${repo_dir}: create realistic test files"
    echo "--------------------------------------------------------------------------------"

    # Create README
    cat > README.md << EOF
# Example Repository ${i}

This is test repository ${i} for supsrc monitoring.

Created: $(date)

## Files

- \`app.py\` - Main application file
- \`config.yaml\` - Configuration file
- \`utils.py\` - Utility functions
- \`data/\` - Data directory with sample files
EOF

    # Create Python application file
    cat > app.py << 'EOF'
#!/usr/bin/env python3
"""
Example application for testing supsrc monitoring.
"""

import os
import sys
from pathlib import Path

def main():
    """Main application entry point."""
    print(f"Running example app from {Path.cwd()}")
    print(f"Python version: {sys.version}")
    print(f"Arguments: {sys.argv[1:]}")

if __name__ == "__main__":
    main()
EOF

    # Create utility file
    cat > utils.py << 'EOF'
"""Utility functions for the example application."""

import datetime
import json
from typing import Dict, Any

def get_timestamp() -> str:
    """Get current timestamp as ISO string."""
    return datetime.datetime.now().isoformat()

def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from file."""
    with open(config_path) as f:
        return json.load(f)

def log_message(message: str, level: str = "INFO") -> None:
    """Log a message with timestamp."""
    timestamp = get_timestamp()
    print(f"[{timestamp}] {level}: {message}")
EOF

    # Create configuration file
    cat > config.yaml << EOF
app:
  name: "Example App ${i}"
  version: "1.0.0"
  debug: true

database:
  url: "sqlite:///example${i}.db"
  pool_size: 5

logging:
  level: "DEBUG"
  file: "app${i}.log"

features:
  monitoring: true
  auto_commit: true
  timer_seconds: $((3 + i * 2))
EOF

    # Create .gitignore
    cat > .gitignore << EOF
# Python
__pycache__/
*.py[cod]
*.so
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db

# Test files
test_*.txt
*.tmp
EOF

    # Create data directory with sample files
    mkdir -p data
    echo '{"sample": "data", "repo": '${i}', "created": "'$(date -Iseconds)'"}' > data/sample.json
    echo -e "name,value,timestamp\ntest1,100,$(date -Iseconds)\ntest2,200,$(date -Iseconds)" > data/test.csv
    echo "This is a sample text file for repository ${i}" > data/sample.txt

    # Create test directory
    mkdir -p tests
    cat > tests/test_app.py << 'EOF'
"""Tests for the example application."""

import unittest
from app import main

class TestApp(unittest.TestCase):
    """Test cases for the main application."""

    def test_main_function_exists(self):
        """Test that main function exists."""
        self.assertTrue(callable(main))

    def test_main_runs_without_error(self):
        """Test that main function runs without error."""
        try:
            main()
        except Exception as e:
            self.fail(f"main() raised {e} unexpectedly!")

if __name__ == "__main__":
    unittest.main()
EOF

    echo "--------------------------------------------------------------------------------"
    echo "1️⃣ ${repo_dir}: create first commit"
    echo "--------------------------------------------------------------------------------"
    git add .
    git commit -m "Initial commit for example repository ${i}

- Added Python application files
- Added configuration and test files
- Added sample data files
- Created: $(date)"

    echo "--------------------------------------------------------------------------------"
    echo "🔗 ${repo_dir}: create fake origin"
    echo "--------------------------------------------------------------------------------"
    git init --bare ${repo_dir}/.git/origin
    git remote add origin ${repo_dir}/.git/origin
    git push --set-upstream origin main

    echo "✅ Repository ${i} setup complete"
    echo
); done

cat<<EOF

================================================================================"
✅ Setup complete! Created ${NUM_REPOS} example repositories
================================================================================"

📁 Repositories created in /tmp/supsrc-example-repo{1..${NUM_REPOS}}

Each repository contains:
  - README.md - Documentation
  - app.py - Main Python application
  - utils.py - Utility functions
  - config.yaml - Configuration file
  - .gitignore - Git ignore patterns
  - data/ - Sample data files (JSON, CSV, TXT)
  - tests/ - Unit test files

🚀 To test with the TUI:

    # Use the enhanced test configuration
    ./test_tui.sh ${NUM_REPOS}

    # Or run manually with output redirection
    supsrc sui -c supsrc_test.conf > /tmp/supsrc_output.log 2>&1 &

⚠️  Running this script again will recreate all repositories

================================================================================"

EOF
