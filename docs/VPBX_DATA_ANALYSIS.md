# VPBX Scraped Data Analysis - Phone System Intelligence

## What We Captured

The comprehensive scrape extracts detailed information about 123NET's hosted phone systems (VPBX instances) that can be invaluable for phone system analysis, troubleshooting, and infrastructure management.

## Data Structure Overview

### Main Table (table_data.csv)
**556 VPBX instances** with key metadata:
- **ID**: Unique VPBX identifier (6, 13, 19, etc.)
- **Handle**: System short name (VM7, BF7, CSU, etc.)
- **Company Name**: Customer name
- **IP Address**: System IP (205.251.183.x)
- **Status**: production_billed, testing, provisioning, decomissioned, etc.
- **FreePBX Version**: 12.0.76.6, 13.0.197.22, 15.0.23.25, etc.
- **Asterisk Version**: 12.8.1, 16.20.0, etc.
- **Devices**: Number of phones/endpoints
- **Switch**: Infrastructure location (VOIPSWITCH)
- **DeploymentID**: Unique deployment identifier
- **VM ID**: Virtual machine identifier
- **Call Center**: Whether Asternic/CallCenter is enabled

### Per-Entry Detailed Data (556 folders × 6 pages each)

#### 1. Detail Main Page (`detail_main.txt/html`)
- **System Configuration**:
  - System IP address
  - FTP credentials (HOST, USER, PASS)
  - REST API credentials
  - VM ID and Monitor info
  - Polycom firmware version options
  
- **Billing Information**:
  - Site codes and agent assignments
  - Bill start/stop dates
  - Charge types (instance, device, seat, addon)
  - Pricing models
  
- **Maintenance Schedule**:
  - Pending maintenance items
  - Recently completed maintenance
  - Due dates and descriptions

#### 2. Site Notes (`site_notes.txt/html`)
- Historical notes about the site
- Configuration changes
- Issues and resolutions
- Customer-specific requirements
- Timestamps and user attribution

#### 3. Site Specific Config (`site_specific_config.txt/html`)
- Custom configuration parameters
- Site-specific dial plans
- Custom features enabled
- Integration settings

#### 4. Edit/Device List (`edit_main.txt/html`)
**Critical for Phone Analysis** - Contains device inventory:

- **Device Properties for Each Phone**:
  - Device ID (unique identifier)
  - MAC address
  - Directory name
  - Main extension number
  - Make (polycom, cisco, yealink, grandstream, fanvil, algo)
  - Model (VVX400, VVX600, CP-7841, T54W, HT813, etc.)
  - Template assignment
  
- **Device Types Tracked**:
  - Desk phones (Polycom VVX series, Cisco 78xx/88xx, Yealink T-series)
  - Conference phones (Polycom Trio 8500, Cisco CP960, Yealink CP920)
  - DECT wireless (Yealink W56P, W60P)
  - ATAs (Cisco SPA-122, GrandStream HT813)
  - Door phones/speakers (Algo 8180, 8186, 8301, Fanvil i12)
  - Softphones (Standalone, Bundled)
  - Directory/Sidecar entries

- **Device Options**:
  - Attendant status
  - D60 expansion module
  - Softphone provisioning status
  - Site code assignments

#### 5. View Config (`view_config.txt/html`)
**Detailed Phone Configuration** - Shows actual provisioning data:

- **SIP Registration Details**:
  - `reg.1.auth.userid` - SIP username
  - `reg.1.address` - SIP server address
  - `reg.1.auth.password` - SIP password
  - `reg.1.displayname` - Display name
  - `reg.1.line.1.label` - Line label
  
- **Phone-Specific Attributes**:
  - Transfer type settings
  - Custom configuration keys
  - Arbitrary attribute overrides
  
- **Log Files Access**:
  - Application logs (app.log)
  - Boot logs (boot.log)
  - Access logs
  - Timestamps and file locations
  
- **Reload History**:
  - Device reload requests
  - Timestamps
  - Completion status
  - Comments

#### 6. Bulk Attribute Edit (`bulk_attribute_edit.txt/html`)
- Mass configuration changes interface
- Template-based provisioning
- Attribute propagation tools

## How This Helps Phone Analysis

### 1. **Inventory Management**
- Track all phones across 556 systems
- Identify phone models and firmware versions
- Find MAC addresses for specific devices
- Count devices per customer

### 2. **Troubleshooting**
- Access device configuration details
- Review log files for specific phones
- Check SIP credentials and registration settings
- Review reload history for problematic devices
- Examine site notes for known issues

### 3. **Migration Planning**
- Identify systems on old FreePBX/Asterisk versions
- Find phones needing firmware updates
- Assess deployment complexity by device count
- Plan upgrades based on device compatibility

### 4. **Security Audits**
- Review SIP credential patterns
- Check for default passwords
- Audit REST API access
- Review FTP configurations

