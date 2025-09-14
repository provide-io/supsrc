#!/bin/bash
# workenv/env.sh - Standardized UV and virtual environment setup
#
# This script provides a standardized way to set up development environments
# across the provide.io ecosystem while wrknv is in development.

set -e

# Check if UV is installed
if ! command -v uv &> /dev/null; then
    echo "UV not found. Installing UV..."
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        # Windows
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    else
        # macOS and Linux
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi

    # Add UV to PATH for this session
    export PATH="$HOME/.cargo/bin:$PATH"

    # Verify installation
    if ! command -v uv &> /dev/null; then
        echo "Error: UV installation failed" >&2
        exit 1
    fi

    echo "UV installed successfully"
fi

# Get the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Navigate to project root (parent of workenv directory)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Check if .venv directory exists
if [[ -d ".venv" ]]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
    echo "Virtual environment activated: $VIRTUAL_ENV"
else
    echo "No .venv directory found in $PROJECT_ROOT"
    echo "Run 'uv venv' to create a virtual environment first"
    exit 1
fi