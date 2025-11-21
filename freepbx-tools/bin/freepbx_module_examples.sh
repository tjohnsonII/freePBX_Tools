#!/bin/bash

# Example usage script for the FreePBX Module Analyzer
# Demonstrates different ways to use the new module analysis tools
#
# VARIABLE MAP (Key Script Variables)
# -----------------------------------
# (No persistent variables; all commands are run directly)
#
# FUNCTION MAP (Major Script Sections)
# ------------------------------------
# (main script body) : Prints usage examples and command explanations
#

echo "🔍 FreePBX Module Analysis Tools - Usage Examples"
echo "================================================="
echo

echo "1. Quick module status overview:"
echo "   freepbx-module-status"
echo "   (Shows enabled/disabled status of all modules)"
echo

echo "2. Comprehensive module analysis (text output):"
echo "   freepbx-module-analyzer"
echo "   (Detailed analysis with configuration information)"
echo

echo "3. Generate JSON report for automation:"
echo "   freepbx-module-analyzer --format json --output /tmp/module_report.json"
echo "   (Machine-readable output for scripts)"
echo

echo "4. Custom MySQL connection:"
echo "   freepbx-module-analyzer --socket /var/lib/mysql/mysql.sock --db-user freepbx"
echo "   (Use specific database connection parameters)"
echo

echo "5. Access via interactive menu:"
echo "   freepbx-callflows"
echo "   (Then select option 7 for module analysis)"
echo

echo "================================================="
echo "The module analyzer evaluates:"
echo "• All FreePBX modules (enabled/disabled status)"
echo "• Core component configurations (extensions, trunks, queues)"
echo "• Voicemail settings and user counts"
echo "• Call parking configuration"
echo "• Fax module settings (if installed)"
echo "• Conference room configurations"
echo "• Asterisk module status"
echo "• System information and versions"
echo

echo "📊 Sample output includes:"
echo "• Module inventory and version information"
echo "• Configuration counts and summaries"
echo "• Key system module status"
echo "• Detailed settings for advanced modules"
echo

echo "🔧 For troubleshooting:"
echo "• Check module versions against policy"
echo "• Identify misconfigured or disabled modules"
echo "• Compare configurations across multiple systems"
echo "• Generate reports for documentation"