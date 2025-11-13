# Repository Organization

## Directory Structure

```
freepbx-tools/
├── cli-tools/              # Terminal programs/scripts for command-line operations
├── web-app/                # Web application programs/scripts (Flask app)
├── database/               # Database programs/scripts and data
├── docs/                   # Information, README files, and documentation
├── data/                   # Internal data documents (CSVs, analysis outputs)
├── freepbx-tools/          # Core FreePBX diagnostic tools (deployed to servers)
└── [root files]            # Base necessary files (config, .gitignore, etc.)
```

## Directory Contents

### `cli-tools/` - Terminal Programs/Scripts
Command-line tools for local execution:
- `deploy_freepbx_tools.py` - Deploy tools to remote servers
- `deploy_uninstall_tools.py` - Uninstall tools from remote servers
- `freepbx_tools_manager.py` - CLI menu interface for deployments
- `phone_config_analyzer.py` - Analyze phone configuration files
- `analyze_vpbx_phone_configs.py` - Batch phone config analysis
- Helper scripts for extraction and analysis

### `web-app/` - Web Application Programs/Scripts
Flask-based web interface:
- `web_manager.py` - Main Flask application
- `web_requirements.txt` - Python dependencies for web app
- `templates/` - HTML templates
- `static/` - Static assets (CSS, JS, images)

### `database/` - Database Programs/Scripts & Data
VPBX database tools and queries:
- `vpbx_data.db` - SQLite database with VPBX information
- `create_vpbx_database.py` - Database creation script
- `query_vpbx.py` - Database query utilities
- `vpbx_query_interactive.py` - Interactive query interface
- `queries/` - SQL query templates

### `docs/` - Information & README Documentation
All markdown documentation files:
- `README.md` - Main project documentation
- `COMPREHENSIVE_SCRAPING.md` - Data scraping guide
- `LOG_ANALYSIS.md` - Log analysis documentation
- `MYSQL_DATABASE_ACCESS.md` - Database access guide
- `PHONE_CONFIG_ANALYSIS.md` - Phone config analysis guide
- `SECURITY.md` - Security documentation
- `WEB_INTERFACE_README.md` - Web app documentation
- Other markdown documentation files

### `data/` - Internal Data Documents
Generated data and analysis outputs:
- `server-lists/` - Server inventory files (ProductionServers.txt, etc.)
- `analysis-output/` - JSON/CSV analysis results
- Company mappings, credentials exports, etc.
- Test outputs and reports

### `freepbx-tools/` - Core FreePBX Tools (Deployed Package)
The installable package that gets deployed to FreePBX servers:
- `bin/` - Diagnostic scripts (freepbx_dump.py, callflow generator, etc.)
- `install.sh` - Installation script
- `version_policy.json` - Version compliance rules
- Supporting scripts and tools

### Root Directory - Base Necessary Files
Essential configuration and control files:
- `.gitignore` - Git exclusions
- `config.py` / `config.example.py` - Configuration files
- `requirements.txt` - Python dependencies
- `run_all.sh` / `summarize.sh` - Orchestration scripts
- Repository metadata files

## Quick Reference

**To deploy tools to servers:** Use `cli-tools/deploy_freepbx_tools.py` or `web-app/web_manager.py`

**To analyze phone configs:** Use `cli-tools/phone_config_analyzer.py`

**To query VPBX data:** Use `database/query_vpbx.py` or the web interface

**To start web interface:** `cd web-app && python web_manager.py`

**To install on FreePBX server:** `cd freepbx-tools && sudo ./install.sh`
