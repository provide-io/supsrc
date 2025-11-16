#!/bin/bash

# Debug monitoring script for supsrc testing
# Usage: ./debug_monitor.sh [log_directory]

LOG_DIR=${1:-"/tmp/supsrc_logs_latest"}

if [ ! -d "${LOG_DIR}" ]; then
    echo "❌ Log directory not found: ${LOG_DIR}"
    echo ""
    echo "Usage: $0 [log_directory]"
    echo ""
    echo "Available log directories:"
    ls -la /tmp/supsrc_logs_* 2>/dev/null || echo "No log directories found"
    exit 1
fi

echo "================================================================================"
echo "🔍 Supsrc Debug Monitor"
echo "================================================================================"
echo "📁 Monitoring logs in: ${LOG_DIR}"
echo ""

# Function to show colored log analysis
analyze_logs() {
    local log_file=$1
    local name=$2

    if [ -f "${log_file}" ]; then
        local total_lines=$(wc -l < "${log_file}")
        local error_lines=$(grep -c "ERROR\|CRITICAL\|Exception\|Traceback" "${log_file}" 2>/dev/null || echo "0")
        local warning_lines=$(grep -c "WARNING\|WARN" "${log_file}" 2>/dev/null || echo "0")
        local debug_lines=$(grep -c "DEBUG" "${log_file}" 2>/dev/null || echo "0")

        printf "📄 %-15s: %5d lines (%d errors, %d warnings, %d debug)\n" \
            "${name}" "${total_lines}" "${error_lines}" "${warning_lines}" "${debug_lines}"

        # Show recent errors if any
        if [ "${error_lines}" -gt 0 ]; then
            echo "   🚨 Recent errors:"
            grep "ERROR\|CRITICAL\|Exception\|Traceback" "${log_file}" | tail -3 | sed 's/^/      /'
        fi
    else
        printf "📄 %-15s: Not found\n" "${name}"
    fi
}

# Function to monitor repository states
check_repositories() {
    echo ""
    echo "📁 Repository Status:"
    echo "=================="

    for repo_dir in /tmp/supsrc-example-repo*; do
        if [ -d "${repo_dir}" ]; then
            repo_name=$(basename "${repo_dir}")
            cd "${repo_dir}"

            # Check git status
            local status=$(git status --porcelain 2>/dev/null | wc -l)
            local commits=$(git rev-list --count HEAD 2>/dev/null || echo "0")
            local last_commit=$(git log -1 --format="%h %s" 2>/dev/null || echo "No commits")

            printf "  %-20s: %2d changes, %2d commits, last: %s\n" \
                "${repo_name}" "${status}" "${commits}" "${last_commit}"

            # Show recent changes if any
            if [ "${status}" -gt 0 ]; then
                echo "    📝 Changes:"
                git status --porcelain | head -3 | sed 's/^/      /'
            fi
        fi
    done
}

# Function to show real-time monitoring
real_time_monitor() {
    echo ""
    echo "📊 Real-time Log Monitor (Ctrl+C to stop)"
    echo "=========================================="

    # Create named pipes for different log streams
    local main_pipe="/tmp/supsrc_main_pipe.$$"
    local error_pipe="/tmp/supsrc_error_pipe.$$"

    mkfifo "${main_pipe}" "${error_pipe}" 2>/dev/null

    # Color coding function
    colorize_logs() {
        while IFS= read -r line; do
            case "${line}" in
                *ERROR*)     echo -e "\033[31m${line}\033[0m" ;;  # Red
                *WARNING*)   echo -e "\033[33m${line}\033[0m" ;;  # Yellow
                *DEBUG*)     echo -e "\033[36m${line}\033[0m" ;;  # Cyan
                *INFO*)      echo -e "\033[32m${line}\033[0m" ;;  # Green
                *CRITICAL*)  echo -e "\033[35m${line}\033[0m" ;;  # Magenta
                *)           echo "${line}" ;;
            esac
        done
    }

    # Start tailing logs with color coding
    if [ -f "${LOG_DIR}/supsrc_main.log" ]; then
        tail -f "${LOG_DIR}/supsrc_main.log" | colorize_logs &
        TAIL_MAIN_PID=$!
    fi

    if [ -f "${LOG_DIR}/supsrc_error.log" ]; then
        tail -f "${LOG_DIR}/supsrc_error.log" | while IFS= read -r line; do
            echo -e "\033[41m[ERROR] ${line}\033[0m"  # Red background
        done &
        TAIL_ERROR_PID=$!
    fi

    if [ -f "${LOG_DIR}/changes.log" ]; then
        tail -f "${LOG_DIR}/changes.log" | while IFS= read -r line; do
            echo -e "\033[42m[CHANGE] ${line}\033[0m"  # Green background
        done &
        TAIL_CHANGES_PID=$!
    fi

    # Cleanup on exit
    cleanup_monitor() {
        kill ${TAIL_MAIN_PID} 2>/dev/null
        kill ${TAIL_ERROR_PID} 2>/dev/null
        kill ${TAIL_CHANGES_PID} 2>/dev/null
        rm -f "${main_pipe}" "${error_pipe}" 2>/dev/null
        exit 0
    }

    trap cleanup_monitor INT TERM

    # Wait for user interrupt
    wait
}

