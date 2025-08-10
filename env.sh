#!/bin/bash
#
# env.sh - Supsrc Development Environment Setup
#
# This script sets up a clean, isolated development environment for Supsrc
# using 'uv' for high-performance virtual environment and dependency management.
#
# Usage: source ./env.sh
#

# --- Configuration ---
COLOR_BLUE='\033[0;34m'
COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[0;33m'
COLOR_RED='\033[0;31m'
COLOR_NC='\033[0m'

# Spinner animation for long operations
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    while ps -p $pid > /dev/null 2>&1; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

print_header() {
    echo -e "\n${COLOR_BLUE}--- ${1} ---${COLOR_NC}"
}

print_success() {
    echo -e "${COLOR_GREEN}✅ ${1}${COLOR_NC}"
}

print_error() {
    echo -e "${COLOR_RED}❌ ${1}${COLOR_NC}"
}

print_warning() {
    echo -e "${COLOR_YELLOW}⚠️  ${1}${COLOR_NC}"
}

# --- Cleanup Previous Environment ---
print_header "🧹 Cleaning Previous Environment"

# Remove any existing Python aliases
unalias python 2>/dev/null
unalias python3 2>/dev/null
unalias pip 2>/dev/null
unalias pip3 2>/dev/null

# Clear existing PYTHONPATH
unset PYTHONPATH

# Store original PATH for restoration if needed
ORIGINAL_PATH="${PATH}"

print_success "Cleared Python aliases and PYTHONPATH"

# --- Project Validation ---
if [ ! -f "pyproject.toml" ]; then
    print_error "No 'pyproject.toml' found in current directory"
    echo "Please run this script from the Supsrc root directory"
    return 1 2>/dev/null || exit 1
fi

PROJECT_NAME=$(basename "$(pwd)")
if [ "$PROJECT_NAME" != "supsrc" ]; then
    print_warning "This script is optimized for Supsrc but running in '${PROJECT_NAME}'"
fi

# --- UV Installation ---
print_header "🚀 Checking UV Package Manager"

if ! command -v uv &> /dev/null; then
    echo "Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh > /tmp/uv_install.log 2>&1 &
    spinner $!
    
    UV_ENV_PATH_LOCAL="$HOME/.local/bin/env"
    UV_ENV_PATH_CARGO="$HOME/.cargo/env"
    
    if [ -f "$UV_ENV_PATH_LOCAL" ]; then
        source "$UV_ENV_PATH_LOCAL"
    elif [ -f "$UV_ENV_PATH_CARGO" ]; then
        source "$UV_ENV_PATH_CARGO"
    fi
    
    if command -v uv &> /dev/null; then
        print_success "UV installed successfully"
    else
        print_error "UV installation failed. Check /tmp/uv_install.log"
        return 1 2>/dev/null || exit 1
    fi
else
    print_success "UV already installed ($(uv --version))"
fi

# --- Platform Detection ---
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
esac

# Virtual environment directory
VENV_DIR=".venv_${OS}_${ARCH}"
export UV_PROJECT_ENVIRONMENT="${VENV_DIR}"

# --- Virtual Environment ---
print_header "🐍 Setting Up Virtual Environment"
echo "Directory: ${VENV_DIR}"

if [ -d "${VENV_DIR}" ] && [ -f "${VENV_DIR}/bin/activate" ] && [ -f "${VENV_DIR}/bin/python" ]; then
    print_success "Virtual environment exists"
else
    echo -n "Creating virtual environment..."
    uv venv "${VENV_DIR}" --python 3.11 > /tmp/uv_venv.log 2>&1 &
    spinner $!
    print_success "Virtual environment created"
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"
export VIRTUAL_ENV="$(pwd)/${VENV_DIR}"

# --- Dependency Installation ---
print_header "📦 Installing Dependencies"

# Create log directory
mkdir -p /tmp/supsrc_setup

echo -n "Syncing dependencies..."
uv sync --all-extras > /tmp/supsrc_setup/sync.log 2>&1 &
SYNC_PID=$!
spinner $SYNC_PID
wait $SYNC_PID
if [ $? -eq 0 ]; then
    print_success "Dependencies synced"
else
    print_error "Dependency sync failed. Check /tmp/supsrc_setup/sync.log"
    return 1 2>/dev/null || exit 1
fi

echo -n "Installing Supsrc in editable mode..."
uv pip install --no-deps -e . > /tmp/supsrc_setup/install.log 2>&1 &
spinner $!
print_success "Supsrc installed"

# --- Development Tools ---
print_header "🛠️ Installing Development Tools"

DEV_TOOLS=(
    "mypy"
    "bandit"
    "ruff"
    "pytest"
    "pytest-cov"
    "pytest-asyncio"
    "pytest-xdist"
)

for tool in "${DEV_TOOLS[@]}"; do
    if ! "${VENV_DIR}/bin/pip" show "$tool" > /dev/null 2>&1; then
        echo -n "Installing ${tool}..."
        uv pip install "$tool" > /tmp/supsrc_setup/${tool}.log 2>&1 &
        spinner $!
        print_success "${tool} installed"
    fi
done

# --- Environment Configuration ---
print_header "🔧 Configuring Environment"

# Set clean PYTHONPATH
export PYTHONPATH="${PWD}/src:${PWD}"
echo "PYTHONPATH: ${PYTHONPATH}"

# Clean up PATH - remove duplicates
NEW_PATH="${VENV_DIR}/bin"
OLD_IFS="$IFS"
IFS=':'
for p in $PATH; do
    case ":$NEW_PATH:" in
        *":$p:"*) ;;
        *) NEW_PATH="$NEW_PATH:$p" ;;
    esac
