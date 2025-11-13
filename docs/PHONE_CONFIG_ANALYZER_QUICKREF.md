# Phone Config Analyzer - Quick Reference

## Command Syntax

```bash
python phone_config_analyzer.py [config_file] [options]
```

## Common Use Cases

### Single File Analysis
```bash
python phone_config_analyzer.py phone.cfg
```

### Batch Analysis (Directory)
```bash
python phone_config_analyzer.py --directory /tftpboot/configs/
```

### With Export
```bash
python phone_config_analyzer.py phone.cfg --json report.json --csv summary.csv
```

### Scripting (No Colors)
```bash
python phone_config_analyzer.py phone.cfg --no-color > audit.log
```

## What It Analyzes

| Category | What It Checks |
|----------|----------------|
| **SIP Accounts** | Extension, user ID, server, registration status |
| **Security** | Passwords, ciphers, credential exposure, provisioning |
| **Network** | VLAN, NTP, Syslog, QoS, LLDP |
| **Features** | Presence, paging, volume persistence, feature keys |
| **Line Keys** | BLF, speed dial, line assignments (1-96) |
| **Softkeys** | Custom softkey mappings |
| **Dial Plan** | 911, long distance, international patterns |

## Security Severity Levels

- **CRITICAL**: Exposed passwords, default credentials
- **HIGH**: Weak passwords (< 8 chars)
- **MEDIUM**: Weak ciphers, HTTP provisioning
- **LOW**: TR-069 insecure, missing features

## Supported Phone Types

- ✅ Polycom VVX/SoundPoint (`.xml`, `.cfg`)
- ✅ Yealink T4x/T5x (`.cfg`)
- ✅ Cisco SPA (`.xml`)
- ✅ Grandstream GXP (`.cfg`)
- ✅ Sangoma (`.conf`)

## Output Files

### JSON (`--json`)
Complete findings with all details, machine-readable

### CSV (`--csv`)
Summary format for Excel/Google Sheets

### Terminal
Colorized, human-readable report

## Quick Checks

### Find Security Issues
```bash
python phone_config_analyzer.py config.xml --json out.json
python -c "import json; data=json.load(open('out.json')); print([i for i in data['findings']['security_issues'] if i['severity']=='CRITICAL'])"
```

### Extract SIP Account Info
```bash
python phone_config_analyzer.py config.xml --json out.json
python -c "import json; data=json.load(open('out.json')); [print(f\"{a['address']}@{a['server']}\") for a in data['findings']['sip_accounts'] if a['address']]"
```

### Check Feature Status
```bash
python phone_config_analyzer.py config.xml --json out.json
python -c "import json; data=json.load(open('out.json')); print({k:v for k,v in data['findings']['feature_status'].items() if v=='1'})"
```

## Integration Examples

### With FreePBX Phone Analyzer
```bash
# Get active phones
freepbx-phone-analyzer > active_phones.txt

# Analyze their configs
python phone_config_analyzer.py --directory /tftpboot/
```

### With Version Check
```bash
# Check compliance
python version_check.py --policy version_policy.json

# Check phone configs
python phone_config_analyzer.py --directory /tftpboot/ --json audit.json
```

### Automated Compliance
```bash
#!/bin/bash
# Daily compliance check

DATE=$(date +%Y%m%d)
python phone_config_analyzer.py --directory /tftpboot/ \
    --json /var/log/phone_audit_$DATE.json \
    --no-color > /var/log/phone_audit_$DATE.log

# Email if critical issues found
if grep -q "CRITICAL" /var/log/phone_audit_$DATE.log; then
    mail -s "Phone Config Alert" admin@example.com < /var/log/phone_audit_$DATE.log
fi
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No configuration data parsed" | Check file encoding, try `--json` to see details |
| False cipher warnings | Ignore `!NULL` and `!MD5` (these exclude weak ciphers) |
| Missing parameters | Some configs export with passwords masked (secure) |
| Slow batch processing | Use `find` with `xargs -P 4` for parallel processing |

## Performance Tips

### Parallel Batch Processing
```bash
find /tftpboot -name "*.cfg" | \
    xargs -P 4 -I {} python phone_config_analyzer.py {} --json reports/{}.json
```

### Filter Before Processing
```bash
# Only process Polycom configs
find /tftpboot -name "*.cfg" -exec grep -l "PHONE_CONFIG" {} \; | \
    xargs -I {} python phone_config_analyzer.py {}
```

## Exit Codes

- `0` - Success
- `1` - Error (file not found, parse error)

## Python API Example

```python
from pathlib import Path
from phone_config_analyzer import PhoneConfigAnalyzer

analyzer = PhoneConfigAnalyzer()
findings = analyzer.analyze_all(Path('config.xml'))

# Check compliance
critical = [i for i in findings['security_issues'] if i['severity'] == 'CRITICAL']
if critical:
    print(f"FAIL: {len(critical)} critical issues")
else:
    print("PASS: No critical issues")

# Get extension info
for account in findings['sip_accounts']:
    if account['address']:
        print(f"Extension {account['address']} -> {account['server']}")
```

## Related Commands

```bash
# Live phone analysis (requires FreePBX)
freepbx-phone-analyzer

# VPBX web scraper analysis
python analyze_vpbx_phone_configs.py --data-dir vpbx_data/

# Version compliance
python version_check.py --policy version_policy.json

# Full FreePBX diagnostic
freepbx-diagnostic
```

## Get Help

```bash
python phone_config_analyzer.py --help
```

## Report Sections

When you run the analyzer, you'll see these sections:

1. 📞 **SIP ACCOUNTS** - Registration info
2. 🔒 **SECURITY ISSUES** - Vulnerabilities found
3. 🌐 **NETWORK CONFIGURATION** - Network settings
4. ⚙️ **FEATURE STATUS** - Enabled features
5. 🔘 **LINE KEYS SUMMARY** - Key type counts
6. 🎹 **CUSTOM SOFTKEYS** - Softkey mappings
7. ⚠️ **CONFIGURATION WARNINGS** - Non-compliant settings

Each section is color-coded:
- 🔴 Red = Critical issues
- 🟡 Yellow = Warnings
- 🟢 Green = Good/enabled
- 🔵 Cyan = Information

## Minimum Requirements

- Python 3.6+
- No external dependencies
- Works on Windows, Linux, macOS

## File Size Limits

- Max config file size: ~10 MB
- Max parameters: ~10,000
- Processing time: ~0.1 sec per file

## Best Practices

1. ✅ Run after provisioning changes
2. ✅ Schedule daily compliance checks
3. ✅ Export JSON for historical tracking
4. ✅ Review CRITICAL issues immediately
5. ✅ Validate dial plan includes 911
6. ✅ Check for exposed credentials
7. ✅ Verify provisioning uses HTTPS

## Support

For issues or enhancements, see the main FreePBX Tools repository.
