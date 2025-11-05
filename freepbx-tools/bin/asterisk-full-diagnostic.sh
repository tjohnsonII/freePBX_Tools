[root@pbx-oib diagnostic]# cat asterisk-full-diagnostic.sh 
#!/bin/bash

# ANSI Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Output location
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT="full_diagnostic_$TIMESTAMP.txt"

# Print header
echo -e "${CYAN}${BOLD}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║          🔧  Asterisk & FreePBX Full Diagnostic Tool          ║
║                                                               ║
║          Complete System Health & Configuration Report        ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${YELLOW}📋 Generating comprehensive diagnostic report...${NC}"
echo -e "${CYAN}Output file: ${BOLD}$OUTPUT${NC}\n"

# Header
{
echo "========== Asterisk + FreePBX Full Diagnostic Report =========="
echo "Generated: $(date)"
echo "==============================================================="
echo
echo "🔹 Hostname: $(hostname)"
echo "🔹 Uptime:"
uptime
echo
echo "🔹 OS Info:"
cat /etc/*release
echo
echo "🔹 Kernel & Architecture:"
uname -a
echo
echo "🔹 Disk Usage:"
df -h
echo
echo "🔹 Memory Usage:"
free -m
echo
echo "🔹 CPU Load:"
top -b -n1 | head -15
echo
echo "==============================================================="
echo "🔸 Asterisk Version:"
asterisk -rx "core show version"
echo
echo "🔸 Asterisk Modules Loaded (PJSIP):"
asterisk -rx "module show like pjsip"
echo
echo "🔸 Asterisk Core Settings:"
asterisk -rx "core show settings"
echo
echo "🔸 Active Channels / Calls:"
asterisk -rx "core show channels"
echo
echo "🔸 SIP Settings:"
asterisk -rx "pjsip show settings"
echo
echo "🔸 PJSIP Endpoints:"
asterisk -rx "pjsip show endpoints"
echo
echo "🔸 PJSIP Contacts:"
asterisk -rx "pjsip show contacts"
echo
echo "🔸 PJSIP Registrations:"
asterisk -rx "pjsip show registrations"
echo
echo "🔸 PJSIP Transports:"
asterisk -rx "pjsip show transports"
echo
echo "🔸 Dialplan Hints:"
asterisk -rx "core show hints"
echo
echo "==============================================================="
echo "📄 Last 10 Call Detail Records (CDRs):"
mysql -u root -e "USE asteriskcdrdb; SELECT calldate, src, dst, disposition, duration FROM cdr ORDER BY calldate DESC LIMIT 10;"
echo
} > "$OUTPUT"

echo -e "${GREEN}${BOLD}✓ Diagnostic complete!${NC}"
echo -e "${CYAN}Output saved to: ${BOLD}$OUTPUT${NC}"

# Show file size
SIZE=$(du -h "$OUTPUT" | cut -f1)
echo -e "${CYAN}File size: ${BOLD}$SIZE${NC}"

# Show quick summary
echo -e "\n${YELLOW}${BOLD}Quick Summary:${NC}"
DISK_WARN=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_WARN" -gt 80 ]; then
    echo -e "${RED}⚠ Disk usage is high: ${DISK_WARN}%${NC}"
else
    echo -e "${GREEN}✓ Disk usage OK: ${DISK_WARN}%${NC}"
fi

MEM_FREE=$(free -m | awk 'NR==2{printf "%.0f", $7/$2*100}')
if [ "$MEM_FREE" -lt 10 ]; then
    echo -e "${RED}⚠ Low free memory: ${MEM_FREE}%${NC}"
else
    echo -e "${GREEN}✓ Memory OK: ${MEM_FREE}% free${NC}"
fi

CHANNELS=$(asterisk -rx "core show channels" | grep "active channel" | awk '{print $1}')
echo -e "${CYAN}📞 Active channels: ${BOLD}$CHANNELS${NC}"

echo ""