done
IFS="$OLD_IFS"
export PATH="$NEW_PATH"

# --- Tool Verification ---
print_header "🔍 Verifying Installation"

echo -e "\n${COLOR_GREEN}Tool Locations & Versions:${COLOR_NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# UV
if command -v uv &> /dev/null; then
    UV_PATH=$(command -v uv 2>/dev/null || which uv 2>/dev/null || echo "uv")
    printf "%-12s: %s\n" "UV" "$UV_PATH"
    printf "%-12s  %s\n" "" "$(uv --version 2>/dev/null || echo "not found")"
fi

# Python
PYTHON_PATH="${VENV_DIR}/bin/python"
if [ -f "$PYTHON_PATH" ]; then
    printf "%-12s: %s\n" "Python" "$PYTHON_PATH"
    printf "%-12s  %s\n" "" "$($PYTHON_PATH --version 2>&1)"
fi

# Supsrc
SUPSRC_PATH="${VENV_DIR}/bin/supsrc"
if [ -f "$SUPSRC_PATH" ]; then
    printf "%-12s: %s\n" "Supsrc" "$SUPSRC_PATH"
    SUPSRC_VERSION=$($SUPSRC_PATH --version 2>&1 | head -n1)
    printf "%-12s  %s\n" "" "$SUPSRC_VERSION"
fi

# Pytest
PYTEST_PATH="${VENV_DIR}/bin/pytest"
if [ -f "$PYTEST_PATH" ]; then
    printf "%-12s: %s\n" "Pytest" "$PYTEST_PATH"
    PYTEST_VERSION=$($PYTEST_PATH --version 2>&1 | head -n1)
    printf "%-12s  %s\n" "" "$PYTEST_VERSION"
fi

# Ruff
RUFF_PATH="${VENV_DIR}/bin/ruff"
if [ -f "$RUFF_PATH" ]; then
    printf "%-12s: %s\n" "Ruff" "$RUFF_PATH"
    RUFF_VERSION=$($RUFF_PATH --version 2>&1)
    printf "%-12s  %s\n" "" "$RUFF_VERSION"
fi

# MyPy
MYPY_PATH="${VENV_DIR}/bin/mypy"
if [ -f "$MYPY_PATH" ]; then
    printf "%-12s: %s\n" "MyPy" "$MYPY_PATH"
    MYPY_VERSION=$($MYPY_PATH --version 2>&1)
    printf "%-12s  %s\n" "" "$MYPY_VERSION"
fi

# Bandit
BANDIT_PATH="${VENV_DIR}/bin/bandit"
if [ -f "$BANDIT_PATH" ]; then
    printf "%-12s: %s\n" "Bandit" "$BANDIT_PATH"
    BANDIT_VERSION=$($BANDIT_PATH --version 2>&1 | grep -i bandit | head -n1)
    printf "%-12s  %s\n" "" "$BANDIT_VERSION"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# --- Final Summary ---
print_header "✅ Environment Ready!"

echo -e "\n${COLOR_GREEN}Supsrc development environment activated${COLOR_NC}"
echo "Virtual environment: ${VENV_DIR}"
echo -e "\nUseful commands:"
echo "  supsrc --help     # Supsrc CLI"
echo "  supsrc watch      # Interactive TUI mode"
echo "  supsrc tail       # Non-interactive mode"
echo "  pytest            # Run tests"
echo "  ruff format .     # Format code"
echo "  ruff check .      # Lint code"
echo "  mypy src/         # Type check"
echo "  bandit -r src/    # Security scan"
echo "  deactivate        # Exit environment"

# --- Cleanup ---
# Remove temporary log files older than 1 day
find /tmp/supsrc_setup -name "*.log" -mtime +1 -delete 2>/dev/null

# Return success
return 0 2>/dev/null || exit 0


# 🔼⚙️