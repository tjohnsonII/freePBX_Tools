# FreePBX Tools - AI Agent Instructions

## Project Overview

This is a suite of diagnostic and visualization tools for FreePBX/Asterisk phone systems. The project has two main components:

1. **Core Tools** (`freepbx-tools/`): Installation package with utilities for FreePBX analysis
2. **Orchestration Scripts** (root): Multi-server deployment and report aggregation tools

## Architecture

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

- **Python 3.6+ compatibility**: Uses `universal_newlines=True` instead of `text=True` for subprocess
- **MySQL CLI access**: All database queries use `mysql -NBe` command, not Python drivers
- **Graphviz**: Required for SVG call-flow generation (`dot` command)
- **Standard paths**: Tools install to `/usr/local/123net/freepbx-tools/`, output to `/home/123net/callflows/`

## Development Patterns

### Database Access Pattern
```python
# Always use subprocess.run with mysql CLI
def q(sql, socket=None, user="root", password=None):
    cmd = ["mysql", "-NBe", sql, "asterisk", "-u", user]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
```

### Schema Adaptation
Tools handle FreePBX version differences by checking table/column existence:
```python
def has_table(t, **kw): return t in get_tables(**kw)
def first_table(options, **kw): # find first existing table from list
```

### Multi-Server Orchestration
Root-level scripts deploy tools across server fleets:
- **`run_all.sh`**: Parallel execution across hosts from `ProductionServers.txt`
- **Pattern**: `scp` script → `ssh` execute → `scp` results back to `./reports/`

### Error Handling Convention
All scripts use bash `set -euo pipefail` and Python graceful degradation (return empty lists/dicts on DB errors).

## Key Workflows

### Installation
```bash
sudo ./freepbx-tools/install.sh  # Installs deps, creates symlinks, runs smoke tests
```

### Single Host Analysis
```bash
freepbx-callflows           # Interactive menu
freepbx-dump --out file.json # Raw data export
freepbx-diagnostic          # Full system report
```

### Fleet Operations
```bash
./run_all.sh ProductionServers.txt  # Deploy to all hosts
./summarize.sh                       # Aggregate reports
```

## File Conventions

- **Executable naming**: All tools have both friendly names (`freepbx-*`) and legacy names (`asterisk-*`)
- **Output locations**: JSON/SVG to `/home/123net/callflows/`, diagnostics to working directory
- **Config files**: `version_policy.json` defines acceptable FreePBX/Asterisk major versions
- **Host lists**: CSV/TSV files with IP addresses, first column is always the target host

## When Modifying Code

1. **Maintain Python 3.6 compatibility** - test on EL7 systems
2. **Preserve MySQL CLI pattern** - don't introduce Python DB drivers
3. **Handle schema variations** - FreePBX table structures change between versions
4. **Test installation path** - scripts assume `/usr/local/123net/freepbx-tools/` structure
5. **Validate on actual FreePBX** - tools interact with live phone system databases

## Critical Files to Understand

- `freepbx_dump.py`: Master data model and schema handling
- `install.sh`: Dependency management and EL7/8/9 compatibility
- `version_policy.json`: Version compliance rules
- `run_all.sh`: Multi-server deployment pattern