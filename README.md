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

> **🔒 Security Note**: This repository contains NO passwords or sensitive credentials. All authentication is handled via secure environment variables or interactive prompts. See [SECURITY.md](SECURITY.md) for best practices.

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
| `freepbx-callflow-validator` | **NEW:** Validate call flows with real call simulation | Console output + JSON results |

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
- **Windows machine** for deployment (PowerShell)
- **SSH access** to FreePBX server 
- **Python 3.6+** on FreePBX server
- **Asterisk** running on target server
- **MySQL CLI access** on FreePBX server
- **Root access** on FreePBX server

**Optional (for GUI comparison features):**
- Python packages: `beautifulsoup4`, `requests` (automatically installed by `install.sh`)

### Quick Deployment (Recommended)

#### Option 1: Environment Variables (Most Secure)
```powershell
# Set credentials as environment variables (Windows PowerShell)
$env:FREEPBX_USER_PASSWORD = "your-123net-password"
$env:FREEPBX_ROOT_PASSWORD = "***REMOVED***"

# Deploy everything in one command
.\deploy_freepbx_tools.ps1
```

#### Option 2: Interactive Deployment (Secure Prompts)
```powershell
# Run without passwords - will prompt securely
.\deploy_freepbx_tools.ps1
```

#### What the Deployment Does:
1. **Upload** entire `freepbx-tools` folder via SCP
2. **SSH** into server as 123net user
3. **Switch to root** using `su root` command
4. **Run bootstrap.sh** to make all scripts executable  
5. **Run install.sh** to complete installation
6. **Create symlinks** in `/usr/local/bin/` for easy access
7. **Verify installation** with automatic tests

### Manual Installation (Alternative)
If you prefer manual control:

```bash
# 1. Upload files manually via SCP or WinSCP
# 2. SSH into the server
ssh 123net@69.39.69.102
su root

# 3. Navigate to uploaded directory and install
cd /path/to/freepbx-tools
./bootstrap.sh    # Make everything executable
./install.sh      # Install with dependencies and symlinks
```

### SSH Key Setup (Optional)
For passwordless authentication:
```bash
./freepbx-tools/bin/setup_ssh_auth.sh
```

## 🎯 Quick Start Guide

### Test Server Configuration
- **IP**: 69.39.69.102
- **User**: 123net
- **Authentication**: Secure passwords (see SECURITY.md for best practices)

### Step 1: Deploy and Install
```powershell
# One-command deployment from Windows
$env:FREEPBX_USER_PASSWORD = "your-123net-password"
$env:FREEPBX_ROOT_PASSWORD = "***REMOVED***"
.\deploy_freepbx_tools.ps1
```

### Step 2: Access the Interactive Menu
```bash
# SSH into the server and run the main menu
ssh 123net@69.39.69.102
freepbx-callflows

# Select option 11 for "📞 Call Simulation & Validation"
```

### Step 3: Test Call Flow Validation
```bash
# Complete workflow from the menu:
# 1. Generate ASCII call flows (option 10)
# 2. Test with real calls (option 11)
# 3. Validate accuracy and get scores

# Or use command line directly:
freepbx-callflow-validator 2485815200
```

## 💻 Usage Examples

### Interactive Menu (Recommended)
```bash
# Access the main menu system
freepbx-callflows

# Navigate to call simulation (option 11):
📞 Call Simulation Options:
 1) Test specific DID with call simulation
 2) Validate call flow accuracy for DID  
 3) Test extension call
 4) Test voicemail call
 5) Test playback application
 6) Run comprehensive call validation
 7) Monitor active call simulations
```

### Command Line Usage
```bash
# Direct call simulation via Python
python3 /usr/local/123net/freepbx-tools/bin/call_simulator.py --did 2485815200
python3 /usr/local/123net/freepbx-tools/bin/call_simulator.py --extension 4220

# Call flow validation
python3 /usr/local/123net/freepbx-tools/bin/callflow_validator.py 2485815200

# Real-time call monitoring
/usr/local/123net/call-simulation/simulate_calls.sh monitor
```

