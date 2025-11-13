# Phone Config Analyzer - Integration Guide

## Overview

The Phone Configuration Analyzer has been integrated into the FreePBX Tools Manager as **Menu Option 7**.

## Accessing the Phone Config Analyzer

### Step 1: Launch FreePBX Tools Manager
```bash
python freepbx_tools_manager.py
```

### Step 2: Select Option 7
From the main menu:
```
📋 Main Menu:
  1) Deploy tools to server(s)
  2) Uninstall tools from server(s)
  3) 🔄 Uninstall + Install (clean deployment)
  4) Test dashboard on test server (69.39.69.102)
  5) View deployment status
  6) 🔌 SSH into a server
  7) 📱 Phone Config Analyzer      ← NEW!
  8) Exit

Choose option (1-8): 7
```

## Phone Config Analyzer Submenu

When you select option 7, you'll see:

```
======================================================================
  📱 Phone Configuration Analyzer
======================================================================

What would you like to analyze?
  1) Single config file
  2) Directory of config files
  3) Run interactive demo
  4) View documentation
  5) Back to main menu

Choose option (1-5):
```

## Usage Scenarios

### Option 1: Single Config File Analysis

**When to use**: Analyze a single phone configuration file

**Example workflow**:
1. Select option 1
2. Enter file path: `freepbx-tools/bin/123net_internal_docs/CSU_VVX600.cfg`
3. Choose if you want JSON export: `yes` or `no`
4. Choose if you want CSV export: `yes` or `no`
5. View the comprehensive analysis report

**Output**:
- Terminal display with color-coded sections
- Optional JSON file with complete findings
- Optional CSV file with summary data

### Option 2: Directory Analysis

**When to use**: Analyze multiple phone configs at once (e.g., entire TFTP directory)