### 5. **Infrastructure Analysis**
- Map systems to switch locations
- Identify VM assignments
- Track deployment IDs
- Monitor system status distribution

### 6. **Customer Support**
- Quick access to customer's phone inventory
- Review billing and site codes
- Check maintenance history
- Access system credentials for remote support

### 7. **Reporting & Analytics**
```python
# Example: Analyze phone models across all systems
import csv
import os
from collections import Counter

# Count phone models
phone_models = Counter()

# Parse all edit_main.txt files
for entry_dir in os.listdir('vpbx_comprehensive'):
    if entry_dir.startswith('entry_'):
        edit_file = f'vpbx_comprehensive/{entry_dir}/edit_main.txt'
        if os.path.exists(edit_file):
            with open(edit_file) as f:
                content = f.read()
                # Extract model information
                # ... parsing logic ...
                
# Results:
# VVX400: 1,234 phones
# VVX600: 567 phones
# Cisco CP-7841: 234 phones
# etc.
```

## Key Data Points by Category

### System-Level Data
- 556 total VPBX instances
- FreePBX versions: 12.x, 13.x, 15.x, 16.x
- Asterisk versions: 12.8.1, 16.20.0, etc.
- Status distribution: production_billed, testing, provisioning, decomissioned

### Device-Level Data
- **Makes**: Polycom, Cisco, Yealink, GrandStream, Fanvil, Algo
- **Categories**: Desk phones, conference phones, wireless, ATAs, door stations, softphones
- **Configurations**: Templates, extensions, MAC addresses, SIP credentials

### Operational Data
- Billing codes and agents
- Maintenance schedules
- Change history via site notes
- Log file access for debugging

## Integration with Existing FreePBX Tools

This data complements your existing tools:

### With `freepbx_phone_analyzer.py`
- Cross-reference MAC addresses
- Validate phone configurations
- Compare provisioned vs actual devices

### With `freepbx_dump.py`
- Correlate web admin data with MySQL data
- Validate consistency
- Fill gaps in database queries

### With `freepbx_callflow_graphV2.py`
- Add device context to call flows
- Map extensions to physical phones
- Identify device-specific routing

### With `freepbx_cdr_analyzer.py`
- Link CDR data to specific devices
- Identify problematic phones by call quality
- Track device usage patterns

## Next Steps for Analysis

### 1. Build Phone Inventory Database
```python
# Create comprehensive phone database
# Link MAC → Model → Extension → VPBX → Customer
```

### 2. Version Compliance Checker
```python
# Check against version_policy.json
# Identify systems needing updates
# Flag EOL firmware versions
```

### 3. Configuration Validator
```python
# Parse SIP credentials
# Check for weak passwords
# Validate dial plan consistency
```

### 4. Phone Health Dashboard
```python
# Aggregate log files
# Track reload frequency
# Identify problematic devices
```

### 5. Migration Tool
```python
# Generate migration plans
# Create device mapping spreadsheets
# Automate configuration backups
```

## Sample Queries You Can Now Answer

1. **"How many VVX400 phones do we have deployed?"**
   - Parse all edit_main.txt files, count Model=VVX400

2. **"Which systems are still on FreePBX 12?"**
   - Filter table_data.csv where FreePBX column starts with "12."

3. **"What's the SIP password for extension 222 on VM7?"**
   - Look in entry_6/view_config.txt for reg.1.auth.password

4. **"Show me all Algo door phones deployed"**
   - Parse edit_main.txt files for Make=Algo

5. **"Which sites have pending maintenance?"**
   - Parse detail_main.txt for Pending Maintenance sections

6. **"What firmware version is customer X using?"**
   - Check detail_main.txt for "Poly Firmware ver" setting

7. **"How many devices does the average customer have?"**
   - Average the "Devices" column in table_data.csv

8. **"Which systems have call center enabled?"**
   - Filter table_data.csv where "Call Center" is not empty

## Storage & Performance

- **Test output**: 2 entries = ~50KB per entry = 100KB total
- **Full output estimate**: 556 entries × 50KB = ~28MB
- **With HTML**: ~2-3x larger = ~75MB total
- **Search performance**: Use `grep`, Python pandas, or SQLite import for fast queries

## Conclusion

This comprehensive scrape provides a **complete phone system inventory and configuration database** that was previously only accessible through manual web interface navigation. You now have:

- ✅ Complete device inventory (make, model, MAC, extension)
- ✅ SIP configuration details (credentials, server addresses)
- ✅ Historical notes and maintenance records
- ✅ Billing and customer information
- ✅ Version tracking (FreePBX, Asterisk, firmware)
- ✅ Log file access paths
- ✅ System status and deployment tracking

This data enables automated analysis, reporting, troubleshooting, and infrastructure management that would otherwise require hours of manual clicking through the web interface.
