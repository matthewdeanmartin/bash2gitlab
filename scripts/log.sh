#!/usr/bin/env bash

# Bash Logging Library
# Source this file to use it, or execute it directly for a demo

# Log levels (matching Python's logging module)
declare -gA LOG_LEVELS=(
    [CRITICAL]=50
    [ERROR]=40
    [WARNING]=30
    [INFO]=20
    [DEBUG]=10
    [NOTSET]=0
)

# Current log level (default to INFO)
LOG_LEVEL=${LOG_LEVEL:-20}

# Color codes
declare -gA LOG_COLORS=(
    [CRITICAL]="\033[1;37;41m"  # Bold white on red
    [ERROR]="\033[1;31m"         # Bold red
    [WARNING]="\033[1;33m"       # Bold yellow
    [INFO]="\033[1;32m"          # Bold green
    [DEBUG]="\033[1;34m"         # Bold blue
    [RESET]="\033[0m"
)

# Check if colors should be disabled
USE_COLOR=1
if [[ -n "${NO_COLOR}" || -n "${NOCOLOR}" || ! -t 1 ]]; then
    USE_COLOR=0
fi

# Stopwatch variables
declare -g STOPWATCH_START=0
declare -g STOPWATCH_LAST=0

# Timing history for spark graph (stores elapsed times in milliseconds)
declare -ga TIMING_HISTORY=()
MAX_HISTORY=20

# Math backend detection
MATH_BACKEND=""

_detect_math_backend() {
    if [[ -n "$MATH_BACKEND" ]]; then
        return
    fi

    if command -v bc &>/dev/null; then
        MATH_BACKEND="bc"
    elif command -v python3 &>/dev/null; then
        MATH_BACKEND="python3"

    elif command -v python &>/dev/null; then
        MATH_BACKEND="python"
    elif command -v node &>/dev/null; then
        MATH_BACKEND="node"
    else
        MATH_BACKEND="bash"
    fi
    echo $MATH_BACKEND
}