**Example workflow**:
1. Select option 2
2. Enter directory path: `/tftpboot/configs/` (Linux) or `C:\TFTP\configs\` (Windows)
3. Choose if you want batch JSON export
4. If yes, specify output directory: `reports`
5. View analysis for all configs in the directory

**Tip**: The tool will show you a shell script example for batch JSON export if needed.

### Option 3: Interactive Demo

**When to use**: Learn about the analyzer's capabilities through guided examples

**Example workflow**:
1. Select option 3
2. Press Enter to advance through 7 different demo scenarios:
   - Basic configuration analysis
   - Security compliance checking
   - SIP account extraction
   - Line key configuration analysis
   - Feature compliance checking
   - Network configuration audit
   - JSON export for automation

**Duration**: ~5 minutes with pauses between demos

### Option 4: View Documentation

**When to use**: Access comprehensive documentation or quick reference guides

**Available documents**:
- `PHONE_CONFIG_ANALYZER_README.md` - Full documentation (500 lines)
- `PHONE_CONFIG_ANALYZER_QUICKREF.md` - Quick reference (300 lines)
- `PHONE_CONFIG_ANALYZER_SUMMARY.md` - Project overview

**Workflow**:
1. Select option 4
2. View list of available documentation
3. Enter filename to open (or 'no' to skip)
4. Document opens in default viewer

### Option 5: Back to Main Menu

Returns to the FreePBX Tools Manager main menu.

## Real-World Usage Examples

### Example 1: Analyze Phone Config After Provisioning

**Scenario**: You just provisioned a new Polycom VVX600 and want to verify its configuration.

```
1. Launch: python freepbx_tools_manager.py
2. Select: 7 (Phone Config Analyzer)
3. Select: 1 (Single config file)
4. Enter path: /tftpboot/0004f2123456.cfg
5. Export JSON: yes
6. Filename: vvx600_analysis.json
7. Export CSV: no
```

**Result**: 
- Terminal shows full analysis
- JSON file saved for records
- Security issues highlighted
- Feature compliance verified

### Example 2: Audit All Phone Configs

**Scenario**: Security audit requires checking all 50+ phone configs for weak passwords.

```
1. Launch: python freepbx_tools_manager.py
2. Select: 7 (Phone Config Analyzer)
3. Select: 2 (Directory of config files)
4. Enter path: /tftpboot/
5. Export each: yes
6. Output dir: security_audit_2025_11_08
```

**Result**:
- All configs analyzed
- Security issues for each phone reported
- JSON files saved in audit directory
- Can be reviewed or automated

### Example 3: Learn the Tool

**Scenario**: New team member needs to understand what the analyzer can do.

```
1. Launch: python freepbx_tools_manager.py
2. Select: 7 (Phone Config Analyzer)
3. Select: 3 (Run interactive demo)
4. Press Enter to advance through demos
```

**Result**:
- Hands-on learning with real examples
- See all capabilities in action
- Understand output format

### Example 4: Quick Reference Lookup

**Scenario**: Need to remember command syntax for batch processing.

```
1. Launch: python freepbx_tools_manager.py
2. Select: 7 (Phone Config Analyzer)
3. Select: 4 (View documentation)
4. Enter: PHONE_CONFIG_ANALYZER_QUICKREF.md
```

**Result**:
- Quick reference opens
- Find command examples
- Copy/paste for scripts

## Integration with Other Tools

### With FreePBX Deployment

After deploying tools to a server (Option 1), you can analyze configs:

```
1. Deploy tools → Select servers → Deploy
2. SSH to server (Option 6)
3. Copy configs: scp 123net@SERVER:/tftpboot/*.cfg ./configs/
4. Exit SSH
5. Phone Config Analyzer (Option 7)
6. Analyze directory: ./configs/
```

### With Version Check

Compare phone firmware versions with configs:

```
1. Run version check on servers
2. Phone Config Analyzer on configs
3. Cross-reference firmware vs configuration
4. Identify upgrade candidates
```

## Tips and Best Practices

### 1. Regular Audits
- Schedule weekly config audits
- Look for security issues
- Track configuration drift

### 2. Post-Provisioning Verification
- Always analyze after provisioning
- Verify VLAN settings
- Check feature enablement

### 3. Bulk Operations
- Use directory analysis for efficiency
- Export to JSON for automation
- Script repetitive tasks

### 4. Documentation
- Keep analysis reports
- Track configuration changes
- Document security fixes

### 5. Security Focus
- Review CRITICAL issues immediately
- Fix HIGH severity within 24 hours
- Monitor for exposed credentials

## Keyboard Shortcuts

In the FreePBX Tools Manager:
- `7` - Quick access to Phone Config Analyzer
- `5` then `7` - Exit back to main menu from analyzer
- `Ctrl+C` - Emergency exit (graceful)

## Output Interpretation

### Terminal Colors

- 🔴 **Red** = CRITICAL or errors (immediate action required)
- 🟡 **Yellow** = HIGH/MEDIUM severity (should be addressed)
- 🟢 **Green** = Good status or enabled features
- 🔵 **Cyan** = Informational sections
- 🟣 **Magenta** = Commands and examples

### Security Severity

| Level | Color | Action Required |
|-------|-------|----------------|
| CRITICAL | Red | Immediate fix |
| HIGH | Yellow | Fix within 24 hours |
| MEDIUM | Yellow | Fix within 1 week |
| LOW | White | Fix when convenient |

## Troubleshooting

### "File not found" error

**Solution**: 
- Use absolute paths: `C:\TFTP\config.xml` (Windows) or `/tftpboot/config.xml` (Linux)
- Check file exists: `dir` (Windows) or `ls` (Linux)
- Verify file permissions

### "No configuration data parsed"

**Solution**:
- Check file format (XML, CFG, CONF)
- Verify file encoding (UTF-8)
- Try opening file in text editor to verify contents

### Demo won't run

**Solution**:
- Ensure `phone_config_analyzer_demo.py` exists
- Run from correct directory
- Check Python version (3.6+ required)

### Documentation won't open

**Solution**:
- Windows: Manually open with Notepad++, VS Code, or browser
- Linux: Use `less` or `cat` to view
- Verify files exist in current directory

## Advanced: Automation Scripts

### Daily Security Audit

Create `daily_phone_audit.bat` (Windows):
```batch
@echo off
python phone_config_analyzer.py --directory C:\TFTP\ --json audit_%date:~-4,4%%date:~-10,2%%date:~-7,2%.json --no-color > audit.log
findstr /C:"CRITICAL" audit.log
if %errorlevel%==0 (
    echo CRITICAL ISSUES FOUND! | mail -s "Phone Security Alert" admin@example.com
)
```

### Weekly Report

Create `weekly_report.sh` (Linux):
```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
python phone_config_analyzer.py --directory /tftpboot/ \
    --json /var/log/phone_audit_$DATE.json \
    --csv /var/reports/phone_summary_$DATE.csv \
    --no-color > /var/log/phone_audit_$DATE.log

# Email report
mail -s "Weekly Phone Config Report" team@example.com < /var/log/phone_audit_$DATE.log
```

## Support

### Getting Help

1. **Documentation**: Option 7 → 4 (View documentation)
2. **Demo**: Option 7 → 3 (Interactive demo)
3. **Quick Reference**: `PHONE_CONFIG_ANALYZER_QUICKREF.md`
4. **Full README**: `PHONE_CONFIG_ANALYZER_README.md`

### Reporting Issues

Include in your report:
- Phone type (Polycom, Yealink, etc.)
- Config file sample (redact passwords!)
- Error message
- Python version
- Operating system

## Version History

### v1.0 (2025-11-08)
- Initial integration with FreePBX Tools Manager
- Menu option 7 added
- Submenu with 5 options
- Full documentation suite

## Next Steps

1. ✅ Try the interactive demo (Option 7 → 3)
2. ✅ Analyze a sample config (Option 7 → 1)
3. ✅ Read the quick reference (Option 7 → 4)
4. ✅ Set up automated audits
5. ✅ Share with team

---

**Remember**: The Phone Config Analyzer is just one tool in the FreePBX Tools suite. Use it alongside other options in the manager for comprehensive phone system management!
