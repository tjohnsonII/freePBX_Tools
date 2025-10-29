#!/bin/bash
# FreePBX Call Simulation Monitor
# Monitors active call files and Asterisk activity

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