# Perform floating point math
_math() {
    local expr="$1"
    _detect_math_backend

    case "$MATH_BACKEND" in
        bc)
            echo "$expr" | bc -l
            ;;
        python3|python)
            "$MATH_BACKEND" -c "print($expr)"
            ;;
        node)
            node -e "console.log($expr)"
            ;;
        bash)
            # Bash only does integer math, multiply by 1000 for milliseconds
            local result
            result=$(( ${expr//[^0-9]/} ))
            echo "$result"
            ;;
    esac
}

# Get current time in milliseconds
_get_time_ms() {
    local time_ms
    if [[ "$MATH_BACKEND" == "bash" ]]; then
        # Use seconds for bash fallback
        printf -v time_ms '%(%s)T' -1
        echo "${time_ms}000"
    else
        time_ms=$(_math "$(date +%s.%N) * 1000")
        printf "%.0f" "$time_ms"
    fi
}

# Format time duration
_format_duration() {
    local ms=$1
    local sec min hr

    if [[ "$MATH_BACKEND" == "bash" ]]; then
        sec=$((ms / 1000))
        if ((sec < 60)); then
            echo "${sec}s"
        elif ((sec < 3600)); then
            min=$((sec / 60))
            sec=$((sec % 60))
            echo "${min}m${sec}s"
        else
            hr=$((sec / 3600))
            min=$(((sec % 3600) / 60))
            echo "${hr}h${min}m"
        fi
    else
        sec=$(_math "$ms / 1000")
        if (( $(echo "$sec < 1" | bc -l 2>/dev/null || echo 0) )); then
            printf "%.0fms" "$ms"
        elif (( $(echo "$sec < 60" | bc -l 2>/dev/null || echo 0) )); then
            printf "%.2fs" "$sec"
        elif (( $(echo "$sec < 3600" | bc -l 2>/dev/null || echo 0) )); then
            printf "%.1fm" "$(_math "$sec / 60")"
        else
            printf "%.1fh" "$(_math "$sec / 3600")"
        fi
    fi
}

# Generate spark graph
_generate_spark() {
    local -a values=("$@")
    local max=0
    local spark=""
    local blocks=("▁" "▂" "▃" "▄" "▅" "▆" "▇" "█")

    # Find max value
    for val in "${values[@]}"; do
        if ((val > max)); then
            max=$val
        fi
    done

    if ((max == 0)); then
        max=1
    fi

    # Generate spark line
    for val in "${values[@]}"; do
        local idx
        if [[ "$MATH_BACKEND" == "bash" ]]; then
            idx=$(( (val * 7) / max ))
        else
            idx=$(_math "int(($val * 7.0) / $max)")
        fi
        if ((idx > 7)); then idx=7; fi
        if ((idx < 0)); then idx=0; fi

        # Color based on value (red for slow, green for fast)
        if ((USE_COLOR)); then
            if ((val * 3 > max * 2)); then
                spark+="\033[1;31m${blocks[$idx]}\033[0m"  # Red for slow
            elif ((val * 2 < max)); then
                spark+="\033[1;32m${blocks[$idx]}\033[0m"  # Green for fast
            else
                spark+="${blocks[$idx]}"  # Default for medium
            fi
        else
            spark+="${blocks[$idx]}"
        fi
    done

    echo -e "$spark"
}

# Start the stopwatch
log_stopwatch_start() {
    _detect_math_backend
    STOPWATCH_START=$(_get_time_ms)
    STOPWATCH_LAST=$STOPWATCH_START
    TIMING_HISTORY=()
}

# Get elapsed time since last log
_get_elapsed() {
    local now=$(_get_time_ms)
    local elapsed
    if [[ "$MATH_BACKEND" == "bash" ]]; then
        elapsed=$((now - STOPWATCH_LAST))
    else
        elapsed=$(_math "$now - $STOPWATCH_LAST")
        printf "%.0f" "$elapsed"
    fi
    STOPWATCH_LAST=$now
    echo "$elapsed"
}

# Get total time since start
_get_total() {
    local now=$(_get_time_ms)
    local total
    if [[ "$MATH_BACKEND" == "bash" ]]; then
        total=$((now - STOPWATCH_START))
    else
        total=$(_math "$now - $STOPWATCH_START")
        printf "%.0f" "$total"
    fi
    echo "$total"
}

# Core logging function
_log() {
    local level=$1
    local level_num=${LOG_LEVELS[$level]}
    shift
    local message="$*"

    # Check if we should log this level
    if ((level_num < LOG_LEVEL)); then
        return
    fi

    # Get timing info
    local elapsed=$(_get_elapsed)
    local total=$(_get_total)

    # Add to history
    TIMING_HISTORY+=("$elapsed")
    if ((${#TIMING_HISTORY[@]} > MAX_HISTORY)); then
        TIMING_HISTORY=("${TIMING_HISTORY[@]:1}")
    fi

    # Generate spark graph
    local spark=""
    if ((${#TIMING_HISTORY[@]} > 1)); then
        spark=$(_generate_spark "${TIMING_HISTORY[@]}")
    fi

    # Format timestamp
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Build log line
    local color=""
    local reset=""
    if ((USE_COLOR)); then
        color="${LOG_COLORS[$level]}"
        reset="${LOG_COLORS[RESET]}"
    fi

    # Format: [TIME] [LEVEL] [+elapsed/total] [spark] message
    local elapsed_fmt=$(_format_duration "$elapsed")
    local total_fmt=$(_format_duration "$total")

    printf "%s [%b%-8s%b] [+%-8s / %-8s]" \
        "$timestamp" "$color" "$level" "$reset" "$elapsed_fmt" "$total_fmt"

    if [[ -n "$spark" ]]; then
        printf " [%b]" "$spark"
    fi

    printf " %s\n" "$message"
}

# Logging functions
log_debug() {
    _log DEBUG "$@"
}

log_info() {
    _log INFO "$@"
}

log_warning() {
    _log WARNING "$@"
}

log_error() {
    _log ERROR "$@"
}

log_critical() {
    _log CRITICAL "$@"
}

# Set log level
log_set_level() {
    local level=$1
    if [[ -n "${LOG_LEVELS[$level]}" ]]; then
        LOG_LEVEL=${LOG_LEVELS[$level]}
    else
        echo "Invalid log level: $level" >&2
        return 1
    fi
}

# Demo mode - runs if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "=== Bash Logging Library Demo ==="
    echo "Math backend: $MATH_BACKEND"
    echo ""

    log_set_level DEBUG
    log_stopwatch_start

    log_debug "This is a debug message"
    sleep 0.1

    log_info "This is an info message"
    sleep 0.2

    log_warning "This is a warning message"
    sleep 0.05

    log_error "This is an error message"
    sleep 0.3

    log_info "Let's simulate some work..."
    for i in {1..10}; do
        log_debug "Processing item $i"
        sleep $(awk "BEGIN {print $RANDOM / 32768 * 0.2}")
    done

    log_critical "This is a critical message!"
    sleep 0.1

    log_info "Demo complete - notice the spark graph showing timing patterns"

    echo ""
    echo "=== Testing log level filtering ==="
    log_set_level WARNING
    log_debug "This debug message should not appear"
    log_info "This info message should not appear"
    log_warning "This warning should appear"
    log_error "This error should appear"

    echo ""
    echo "=== Usage ==="
    echo "Source this file: source ${BASH_SOURCE[0]}"
    echo "Then use: log_stopwatch_start, log_debug, log_info, log_warning, log_error, log_critical"
    echo "Set level: log_set_level DEBUG|INFO|WARNING|ERROR|CRITICAL"
    echo "Disable colors: export NO_COLOR=1"
fi