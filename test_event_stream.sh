#!/usr/bin/env bash
# Test script for headless event stream output
# Generates various file events to test the console formatter

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🧪 Supsrc Event Stream Test Generator${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Create test directory
TEST_DIR="/tmp/supsrc_event_test"
echo -e "${YELLOW}📁 Setting up test directory: ${TEST_DIR}${NC}"
rm -rf "${TEST_DIR}"
mkdir -p "${TEST_DIR}/src"
mkdir -p "${TEST_DIR}/tests"
mkdir -p "${TEST_DIR}/docs"

cd "${TEST_DIR}"

# Initialize git repository
echo -e "${YELLOW}🔧 Initializing git repository...${NC}"
git init -q
git config user.name "Event Tester"
git config user.email "test@supsrc.local"

# Create initial commit
echo "# Event Stream Test" > README.md
git add README.md
git commit -q -m "Initial commit"

# Create supsrc configuration
echo -e "${YELLOW}⚙️  Creating supsrc configuration...${NC}"
cat > supsrc.conf <<EOF
[repositories.test-repo]
path = "${TEST_DIR}"
enabled = true

[repositories.test-repo.rule]
type = "inactivity"

[repositories.test-repo.rule.inactivity]
enabled = true
seconds = 5

[repositories.test-repo.actions]
commit = true
push = false

[repositories.test-repo.commit]
message_template = "🔼⚙️ Auto-commit: {file_count} files changed"
EOF

echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"
echo -e "${YELLOW}📍 Working directory: ${TEST_DIR}${NC}"
echo ""

# Start supsrc watch in background
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🚀 Starting supsrc watch in background...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Kill any existing supsrc watch processes
pkill -f "supsrc watch" 2>/dev/null || true
sleep 1

# Start watch in background and redirect output
uv run supsrc watch -c supsrc.conf 2>&1 &
WATCH_PID=$!
echo -e "${YELLOW}💫 Watch process started (PID: ${WATCH_PID})${NC}"
echo ""

# Wait for watch to initialize
sleep 3

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📝 Generating file events...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Event 1: Create new Python file
echo -e "${YELLOW}[Event 1] Creating new Python file: src/main.py${NC}"
cat > src/main.py <<EOF
def main():
    print("Hello, world!")

if __name__ == "__main__":
    main()
EOF
sleep 2

# Event 2: Create test file
echo -e "${YELLOW}[Event 2] Creating test file: tests/test_main.py${NC}"
cat > tests/test_main.py <<EOF
import pytest

def test_main():
    assert True
EOF
sleep 2

# Event 3: Modify existing file
echo -e "${YELLOW}[Event 3] Modifying src/main.py${NC}"
cat >> src/main.py <<EOF

def helper():
    return "Helper function"
EOF
sleep 2

# Event 4: Create multiple files rapidly
echo -e "${YELLOW}[Event 4] Creating multiple files rapidly (batch test)${NC}"
echo "# Utils" > src/utils.py
echo "# Config" > src/config.py
echo "# Database" > src/database.py
sleep 1

# Event 5: Create documentation
echo -e "${YELLOW}[Event 5] Creating documentation: docs/api.md${NC}"
cat > docs/api.md <<EOF
# API Documentation

## Functions

- \`main()\`: Entry point
- \`helper()\`: Helper function
EOF
sleep 2

# Event 6: Modify multiple files
echo -e "${YELLOW}[Event 6] Modifying multiple files${NC}"
echo "# Updated" >> src/utils.py
echo "# Updated" >> src/config.py
sleep 2

# Event 7: Create and delete file
echo -e "${YELLOW}[Event 7] Create and delete temporary file${NC}"
echo "temp" > temp.txt
sleep 1
rm temp.txt
sleep 2

# Event 8: Wait for inactivity rule to trigger
echo -e "${YELLOW}[Event 8] Waiting for inactivity rule (5 seconds)...${NC}"
sleep 6

# Event 9: More modifications after auto-commit
echo -e "${YELLOW}[Event 9] Post-commit modifications${NC}"
echo "# Post-commit change" >> README.md
sleep 2

# Event 10: Final batch of changes
echo -e "${YELLOW}[Event 10] Final batch of changes${NC}"
echo "version = '1.0.0'" > src/version.py
cat >> README.md <<EOF

## Features
- Event stream testing
- Auto-commit functionality
EOF
sleep 3

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Event generation complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Wait a bit more for final events to process
echo -e "${YELLOW}⏳ Waiting for final events to process (5 seconds)...${NC}"
sleep 5

# Show summary
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📊 Test Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Git commits created:${NC}"
git log --oneline --color=always | head -5
echo ""
echo -e "${YELLOW}Files in repository:${NC}"
find . -type f -not -path './.git/*' -not -name 'supsrc.conf' | sort
echo ""
echo -e "${YELLOW}Event log location:${NC} .supsrc/local/logs/events.jsonl"
if [ -f .supsrc/local/logs/events.jsonl ]; then
    EVENT_COUNT=$(wc -l < .supsrc/local/logs/events.jsonl)
    echo -e "${GREEN}✓ ${EVENT_COUNT} events logged${NC}"
fi
echo ""

# Kill watch process
echo -e "${YELLOW}🛑 Stopping watch process...${NC}"
kill ${WATCH_PID} 2>/dev/null || true
sleep 1

# Reset terminal
printf '\e[?1000l\e[?1002l\e[?1003l\e[?1006l'

echo ""
echo -e "${GREEN}🎉 Test complete!${NC}"
echo -e "${YELLOW}💡 Test directory preserved at: ${TEST_DIR}${NC}"
echo -e "${YELLOW}💡 To run again: cd ${TEST_DIR} && uv run supsrc watch -c supsrc.conf${NC}"
echo ""
