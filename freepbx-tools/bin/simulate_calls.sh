#!/bin/bash

# FreePBX Call Simulation Monitor
# Monitors active call files and Asterisk activity
#
# VARIABLE MAP (Key Script Variables)
# -----------------------------------
# SPOOL_DIR      : Path to Asterisk outgoing call file spool directory
# LOG_FILE       : Path to Asterisk full log file
# active_files   : List of active call files in spool directory
# file           : Current call file being processed in loop
#
# FUNCTION MAP (Major Functions)
# -----------------------------
# monitor_calls      : Main monitoring loop, displays active call files and log activity
# (main script body) : Calls monitor_calls and handles script execution
#

set -euo pipefail

SPOOL_DIR="/var/spool/asterisk/outgoing"
LOG_FILE="/var/log/asterisk/full"

monitor_calls() {
    echo "📊 FREEPBX CALL SIMULATION MONITOR"
    echo "=================================="
    echo "📁 Spool Directory: $SPOOL_DIR"
    echo "📝 Log File: $LOG_FILE"
    echo ""
    echo "🔄 Press Ctrl+C to stop monitoring..."
    echo ""
    
    while true; do
        clear
        echo "📊 FREEPBX CALL SIMULATION MONITOR - $(date)"
        echo "=============================================="
        
        # Show active call files
        echo ""
        echo "📁 ACTIVE CALL FILES:"
        echo "--------------------"
        active_files=$(ls "$SPOOL_DIR"/*.call 2>/dev/null || echo "")
        if [[ -n "$active_files" ]]; then
            ls -la "$SPOOL_DIR"/*.call 2>/dev/null
            echo ""
            echo "📋 File Details:"
            for file in "$SPOOL_DIR"/*.call; do
                if [[ -f "$file" ]]; then
                    echo "  📄 $(basename "$file"):"
                    echo "     📅 Modified: $(stat -c %y "$file" 2>/dev/null || echo 'Unknown')"
                    echo "     📏 Size: $(stat -c %s "$file" 2>/dev/null || echo 'Unknown') bytes"
                    echo "     👤 Owner: $(stat -c %U:%G "$file" 2>/dev/null || echo 'Unknown')"
                    echo ""
                fi
            done
        else
            echo "   ✅ No active call files (all processed)"
        fi
        
        # Show recent call activity
        echo ""
        echo "📝 RECENT CALL ACTIVITY (last 10 entries):"
        echo "------------------------------------------"
        if [[ -f "$LOG_FILE" ]]; then
            tail -100 "$LOG_FILE" | grep -E "(call_|spool|Call failed|Queued call)" | tail -10 | while read -r line; do
                echo "   📋 $line"
            done
        else
            echo "   ⚠️  Log file not accessible"
        fi
        
        # Show Asterisk status
        echo ""
        echo "📞 ASTERISK STATUS:"
        echo "------------------"
        if command -v asterisk >/dev/null 2>&1; then
            echo "   📊 Active calls: $(asterisk -rx 'core show calls' 2>/dev/null | grep -c 'active call' || echo '0')"
            echo "   🔗 Channels: $(asterisk -rx 'core show channels' 2>/dev/null | tail -1 || echo 'Unknown')"
        else
            echo "   ⚠️  Asterisk CLI not accessible"
        fi
        
        # Show system info
        echo ""
        echo "💻 SYSTEM INFO:"
        echo "--------------"
        echo "   ⏰ Current time: $(date)"
        echo "   💾 Disk usage: $(df -h "$SPOOL_DIR" 2>/dev/null | tail -1 | awk '{print $5}' || echo 'Unknown') used"
        echo "   🔄 Uptime: $(uptime | awk -F'up ' '{print $2}' | awk -F',' '{print $1}' || echo 'Unknown')"
        
        echo ""
        echo "🔄 Refreshing in 5 seconds... (Ctrl+C to stop)"
        sleep 5
    done
}

show_summary() {
    echo "📊 CALL SIMULATION SUMMARY"
    echo "========================="
    
    # Count call files
    if ls "$SPOOL_DIR"/*.call >/dev/null 2>&1; then
        call_count=$(ls -1 "$SPOOL_DIR"/*.call 2>/dev/null | wc -l)
    else
        call_count=0
    fi
    echo "📁 Active call files: $call_count"
    
    # Recent activity
    if [[ -f "$LOG_FILE" ]]; then
        recent_calls=$(tail -100 "$LOG_FILE" | grep -c "call_" || echo "0")
        echo "📝 Recent call activity: $recent_calls entries in last 100 log lines"
        
        # Last call simulation
        last_call=$(tail -100 "$LOG_FILE" | grep "call_" | tail -1 || echo "None found")
        echo "🕐 Last call activity: $last_call"
    fi
    
    # Check for results files
    if ls /home/123net/call_simulation_results_*.json >/dev/null 2>&1; then
        results_count=$(ls -1 /home/123net/call_simulation_results_*.json 2>/dev/null | wc -l)
        latest_results=$(ls -t /home/123net/call_simulation_results_*.json 2>/dev/null | head -1)
        echo "📋 Saved result files: $results_count"
        echo "📄 Latest results: $(basename "$latest_results")"
    else
        echo "📋 Saved result files: 0"
    fi
}

show_help() {
    echo "FreePBX Call Simulation Monitor"
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  monitor    - Start real-time monitoring (default)"
    echo "  summary    - Show current status summary"
    echo "  help       - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0               # Start monitoring"
    echo "  $0 monitor       # Start monitoring" 
    echo "  $0 summary       # Show summary"
}

# Main logic
case "${1:-monitor}" in
    monitor)
        monitor_calls
        ;;
    summary)
        show_summary
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
        
        # Show recent call activity
        echo ""
        echo "📝 RECENT CALL ACTIVITY (last 10 entries):"
        echo "------------------------------------------"
        if [[ -f "$LOG_FILE" ]]; then
            tail -100 "$LOG_FILE" | grep -E "(call_|spool|Call failed|Queued call)" | tail -10 | while read -r line; do
                echo "   📋 $line"
            done
        else
            echo "   ⚠️  Log file not accessible"
        fi
        
        # Show Asterisk status
        echo ""
        echo "📞 ASTERISK STATUS:"
        echo "------------------"
        if command -v asterisk >/dev/null 2>&1; then
            echo "   📊 Active calls: $(asterisk -rx 'core show calls' 2>/dev/null | grep -c 'active call' || echo '0')"
            echo "   🔗 Channels: $(asterisk -rx 'core show channels' 2>/dev/null | tail -1 || echo 'Unknown')"
        else
            echo "   ⚠️  Asterisk CLI not accessible"
        fi
        
        # Show system info
        echo ""
        echo "💻 SYSTEM INFO:"
        echo "--------------"
        echo "   ⏰ Current time: $(date)"
        echo "   💾 Disk usage: $(df -h "$SPOOL_DIR" 2>/dev/null | tail -1 | awk '{print $5}' || echo 'Unknown') used"
        echo "   🔄 Uptime: $(uptime | awk -F'up ' '{print $2}' | awk -F',' '{print $1}' || echo 'Unknown')"
        
        echo ""
        echo "🔄 Refreshing in 5 seconds... (Ctrl+C to stop)"
        sleep 5
    done
}

show_summary() {
    echo "📊 CALL SIMULATION SUMMARY"
    echo "========================="
    
    # Count call files
    if ls "$SPOOL_DIR"/*.call >/dev/null 2>&1; then
        call_count=$(ls -1 "$SPOOL_DIR"/*.call 2>/dev/null | wc -l)
    else
        call_count=0
    fi
    echo "📁 Active call files: $call_count"
    
    # Recent activity
    if [[ -f "$LOG_FILE" ]]; then
        recent_calls=$(tail -100 "$LOG_FILE" | grep -c "call_" || echo "0")
        echo "📝 Recent call activity: $recent_calls entries in last 100 log lines"
        
        # Last call simulation
        last_call=$(tail -100 "$LOG_FILE" | grep "call_" | tail -1 || echo "None found")
        echo "🕐 Last call activity: $last_call"
    fi
    
    # Check for results files
    results_count=$(ls -1 /home/123net/call_simulation_results_*.json 2>/dev/null | wc -l || echo "0")
    echo "📋 Saved result files: $results_count"
    
    if [[ $results_count -gt 0 ]]; then
        latest_results=$(ls -t /home/123net/call_simulation_results_*.json 2>/dev/null | head -1)
        echo "📄 Latest results: $(basename "$latest_results")"
    fi
}

show_help() {
    echo "FreePBX Call Simulation Monitor"
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  monitor    - Start real-time monitoring (default)"
    echo "  summary    - Show current status summary"
    echo "  help       - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0               # Start monitoring"
    echo "  $0 monitor       # Start monitoring" 
    echo "  $0 summary       # Show summary"
}

# Main logic
case "${1:-monitor}" in
    monitor)
        monitor_calls
        ;;
    summary)
        show_summary
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
    echo "  --user <username>          SSH username (default: $DEFAULT_USER)"
    echo "  --caller-id <number>       Caller ID (default: $DEFAULT_CALLER_ID)"
    echo "  --dry-run                  Show what would be done without executing"
    echo "  --verbose                  Enable verbose output"
    echo "  --help                     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 test-did 2485815200"
    echo "  $0 test-extension 4220"
    echo "  $0 comprehensive --verbose"
    echo "  $0 monitor"
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if Python script exists
    if [ ! -f "$SCRIPT_DIR/call_simulator.py" ]; then
        echo -e "${RED}❌ call_simulator.py not found in $SCRIPT_DIR${NC}"
        exit 1
    fi
    
    # Check SSH connectivity
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER_USER@$SERVER_IP" "echo 'SSH OK'" >/dev/null 2>&1; then
        echo -e "${RED}❌ Cannot connect to $SERVER_IP via SSH${NC}"
        echo "   Make sure SSH key authentication is set up"
        exit 1
    fi
    
    # Check if server has Asterisk
    if ! ssh "$SERVER_USER@$SERVER_IP" "test -d /var/spool/asterisk/outgoing" >/dev/null 2>&1; then
        echo -e "${RED}❌ Asterisk spool directory not found on server${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Prerequisites check passed${NC}"
}

monitor_calls() {
    echo -e "${BLUE}📊 Monitoring active call simulations...${NC}"
    echo "Press Ctrl+C to stop monitoring"
    
    while true; do
        # Check for call files in spool directory
        active_calls=$(ssh "$SERVER_USER@$SERVER_IP" "ls -la /var/spool/asterisk/outgoing/call_*.call 2>/dev/null | wc -l" 2>/dev/null || echo "0")
        
        # Check recent Asterisk logs
        recent_activity=$(ssh "$SERVER_USER@$SERVER_IP" "tail -5 /var/log/asterisk/full 2>/dev/null | grep -c 'call_' || echo '0'" 2>/dev/null)
        
        # Clear screen and show status
        clear
        echo -e "${BLUE}📞 CALL SIMULATION MONITOR${NC}"
        echo "=" * 40
        echo "Time: $(date)"
        echo "Active call files: $active_calls"
        echo "Recent activity: $recent_activity log entries"
        echo ""
        
        if [ "$active_calls" -gt 0 ]; then
            echo -e "${YELLOW}📋 Active Call Files:${NC}"
            ssh "$SERVER_USER@$SERVER_IP" "ls -la /var/spool/asterisk/outgoing/call_*.call 2>/dev/null || echo 'None'" 2>/dev/null
        fi
        
        echo ""
        echo -e "${BLUE}📝 Recent Asterisk Activity:${NC}"
        ssh "$SERVER_USER@$SERVER_IP" "tail -10 /var/log/asterisk/full 2>/dev/null | grep -E '(NOTICE|WARNING|ERROR)' | tail -5 || echo 'No recent activity'" 2>/dev/null
        
        sleep 5
    done
}

cleanup_call_files() {
    echo -e "${YELLOW}🧹 Cleaning up old call simulation files...${NC}"
    
    # Remove old call files from temp directory
    old_temp_files=$(ssh "$SERVER_USER@$SERVER_IP" "ls /tmp/call_* 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    if [ "$old_temp_files" -gt 0 ]; then
        ssh "$SERVER_USER@$SERVER_IP" "rm -f /tmp/call_*" 2>/dev/null
        echo "   Removed $old_temp_files old temp files"
    fi
    
    # Check for stuck call files (older than 5 minutes)
    stuck_files=$(ssh "$SERVER_USER@$SERVER_IP" "find /var/spool/asterisk/outgoing -name 'call_*.call' -mmin +5 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    if [ "$stuck_files" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Found $stuck_files stuck call files (older than 5 minutes)${NC}"
        ssh "$SERVER_USER@$SERVER_IP" "find /var/spool/asterisk/outgoing -name 'call_*.call' -mmin +5 -ls 2>/dev/null"
        
        read -p "Remove stuck call files? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ssh "$SERVER_USER@$SERVER_IP" "find /var/spool/asterisk/outgoing -name 'call_*.call' -mmin +5 -delete 2>/dev/null"
            echo "   Removed stuck call files"
        fi
    fi
    
    echo -e "${GREEN}✅ Cleanup completed${NC}"
}

run_simulation() {
    local command="$1"
    shift
    
    log "Starting call simulation: $command $*"
    
    # Build Python command
    python_cmd="python3 $SCRIPT_DIR/call_simulator.py"
    python_cmd="$python_cmd --server $SERVER_IP --user $SERVER_USER --caller-id $CALLER_ID"
    
    case "$command" in
        "test-did")
            if [ $# -lt 1 ]; then
                echo -e "${RED}❌ DID number required${NC}"
                exit 1
            fi
            python_cmd="$python_cmd --did $1"
            ;;
        "test-extension")
            if [ $# -lt 1 ]; then
                echo -e "${RED}❌ Extension number required${NC}"
                exit 1
            fi
            python_cmd="$python_cmd --extension $1"
            ;;
        "test-voicemail")
            if [ $# -lt 1 ]; then
                echo -e "${RED}❌ Mailbox number required${NC}"
                exit 1
            fi
            python_cmd="$python_cmd --voicemail $1"
            ;;
        "test-playback")
            if [ $# -lt 1 ]; then
                echo -e "${RED}❌ Sound file required${NC}"
                exit 1
            fi
            python_cmd="$python_cmd --playback $1"
            ;;
        "comprehensive")
            python_cmd="$python_cmd --comprehensive"
            ;;
        *)
            echo -e "${RED}❌ Unknown command: $command${NC}"
            show_help
            exit 1
            ;;
    esac
    
    # Execute the simulation
    if [ "$DRY_RUN" = "true" ]; then
        echo -e "${YELLOW}🔍 DRY RUN - Would execute:${NC}"
        echo "$python_cmd"
    else
        echo -e "${BLUE}🚀 Executing call simulation...${NC}"
        if [ "$VERBOSE" = "true" ]; then
            $python_cmd 2>&1 | tee -a "$LOG_FILE"
        else
            $python_cmd | tee -a "$LOG_FILE"
        fi
        
        echo -e "${GREEN}✅ Simulation completed${NC}"
        echo "Log saved to: $LOG_FILE"
    fi
}

# Parse command line arguments
SERVER_IP="$DEFAULT_SERVER"
SERVER_USER="$DEFAULT_USER"
CALLER_ID="$DEFAULT_CALLER_ID"
DRY_RUN="false"
VERBOSE="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        --server)
            SERVER_IP="$2"
            shift 2
            ;;
        --user)
            SERVER_USER="$2"
            shift 2
            ;;
        --caller-id)
            CALLER_ID="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --verbose)
            VERBOSE="true"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        monitor)
            COMMAND="monitor"
            shift
            break
            ;;
        cleanup)
            COMMAND="cleanup"
            shift
            break
            ;;
        test-*|comprehensive)
            COMMAND="$1"
            shift
            break
            ;;
        *)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Main execution
print_header

if [ -z "${COMMAND:-}" ]; then
    show_help
    exit 0
fi

log "Starting FreePBX call simulation manager"
log "Server: $SERVER_IP, User: $SERVER_USER, Caller ID: $CALLER_ID"

# Handle special commands
case "$COMMAND" in
    "monitor")
        check_prerequisites
        monitor_calls
        ;;
    "cleanup")
        check_prerequisites
        cleanup_call_files
        ;;
    *)
        check_prerequisites
        run_simulation "$COMMAND" "$@"
        ;;
esac

log "FreePBX call simulation manager completed"