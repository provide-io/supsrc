#!/bin/bash
#
# env.sh - Supsrc Development Environment Setup
#
# This script sets up a clean, isolated development environment for Supsrc
# using 'wrkenv' to manage tool versions.
#
# Usage: source ./env.sh
#

# --- Configuration ---
COLOR_BLUE='\033[0;34m'
COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_NC='\033[0m'

print_header() {
    echo -e "\n${COLOR_BLUE}--- ${1} ---
${COLOR_NC}"
}

print_success() {
    echo -e "${COLOR_GREEN}✅ ${1}${COLOR_NC}"
}

print_error() {
    echo -e "${COLOR_RED}❌ ${1}${COLOR_NC}"
}

# --- wrkenv Installation ---
print_header "🚀 Checking wrkenv"

if ! command -v wrkenv &> /dev/null; then
    print_error "wrkenv not found."
    echo "Please install wrkenv to continue:"
    echo "  pip install wrkenv"
    return 1 2>/dev/null || exit 1
else
    print_success "wrkenv already installed ($(wrkenv --version))"
fi

# --- Environment Setup ---
print_header "🛠️ Setting Up Environment"

if [ ! -f "wrkenv.toml" ]; then
    print_error "No 'wrkenv.toml' found in current directory"
    echo "Please create a wrkenv.toml file to define the required tools."
    return 1 2>/dev/null || exit 1
fi

echo -n "Installing tools with wrkenv..."
wrkenv install > /tmp/wrkenv_install.log 2>&1 & 
spinner $!

if [ $? -eq 0 ]; then
    print_success "Tools installed successfully"
else
    print_error "wrkenv install failed. Check /tmp/wrkenv_install.log"
    return 1 2>/dev/null || exit 1
fi

# --- Activate Environment ---
print_header "엑 Setting Up Environment"

eval $(wrkenv env)

print_success "wrkenv environment activated"

# --- Final Summary ---
print_header "✅ Environment Ready!"

echo -e "\n${COLOR_GREEN}Supsrc development environment activated${COLOR_NC}"
echo "wrkenv is managing your tool versions."