# Function to generate summary report
generate_report() {
    local report_file="${LOG_DIR}/debug_report.txt"

    echo ""
    echo "📊 Generating debug report..."

    cat > "${report_file}" << EOF
Supsrc Debug Report
Generated: $(date)
Log Directory: ${LOG_DIR}

=== LOG ANALYSIS ===
EOF

    # Analyze each log file
    for log_file in "${LOG_DIR}"/*.log; do
        if [ -f "${log_file}" ]; then
            local filename=$(basename "${log_file}")
            echo "--- ${filename} ---" >> "${report_file}"
            echo "Total lines: $(wc -l < "${log_file}")" >> "${report_file}"
            echo "Errors: $(grep -c "ERROR\|CRITICAL" "${log_file}" 2>/dev/null || echo "0")" >> "${report_file}"
            echo "Warnings: $(grep -c "WARNING" "${log_file}" 2>/dev/null || echo "0")" >> "${report_file}"
            echo "" >> "${report_file}"

            # Include last few errors
            if grep -q "ERROR\|CRITICAL" "${log_file}" 2>/dev/null; then
                echo "Recent errors:" >> "${report_file}"
                grep "ERROR\|CRITICAL" "${log_file}" | tail -5 >> "${report_file}"
                echo "" >> "${report_file}"
            fi
        fi
    done

    # Repository analysis
    echo "=== REPOSITORY ANALYSIS ===" >> "${report_file}"
    for repo_dir in /tmp/supsrc-example-repo*; do
        if [ -d "${repo_dir}" ]; then
            repo_name=$(basename "${repo_dir}")
            echo "--- ${repo_name} ---" >> "${report_file}"
            cd "${repo_dir}"
            echo "Git status: $(git status --porcelain | wc -l) changes" >> "${report_file}"
            echo "Commits: $(git rev-list --count HEAD 2>/dev/null || echo "0")" >> "${report_file}"
            echo "Last commit: $(git log -1 --format="%h %s %ad" --date=short 2>/dev/null || echo "None")" >> "${report_file}"
            echo "" >> "${report_file}"
        fi
    done

    echo "✅ Report saved to: ${report_file}"
}

# Main menu
show_menu() {
    echo ""
    echo "Choose an option:"
    echo "  1) Show log analysis"
    echo "  2) Check repository status"
    echo "  3) Real-time log monitoring"
    echo "  4) Generate debug report"
    echo "  5) Show recent errors only"
    echo "  6) Exit"
    echo ""
    read -p "Enter choice [1-6]: " choice

    case $choice in
        1)
            echo ""
            echo "📊 Log Analysis:"
            echo "==============="
            analyze_logs "${LOG_DIR}/supsrc_main.log" "Main"
            analyze_logs "${LOG_DIR}/supsrc_error.log" "Errors"
            analyze_logs "${LOG_DIR}/foundation.log" "Foundation"
            analyze_logs "${LOG_DIR}/tui_debug.log" "TUI"
            analyze_logs "${LOG_DIR}/changes.log" "Changes"
            show_menu
            ;;
        2)
            check_repositories
            show_menu
            ;;
        3)
            real_time_monitor
            ;;
        4)
            generate_report
            show_menu
            ;;
        5)
            echo ""
            echo "🚨 Recent Errors:"
            echo "================"
            for log_file in "${LOG_DIR}"/*.log; do
                if [ -f "${log_file}" ] && grep -q "ERROR\|CRITICAL\|Exception" "${log_file}" 2>/dev/null; then
                    echo "From $(basename "${log_file}"):"
                    grep "ERROR\|CRITICAL\|Exception" "${log_file}" | tail -5 | sed 's/^/  /'
                    echo ""
                fi
            done
            show_menu
            ;;
        6)
            echo "👋 Goodbye!"
            exit 0
            ;;
        *)
            echo "❌ Invalid choice"
            show_menu
            ;;
    esac
}

# Quick analysis on startup
echo "📊 Quick Analysis:"
echo "=================="
analyze_logs "${LOG_DIR}/supsrc_main.log" "Main"
analyze_logs "${LOG_DIR}/supsrc_error.log" "Errors"
analyze_logs "${LOG_DIR}/changes.log" "Changes"

# Check if logs are being actively written
if [ -f "${LOG_DIR}/supsrc_main.log" ]; then
    local age=$(stat -f %m "${LOG_DIR}/supsrc_main.log" 2>/dev/null)
    local now=$(date +%s)
    local diff=$((now - age))

    if [ ${diff} -lt 60 ]; then
        echo ""
        echo "🟢 Logs appear to be actively updating (modified ${diff}s ago)"
    else
        echo ""
        echo "🟡 Logs may be stale (modified ${diff}s ago)"
    fi
fi

# Start interactive menu
show_menu