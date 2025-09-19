#!/bin/bash

# Enhanced TUI test runner with output redirection to prevent terminal corruption
# Usage: ./test_tui.sh [number_of_repos] [timeout_seconds]

NUM_REPOS=${1:-5}
TIMEOUT=${2:-60}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create log directory
LOG_DIR="/tmp/supsrc_logs_${TIMESTAMP}"
mkdir -p "${LOG_DIR}"

echo "================================================================================"
echo "🧪 Starting supsrc TUI test with ${NUM_REPOS} repositories"
echo "================================================================================"

# Setup repositories if they don't exist
echo "📁 Setting up ${NUM_REPOS} test repositories..."
./setup_examples.sh ${NUM_REPOS}

# Create test configuration
echo "⚙️ Creating test configuration..."
cat > supsrc_test.conf << EOF
[global]
log_level = "DEBUG"
# Enable more verbose logging for testing

[repositories]
EOF

# Add repositories to config with different timer settings
for i in $(seq 1 ${NUM_REPOS}); do
    timer_seconds=$((3 + i * 2))  # Staggered timers: 5s, 7s, 9s, 11s, etc.
    cat >> supsrc_test.conf << EOF

  [repositories.example-repo-${i}]
    path = "/tmp/supsrc-example-repo${i}"
    enabled = true

    [repositories.example-repo-${i}.rule]
      type = "supsrc.rules.inactivity"
      period = "${timer_seconds}s"

    [repositories.example-repo-${i}.repository]
      type = "supsrc.engines.git"
      auto_push = false
      commit_message_template = "Auto-commit repo${i} [{{save_count}}]: {{change_summary}} ({{timestamp}})"
EOF
done

# Define log files
MAIN_LOG="${LOG_DIR}/supsrc_main.log"
ERROR_LOG="${LOG_DIR}/supsrc_error.log"
FOUNDATION_LOG="${LOG_DIR}/foundation.log"
TUI_LOG="${LOG_DIR}/tui_debug.log"

echo ""
echo "📋 Log files will be created in: ${LOG_DIR}"
echo "   - Main output: ${MAIN_LOG}"
echo "   - Error output: ${ERROR_LOG}"
echo "   - Foundation logs: ${FOUNDATION_LOG}"
echo "   - TUI debug: ${TUI_LOG}"
echo ""

# Create file change simulator script
cat > "${LOG_DIR}/simulate_changes.sh" << 'EOF'
#!/bin/bash
# Script to simulate file changes in test repositories

NUM_REPOS=${1:-5}
CHANGE_INTERVAL=${2:-15}

echo "Starting file change simulation for ${NUM_REPOS} repositories every ${CHANGE_INTERVAL}s"

count=1
while true; do
    repo_num=$((RANDOM % NUM_REPOS + 1))
    repo_dir="/tmp/supsrc-example-repo${repo_num}"

    if [ -d "${repo_dir}" ]; then
        cd "${repo_dir}"

        # Randomly choose what to modify
        case $((RANDOM % 4)) in
            0)
                # Modify Python file
                echo "# Modified at $(date)" >> app.py
                echo "📝 Modified app.py in repo ${repo_num}"
                ;;
            1)
                # Add new file
                echo "Test content $(date)" > "test_${count}.txt"
                echo "➕ Added test_${count}.txt in repo ${repo_num}"
                ;;
            2)
                # Modify config
                echo "# Config change $(date)" >> config.yaml
                echo "⚙️ Modified config.yaml in repo ${repo_num}"
                ;;
            3)
                # Modify data file
                echo "$(date),change,${count}" >> data/test.csv
                echo "📊 Modified data/test.csv in repo ${repo_num}"
                ;;
        esac

        count=$((count + 1))
    fi

    sleep ${CHANGE_INTERVAL}
done
EOF

chmod +x "${LOG_DIR}/simulate_changes.sh"

# Start the TUI with output redirection
echo "🚀 Starting supsrc TUI (timeout: ${TIMEOUT}s)..."
echo "   Press Ctrl+C to stop early"
echo "   Use 'tail -f ${MAIN_LOG}' in another terminal to monitor"
echo ""

# Export environment for better logging
export PYTHONPATH="../provide-foundation/src:./workenv/wrkenv_darwin_arm64/lib/python3.11/site-packages:./src"
export SUPSRC_LOG_LEVEL="DEBUG"

# Start TUI in background with output redirection
timeout ${TIMEOUT}s python -m supsrc.cli.main sui -c supsrc_test.conf \
    > "${MAIN_LOG}" 2> "${ERROR_LOG}" &

TUI_PID=$!

echo "TUI started with PID: ${TUI_PID}"
echo "Logs are being written to ${LOG_DIR}/"

# Start file change simulator in background
"${LOG_DIR}/simulate_changes.sh" ${NUM_REPOS} 10 > "${LOG_DIR}/changes.log" 2>&1 &
SIMULATOR_PID=$!

echo "File change simulator started with PID: ${SIMULATOR_PID}"

# Monitor function
monitor_logs() {
    echo ""
    echo "📊 Monitoring logs (Ctrl+C to stop)..."
    echo "================================================================================"

    # Use tail to follow multiple log files
    tail -f "${MAIN_LOG}" "${ERROR_LOG}" "${LOG_DIR}/changes.log" 2>/dev/null &
    TAIL_PID=$!

    # Wait for user interrupt or timeout
    wait ${TUI_PID} 2>/dev/null

    # Cleanup
    kill ${TAIL_PID} 2>/dev/null
    kill ${SIMULATOR_PID} 2>/dev/null

    # Reset terminal mouse tracking modes that may be left enabled by TUI
    printf '\e[?1000l\e[?1002l\e[?1003l\e[?10061l'
    echo "🔄 Terminal reset complete"

    echo ""
    echo "================================================================================"
    echo "🏁 Test completed!"
    echo ""
    echo "📋 Log summary:"
    echo "   Main log lines: $(wc -l < "${MAIN_LOG}" 2>/dev/null || echo "0")"
    echo "   Error log lines: $(wc -l < "${ERROR_LOG}" 2>/dev/null || echo "0")"
    echo "   Changes simulated: $(wc -l < "${LOG_DIR}/changes.log" 2>/dev/null || echo "0")"
    echo ""
    echo "🔍 To analyze results:"
    echo "   less ${MAIN_LOG}     # View main output"
    echo "   less ${ERROR_LOG}    # View errors"
    echo "   ./debug_monitor.sh ${LOG_DIR}  # Analyze with debug tools"
    echo ""
    echo "📁 All logs saved in: ${LOG_DIR}"
}

# Handle cleanup on script exit
cleanup() {
    echo ""
    echo "🛑 Cleaning up..."
    kill ${TUI_PID} 2>/dev/null
    kill ${SIMULATOR_PID} 2>/dev/null
    kill ${TAIL_PID} 2>/dev/null

    # Reset terminal mouse tracking modes that may be left enabled by TUI
    printf '\e[?1000l\e[?1002l\e[?1003l\e[?10061l'
    echo "🔄 Terminal reset complete"

    exit 0
}

trap cleanup INT TERM

# Start monitoring
monitor_logs