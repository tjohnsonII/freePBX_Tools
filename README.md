# FreePBX Tools - Diagnostic & Call Simulation Suite

A comprehensive suite of diagnostic and call simulation tools for FreePBX/Asterisk phone systems. This project includes both core diagnostic tools and an advanced call simulation system for validating call flow behavior.

## 📋 Table of Contents

- [Quick Reference](#-quick-reference)
- [Core Features](#-core-features)
- [Call Simulation System](#-call-simulation-system)
- [Installation & Deployment](#-installation--deployment)
- [Quick Start Guide](#-quick-start-guide)
- [Usage Examples](#-usage-examples)
- [Architecture](#-architecture)
- [Development](#-development)

## ⚡ Quick Reference

| Command | Purpose | Output Location |
|---------|---------|----------------|
| `freepbx-callflows` | Interactive menu: snapshot, diagrams, TC status, diagnostics | `/home/123net/callflows/` |
| `freepbx-dump` | Take a JSON snapshot of FreePBX DB | `freepbx_dump.json` |
| `freepbx-render` | Render call-flow diagrams from last snapshot | `callflow_<DID>.svg` |
| `freepbx-tc-status` | Show Time Condition override state + last feature code use | Console output |
| `freepbx-module-analyzer` | Analyze all FreePBX modules and their configurations | Console output / JSON |
| `freepbx-ascii-callflow` | Generate ASCII art call flow diagrams | Console output |
| `freepbx-diagnostic` | Full system + Asterisk diagnostic | `full_diagnostic_<timestamp>.txt` |
| `freepbx-version-check` | Compare FreePBX/Asterisk versions to policy | Console output |

## 📈 Core Features

### 🔀 Call-Flow Generator
Renders inbound routes, IVRs, time conditions, queues, etc. into `.svg` diagrams and ASCII art for console/email viewing.

### 📦 Snapshot Utility
Exports FreePBX config to normalized JSON for offline review and consistency across versions.

### 🩺 Full Diagnostics
Collects system and PBX state into comprehensive text reports.

### 📊 Time Condition Status Tool
Shows overrides + last feature code dial from CDRs.

### 🔧 Module Analyzer
Comprehensive analysis of all FreePBX modules and their configurations.

### 📞 **NEW: Call Simulation & Validation**
Advanced call simulation system that creates real Asterisk call files to test and validate call flow predictions.

## 📞 Call Simulation System

### Overview
The call simulation suite provides comprehensive call testing and validation tools for FreePBX systems:

1. **Simulate actual calls** using Asterisk call files
2. **Monitor call behavior** in real-time  
3. **Validate call flow predictions** against actual routing
4. **Test different scenarios** (DIDs, extensions, voicemail, etc.)

### Core Tools

#### `call_simulator.py` - Call Simulation Engine
- Generate and execute Asterisk call files for testing
- DID routing simulation, extension calling tests, voicemail tests
- Application playback tests and comprehensive test suites
- Results logging and analysis

#### `simulate_calls.sh` - User-Friendly Wrapper
- Easy-to-use interface with prerequisites checking
- Real-time monitoring and call file cleanup
- Verbose logging and safety checks

#### `callflow_validator.py` - Validation Engine
- Compare predicted call flows with actual Asterisk behavior
- Component detection validation and extension routing verification
- Scoring system (0-100%) with detailed mismatch analysis

### Integrated Menu System
The call simulation is fully integrated into the main FreePBX menu (`freepbx-callflows` option 11):

```
📞 Call Simulation Options:
 1) Test specific DID with call simulation
 2) Validate call flow accuracy for DID  
 3) Test extension call
 4) Test voicemail call
 5) Test playback application
 6) Run comprehensive call validation
 7) Monitor active call simulations
 8) Return to main menu
```

## 🚀 Installation & Deployment

### Prerequisites
- SSH access to FreePBX server with key authentication
- Python 3.6+ installed locally
- Asterisk running on target server
- MySQL CLI access on FreePBX server

**Optional (for GUI comparison features):**
- Python packages: `beautifulsoup4`, `requests` (automatically installed by `install.sh`)
- For manual installation: `pip3 install beautifulsoup4 requests`

### Step 1: Deploy the Core Tools
```bash
# Install FreePBX diagnostic tools
sudo ./freepbx-tools/install.sh
```

### Step 2: Deploy Call Simulation Suite
```bash
# From your local machine, deploy to FreePBX server
./deploy_call_simulation.sh <SERVER_IP> <SSH_USER>

# Example:
./deploy_call_simulation.sh 69.39.69.102 123net
```

This will:
- Copy all scripts to `/usr/local/123net/freepbx-tools/bin/`
- Create convenient symlinks in `/usr/local/bin/`
- Verify prerequisites (Asterisk, MySQL, etc.)
- Run basic functionality tests

### Step 3: Set Up SSH Keys (if needed)
```bash
./freepbx-tools/bin/setup_ssh_auth.sh
```

## 🎯 Quick Start Guide

### Test Server Configuration
- **IP**: 69.39.69.102
- **User**: 123net
- **Password**: dH10oQW6jQ2rc&402B%e *(for initial setup only)*

### Step 1: Test Connectivity
```bash
./test_connectivity.sh
```

### Step 2: Access the Integrated Menu
```bash
ssh 123net@69.39.69.102
freepbx-callflows
# Select option 11 for "📞 Call Simulation & Validation"
```

### Step 3: Test Call Flow Validation
```bash
# Complete workflow:
# 1. Generate ASCII call flows (option 10)
# 2. Test with real calls (option 11)
# 3. Validate accuracy and get scores

# Or use command line:
freepbx-callflow-validator 2485815200
```

## 💻 Usage Examples

### Basic Call Simulation
```bash
# Test a specific DID
./freepbx-tools/bin/simulate_calls.sh test-did 2485815200

# Test an extension
./freepbx-tools/bin/simulate_calls.sh test-extension 4220

# Test voicemail
./freepbx-tools/bin/simulate_calls.sh test-voicemail 4220

# Monitor active calls
./freepbx-tools/bin/simulate_calls.sh monitor
```

### Validation Workflow
```bash
# Step 1: Generate call flow prediction
python3 /usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py --did 2485815200

# Step 2: Simulate actual call
python3 /usr/local/123net/freepbx-tools/bin/call_simulator.py --did 2485815200

# Step 3: Validate accuracy
python3 /usr/local/123net/freepbx-tools/bin/callflow_validator.py 2485815200
```

### Call File Example
The system creates proper Asterisk call files:
```
Channel: local/*45@from-internal
CallerID: 7140
WaitTime: 10
MaxRetries: 0
Account: 4220
Application: Playback
Data: zombies
Archive: no
```

### Comprehensive Testing
```bash
# Run full validation suite
./freepbx-tools/bin/comprehensive_test.sh

# Test multiple DIDs with accuracy scoring
python3 /usr/local/123net/freepbx-tools/bin/validate_callflows.py 2485815200 3134489750 9062320010
```

## 🏗️ Architecture

### Data Flow Pattern
All tools follow a consistent 3-stage pipeline:
1. **Extract**: Query FreePBX MySQL database via CLI (no Python DB drivers)
2. **Transform**: Normalize data across FreePBX schema versions  
3. **Output**: Generate JSON snapshots, SVG diagrams, or text reports

### Key Components
- **`freepbx_dump.py`**: Core data extractor - queries MySQL CLI to create normalized JSON snapshots
- **`freepbx_callflow_graphV2.py`**: SVG diagram generator using Graphviz dot format
- **`freepbx_callflow_menu.py`**: Interactive CLI menu wrapper for all tools
- **`asterisk-full-diagnostic.sh`**: System diagnostics collector
- **`version_check.py`**: Policy compliance checker against `version_policy.json`

### Critical Dependencies
- **Python 3.6+ compatibility**: Uses `universal_newlines=True` for subprocess
- **MySQL CLI access**: All database queries use `mysql -NBe` command
- **Graphviz**: Required for SVG call-flow generation (`dot` command)
- **Standard paths**: Tools install to `/usr/local/123net/freepbx-tools/`

## 🔧 Development

### File Structure
```
freepbx-tools/
├── install.sh              # Main installation script
├── version_policy.json     # Version compliance rules
└── bin/
    ├── freepbx_dump.py           # Core data extractor
    ├── freepbx_callflow_menu.py  # Interactive menu system
    ├── call_simulator.py         # Call simulation engine
    ├── callflow_validator.py     # Validation system
    └── ...
```

### Database Access Pattern
```python
# Always use subprocess.run with mysql CLI
def q(sql, socket=None, user="root", password=None):
    cmd = ["mysql", "-NBe", sql, "asterisk", "-u", user]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
```

### Multi-Server Orchestration
Root-level scripts deploy tools across server fleets:
- **`run_all.sh`**: Parallel execution across hosts from `ProductionServers.txt`
- **Pattern**: `scp` script → `ssh` execute → `scp` results back to `./reports/`

## 📊 Testing & Validation Features

### Edge Case Testing
- Non-existent DIDs
- Circular references  
- Missing destinations
- Invalid time conditions

### Performance Metrics
- Processing time per DID
- Memory usage tracking
- Database query efficiency
- Call simulation execution time

### Accuracy Scoring
- Database validation (0-100%)
- Schema consistency checks
- Call flow complexity analysis
- Component detection verification

## 🎯 Complete Workflow Example

1. **SSH to FreePBX server**: `ssh 123net@69.39.69.102`
2. **Launch menu**: `freepbx-callflows`
3. **View call flows**: Option 10 (ASCII call flow predictions)
4. **Test with real calls**: Option 11 (Call simulation submenu)
5. **Validate accuracy**: Compare predictions vs actual behavior
6. **Get scoring**: Receive 0-100% accuracy rating

This integrated approach provides both visualization and validation of FreePBX call flows, ensuring your diagnostic tools accurately reflect real-world call behavior.

---

## 📝 Version History

- **v2.0**: Added comprehensive call simulation and validation system
- **v1.0**: Core FreePBX diagnostic and visualization tools

For issues, feature requests, or contributions, please refer to the project repository.