### Complete Validation Workflow
```bash
# Step 1: Generate call flow prediction
freepbx-ascii-callflow --did 2485815200

# Step 2: Simulate actual call and compare
freepbx-callflow-validator 2485815200

# Step 3: View results with accuracy scoring
# Results show predicted vs actual routing with percentage accuracy
```

### Call File Example
The system creates proper Asterisk call files:
```
Channel: local/7140@from-internal
CallerID: 7140
WaitTime: 10
Context: from-internal
Extension: s
Priority: 1
MaxRetries: 0
Account: 4220
Application: Playback
Data: zombies
Archive: no
```

### Comprehensive Testing
```bash
# Test multiple DIDs with accuracy scoring (via menu system)
freepbx-callflows
# Select option 11 → option 6 for comprehensive validation

# Or via command line:
python3 /usr/local/123net/freepbx-tools/bin/callflow_validator.py 2485815200 3134489750 9062320010
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

For a unified “suite” workflow (multi-root workspace + common VS Code Tasks), see [docs/SUITE_DEV.md](docs/SUITE_DEV.md).

### Suite Layout (Monorepo)
This repository is a *suite* of tools. The safest way to keep it maintainable is to treat each major tool as a self-contained subproject with its own dependencies and run commands from that subproject’s folder.

Key subprojects in this repo:
- **Core FreePBX tools (installer + CLI utilities):** `freepbx-tools/`
- **Traceroute Visualizer (Next.js UI):** `traceroute-visualizer-main/traceroute-visualizer-main/`
- **Traceroute Visualizer backend deps (FastAPI dev server option):** `traceroute-visualizer-main/backend/`
- **Web scraping utilities:** `webscraper/`

Recommended conventions:
- **Python:** use a separate virtual environment per subproject (e.g. `webscraper/.venv`, `traceroute-visualizer-main/backend/.venv`) to avoid dependency collisions.
- **Node/Next.js:** keep `node_modules/` and one lockfile next to that project’s `package.json`.
- **Config:** store machine-local settings in `.env.local` or `*.example` templates; avoid committing secrets.

### File Structure
```
freepbx-tools/
├── install.sh                    # Main installation script
├── bootstrap.sh                  # Make scripts executable
├── version_policy.json           # Version compliance rules
└── bin/
    ├── freepbx_dump.py           # Core data extractor
    ├── freepbx_callflow_menu.py  # Interactive menu system
    ├── call_simulator.py         # Call simulation engine
    ├── callflow_validator.py     # Validation system
    ├── simulate_calls.sh         # Call monitoring script
    └── ...

deploy_freepbx_tools.ps1          # Windows deployment script
SECURITY.md                       # Security best practices
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

### From Development Machine to Testing
1. **Deploy**: `.\deploy_freepbx_tools.ps1` (from Windows)
2. **Connect**: `ssh 123net@69.39.69.102`
3. **Launch menu**: `freepbx-callflows`
4. **Analyze**: Option 10 (ASCII call flow predictions)
5. **Test**: Option 11 (Call simulation and validation)
6. **Monitor**: Option 7 (Real-time call monitoring)
7. **Results**: View accuracy scores and detailed analysis

### Real-World Testing Process
```bash
# Generate prediction for DID
freepbx-ascii-callflow --did 2485815200

# Simulate actual calls and compare
freepbx-callflow-validator 2485815200

# Results show:
# ✅ Predicted: IVR → Queue → Agent
# ✅ Actual:    IVR → Queue → Agent  
# 📊 Accuracy: 100%
```

This integrated approach provides both visualization and validation of FreePBX call flows, ensuring your diagnostic tools accurately reflect real-world call behavior.

---

## 📝 Version History

- **v2.0**: Added comprehensive call simulation and validation system
- **v1.0**: Core FreePBX diagnostic and visualization tools

For issues, feature requests, or contributions, please refer to the project repository.