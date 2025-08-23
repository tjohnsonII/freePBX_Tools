[root@pbx-oib diagnostic]# cat asterisk-full-diagnostic.sh 
#!/bin/bash

# Output location
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT="full_diagnostic_$TIMESTAMP.txt"

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

echo "✅ Diagnostic complete! Output saved to: $OUTPUT"

