#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_module_analyzer.py
--------------------------
Comprehensive FreePBX module status and configuration analysis tool.
Evaluates all installed modules and their configurations.
✓ Python 3.6 compatible (uses mysql CLI via subprocess; no external modules).

VARIABLE MAP (Key Script Variables)
-----------------------------------
Colors         : ANSI color codes for CLI output
ASTERISK_DB    : Name of the Asterisk database
DEFAULT_SOCK   : Default MySQL socket path
args           : Parsed command-line arguments
db_socket      : MySQL socket path (if used)
db_user        : MySQL username
db_password    : MySQL password (if used)
output_file    : Path to output report file
modules        : List of installed FreePBX modules
module_data    : Parsed data for each module
summary_stats  : Dictionary of computed summary statistics

Key Function Arguments:
-----------------------
sql            : SQL query string
module         : Module name
row            : Row of data from DB
args           : Parsed command-line arguments

See function docstrings for additional details on arguments and return values.

    FUNCTION MAP (Major Functions)
    -----------------------------
    print_header              : Print professional header banner
    run_mysql_query           : Run a MySQL query using the CLI
    get_installed_modules     : Get list of installed FreePBX modules
    analyze_module            : Analyze a specific module's configuration
    analyze_all_modules       : Analyze all installed modules
    print_summary             : Print summary statistics to terminal
    write_report              : Write analysis report to file
    main                     : CLI entry point, parses args and runs analysis
"""

import argparse, json, os, subprocess, sys, time, re
from collections import defaultdict

# ANSI Color codes
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

def print_header():
    """Print professional header banner"""
    print(Colors.CYAN + Colors.BOLD + """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║          🔧  FreePBX Module Configuration Analyzer            ║
║                                                               ║
║            Comprehensive Module Status & Settings             ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """ + Colors.ENDC)

ASTERISK_DB = "asterisk"
DEFAULT_SOCK = "/var/lib/mysql/mysql.sock"

# ---------------------------
# mysql helpers (3.6 friendly)
# ---------------------------

def run_mysql(sql, socket=None, user="root", password=None, db=ASTERISK_DB):
    """Run a SQL statement via mysql CLI and return stdout as text."""
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    cmd = ["mysql", "-BN"]
    if user:
        cmd += ["--user", str(user)]
    if socket:
        cmd += ["--socket", str(socket)]
    if db:
        cmd += [str(db)]
    cmd += ["-e", sql]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    if p.returncode != 0:
        return ""
    return p.stdout

def run_command(cmd):
    """Run a shell command and return stdout."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, shell=True)
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except Exception as e:
        return "", str(e), 1

def rows_as_dicts(sql, cols, **kw):
    """Run a SELECT that returns exactly len(cols) columns -> list[dict]."""
    out = run_mysql(sql, **kw).rstrip("\n")
    if not out:
        return []
    dicts = []
    for line in out.split("\n"):
        parts = line.split("\t")
        parts = (parts + [""] * len(cols))[:len(cols)]
        dicts.append(dict(zip(cols, parts)))
    return dicts

def get_tables(**kw):
    return set(run_mysql("SHOW TABLES;", **kw).split())

def has_table(t, **kw): 
    return t in get_tables(**kw)

# ---------------------------
# Module Analysis Functions
# ---------------------------

def get_freepbx_modules(**kw):
    """Get all FreePBX modules with their status and versions."""
    if not has_table("modules", **kw):
        return []
    
    sql = """
        SELECT modulename, version, status, enabled, installed, 
               COALESCE(canbeuninstalled,'') as canbeuninstalled,
               COALESCE(canbeinstalled,'') as canbeinstalled,
               COALESCE(canbeenabled,'') as canbeenabled,
               COALESCE(canbedisabled,'') as canbedisabled,
               COALESCE(candisable,'') as candisable,
               COALESCE(canuninstall,'') as canuninstall
        FROM modules 
        ORDER BY modulename;
    """
    return rows_as_dicts(sql, [
        "modulename", "version", "status", "enabled", "installed",
        "canbeuninstalled", "canbeinstalled", "canbeenabled", 
        "canbedisabled", "candisable", "canuninstall"
    ], **kw)

def analyze_core_modules(**kw):
    """Analyze core FreePBX modules and their configurations."""
    analysis = {}
    
    # Extensions/Users
    if has_table("users", **kw):
        users = rows_as_dicts(
            "SELECT extension, name, voicemail, outboundcid FROM users WHERE extension != '';",
            ["extension", "name", "voicemail", "outboundcid"], **kw
        )
        analysis["extensions"] = {
            "count": len(users),
            "with_voicemail": len([u for u in users if u["voicemail"] == "enabled"]),
            "sample": users[:5]
        }
    
    # Trunks
    if has_table("trunks", **kw):
        trunks = rows_as_dicts(
            "SELECT trunkid, name, tech, disabled FROM trunks;",
            ["trunkid", "name", "tech", "disabled"], **kw
        )
        analysis["trunks"] = {
            "count": len(trunks),
            "enabled": len([t for t in trunks if t["disabled"] != "1"]),
            "by_tech": {}
        }
        for trunk in trunks:
            tech = trunk.get("tech", "unknown")
            if tech not in analysis["trunks"]["by_tech"]:
                analysis["trunks"]["by_tech"][tech] = 0
            analysis["trunks"]["by_tech"][tech] += 1
    
    # Inbound Routes
    if has_table("incoming", **kw):
        inbound_count = len(rows_as_dicts("SELECT extension FROM incoming;", ["extension"], **kw))
        analysis["inbound_routes"] = {"count": inbound_count}
    
    # Outbound Routes
    if has_table("outbound_routes", **kw):
        outbound_count = len(rows_as_dicts("SELECT route_id FROM outbound_routes;", ["route_id"], **kw))
        analysis["outbound_routes"] = {"count": outbound_count}
    
    # Queues
    if has_table("queues_config", **kw):
        queues = rows_as_dicts(
            "SELECT extension, descr FROM queues_config;",
            ["extension", "descr"], **kw
        )
        analysis["queues"] = {
            "count": len(queues),
            "sample": queues[:3]
        }
    
    # Ring Groups
    if has_table("ringgroups", **kw):
        rg_count = len(rows_as_dicts("SELECT grpnum FROM ringgroups;", ["grpnum"], **kw))
        analysis["ringgroups"] = {"count": rg_count}
    
    # IVRs
    if has_table("ivr_details", **kw):
        ivr_count = len(rows_as_dicts("SELECT ivr_id FROM ivr_details;", ["ivr_id"], **kw))
        analysis["ivrs"] = {"count": ivr_count}
    
    # Time Conditions
    if has_table("timeconditions", **kw):
        tc_count = len(rows_as_dicts("SELECT timeconditions_id FROM timeconditions;", ["timeconditions_id"], **kw))
        analysis["timeconditions"] = {"count": tc_count}
    
    return analysis

def analyze_voicemail_config(**kw):
    """Analyze voicemail configuration."""
    config = {}
    
    if has_table("voicemail_users", **kw):
        vm_users = rows_as_dicts(
            "SELECT mailbox, context, fullname, email FROM voicemail_users;",
            ["mailbox", "context", "fullname", "email"], **kw
        )
        config["users_count"] = len(vm_users)
        config["with_email"] = len([u for u in vm_users if u["email"]])
        
        # Check voicemail settings
        if has_table("voicemail_users_settings", **kw):
            settings = rows_as_dicts(
                "SELECT keyword, value, COUNT(*) as count FROM voicemail_users_settings GROUP BY keyword, value;",
                ["keyword", "value", "count"], **kw
            )
            config["common_settings"] = settings[:10]
    
    return config

def analyze_parking_config(**kw):
    """Analyze call parking configuration."""
    config = {}
    
    if has_table("parking", **kw):
        parking = rows_as_dicts(
            "SELECT parkext, parkpos, numslots FROM parking;",
            ["parkext", "parkpos", "numslots"], **kw
        )
        if parking:
            config.update(parking[0])
    
    return config

def analyze_fax_config(**kw):
    """Analyze fax configuration if fax module is present."""
    config = {}
    
    if has_table("fax_details", **kw):
        fax_settings = rows_as_dicts(
            "SELECT keyword, value FROM fax_details;",
            ["keyword", "value"], **kw
        )
        config["settings"] = {s["keyword"]: s["value"] for s in fax_settings}
    
    if has_table("fax_users", **kw):
        fax_users = rows_as_dicts(
            "SELECT user, legacy_email FROM fax_users;",
            ["user", "legacy_email"], **kw
        )
        config["users_count"] = len(fax_users)
    
    return config

def analyze_conferencing_config(**kw):
    """Analyze conference room configuration."""
    config = {}
    
    if has_table("conferences", **kw):
        conferences = rows_as_dicts(
            "SELECT exten, description, users FROM conferences;",
            ["exten", "description", "users"], **kw
        )
        config["rooms_count"] = len(conferences)
        config["sample_rooms"] = conferences[:3]
    
    return config

def get_asterisk_module_status():
    """Get Asterisk module status using CLI."""
    stdout, stderr, rc = run_command("asterisk -rx 'module show'")
    if rc != 0:
        return {}
    
    modules = {}
    for line in stdout.split('\n'):
        if 'res_' in line or 'chan_' in line or 'app_' in line or 'func_' in line:
            parts = line.split()
            if len(parts) >= 2:
                module_name = parts[0]
                status = "loaded" if "Loaded" in line else "not_loaded"
                modules[module_name] = status
    
    return modules

def get_system_info():
    """Get basic system information."""
    info = {}
    
    # FreePBX version
    stdout, stderr, rc = run_command("fwconsole --version")
    if rc == 0:
        info["freepbx_version"] = stdout.split()[-1] if stdout else "unknown"
    
    # Asterisk version
    stdout, stderr, rc = run_command("asterisk -rx 'core show version'")
    if rc == 0:
        match = re.search(r'Asterisk\s+([0-9]+\.[0-9]+\.[0-9]+)', stdout)
        info["asterisk_version"] = match.group(1) if match else "unknown"
    
    # System load
    stdout, stderr, rc = run_command("uptime")
    if rc == 0:
        info["uptime"] = stdout
    
    return info

def main():
    parser = argparse.ArgumentParser(description="Analyze FreePBX modules and configurations")
    parser.add_argument("--socket", default=DEFAULT_SOCK, help="MySQL socket path")
    parser.add_argument("--db-user", default="root", help="MySQL user")
    parser.add_argument("--db-password", help="MySQL password")
    parser.add_argument("--output", "-o", help="Output file (JSON format)")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")
    
    args = parser.parse_args()
    
    print_header()
    
    kw = {
        "socket": args.socket,
        "user": args.db_user,
        "password": args.db_password
    }
    
    print(Colors.YELLOW + "🔍 Analyzing FreePBX modules..." + Colors.ENDC)
    
    # Gather all data
    try:
        hostname = os.uname().nodename  # type: ignore
    except AttributeError:
        hostname = os.environ.get('HOSTNAME', 'unknown')
    
    analysis = {
        "meta": {
            "hostname": hostname,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "system_info": get_system_info()
        },
        "freepbx_modules": get_freepbx_modules(**kw),
        "asterisk_modules": get_asterisk_module_status(),
        "core_analysis": analyze_core_modules(**kw),
        "voicemail_config": analyze_voicemail_config(**kw),
        "parking_config": analyze_parking_config(**kw),
        "fax_config": analyze_fax_config(**kw),
        "conferencing_config": analyze_conferencing_config(**kw)
    }
    
    if args.format == "json":
        output = json.dumps(analysis, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"✅ Analysis saved to {args.output}")
        else:
            print(output)
    else:
        # Text format output
        print_text_analysis(analysis)
        
        if args.output:
            with open(args.output, 'w') as f:
                # Redirect stdout to file for text output
                import sys
                old_stdout = sys.stdout
                sys.stdout = f
                print_text_analysis(analysis)
                sys.stdout = old_stdout
            print(f"✅ Analysis saved to {args.output}")

def print_text_analysis(analysis):
    """Print analysis in human-readable text format."""
    meta = analysis["meta"]
    
    # Dramatic header with system info
    print("\n" + Colors.CYAN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "║" + " 📋 FreePBX Module Analysis Report".center(78) + "║" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    print(Colors.CYAN + "║ " + Colors.BOLD + "Host:       " + Colors.ENDC + Colors.GREEN + meta['hostname'].ljust(63) + Colors.CYAN + " ║" + Colors.ENDC)
    print(Colors.CYAN + "║ " + Colors.BOLD + "Generated:  " + Colors.ENDC + meta['generated_at'].ljust(63) + Colors.CYAN + " ║" + Colors.ENDC)
    print(Colors.CYAN + "║ " + Colors.BOLD + "FreePBX:    " + Colors.ENDC + Colors.YELLOW + Colors.BOLD + meta['system_info'].get('freepbx_version', 'unknown').ljust(63) + Colors.CYAN + " ║" + Colors.ENDC)
    print(Colors.CYAN + "║ " + Colors.BOLD + "Asterisk:   " + Colors.ENDC + Colors.YELLOW + Colors.BOLD + meta['system_info'].get('asterisk_version', 'unknown').ljust(63) + Colors.CYAN + " ║" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # FreePBX Modules Summary with dramatic box
    modules = analysis["freepbx_modules"]
    enabled_count = len([m for m in modules if m["enabled"] == "1"])
    installed_count = len([m for m in modules if m["installed"] == "1"])
    
    print("\n" + Colors.GREEN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "║" + " 📦 FreePBX Modules Summary".center(78) + "║" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    print(Colors.GREEN + "║  " + Colors.BOLD + "Total modules:  " + Colors.ENDC + Colors.WHITE + Colors.BOLD + str(len(modules)).ljust(60) + Colors.GREEN + " ║" + Colors.ENDC)
    print(Colors.GREEN + "║  " + Colors.GREEN + "● " + Colors.BOLD + "Enabled:        " + Colors.ENDC + Colors.GREEN + Colors.BOLD + str(enabled_count).ljust(60) + Colors.GREEN + " ║" + Colors.ENDC)
    print(Colors.GREEN + "║  " + Colors.YELLOW + "● " + Colors.BOLD + "Installed:      " + Colors.ENDC + Colors.YELLOW + Colors.BOLD + str(installed_count).ljust(60) + Colors.GREEN + " ║" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Core Components Analysis with dramatic styling
    core = analysis["core_analysis"]
    print("\n" + Colors.BLUE + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.BLUE + Colors.BOLD + "║" + " 🏗️  Core Components".center(78) + "║" + Colors.ENDC)
    print(Colors.BLUE + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    
    if "extensions" in core:
        ext = core["extensions"]
        print(Colors.BLUE + "║  " + Colors.BOLD + "☎️  Extensions:      " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(ext['count']).ljust(20) + Colors.ENDC + 
              Colors.CYAN + "Voicemail: " + Colors.ENDC + Colors.GREEN + Colors.BOLD + str(ext['with_voicemail']).ljust(25) + Colors.BLUE + " ║" + Colors.ENDC)
    
    if "trunks" in core:
        trunks = core["trunks"]
        print(Colors.BLUE + "║  " + Colors.BOLD + "📡 Trunks:          " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(trunks['count']).ljust(20) + Colors.ENDC + 
              Colors.CYAN + "Enabled: " + Colors.ENDC + Colors.GREEN + Colors.BOLD + str(trunks['enabled']).ljust(27) + Colors.BLUE + " ║" + Colors.ENDC)
        for tech, count in trunks.get("by_tech", {}).items():
            print(Colors.BLUE + "║" + Colors.ENDC + "      " + Colors.CYAN + "├─ " + Colors.ENDC + 
                  tech + ": " + Colors.YELLOW + Colors.BOLD + str(count).ljust(63) + Colors.BLUE + " ║" + Colors.ENDC)
    
    if "inbound_routes" in core:
        print(Colors.BLUE + "║  " + Colors.BOLD + "📞 Inbound Routes:  " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(core['inbound_routes']['count']).ljust(56) + Colors.BLUE + " ║" + Colors.ENDC)
    
    if "outbound_routes" in core:
        print(Colors.BLUE + "║  " + Colors.BOLD + "📤 Outbound Routes: " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(core['outbound_routes']['count']).ljust(56) + Colors.BLUE + " ║" + Colors.ENDC)
    
    if "queues" in core:
        print(Colors.BLUE + "║  " + Colors.BOLD + "📋 Queues:          " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(core['queues']['count']).ljust(56) + Colors.BLUE + " ║" + Colors.ENDC)
    
    if "ringgroups" in core:
        print(Colors.BLUE + "║  " + Colors.BOLD + "🔔 Ring Groups:     " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(core['ringgroups']['count']).ljust(56) + Colors.BLUE + " ║" + Colors.ENDC)
    
    if "ivrs" in core:
        print(Colors.BLUE + "║  " + Colors.BOLD + "🎯 IVRs:            " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(core['ivrs']['count']).ljust(56) + Colors.BLUE + " ║" + Colors.ENDC)
    
    if "timeconditions" in core:
        print(Colors.BLUE + "║  " + Colors.BOLD + "⏰ Time Conditions: " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(core['timeconditions']['count']).ljust(56) + Colors.BLUE + " ║" + Colors.ENDC)
    
    print(Colors.BLUE + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Module-specific configurations
    vm_config = analysis["voicemail_config"]
    if vm_config:
        print("\n" + Colors.MAGENTA + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
        print(Colors.MAGENTA + Colors.BOLD + "║" + " 📧 Voicemail Configuration".center(78) + "║" + Colors.ENDC)
        print(Colors.MAGENTA + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
        print(Colors.MAGENTA + "║  " + Colors.BOLD + "Mailboxes:   " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(vm_config.get('users_count', 0)).ljust(62) + Colors.MAGENTA + " ║" + Colors.ENDC)
        print(Colors.MAGENTA + "║  " + Colors.GREEN + "✓ " + Colors.BOLD + "With Email: " + Colors.ENDC + 
              Colors.GREEN + Colors.BOLD + str(vm_config.get('with_email', 0)).ljust(62) + Colors.MAGENTA + " ║" + Colors.ENDC)
        print(Colors.MAGENTA + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    park_config = analysis["parking_config"]
    if park_config:
        print("\n" + Colors.YELLOW + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
        print(Colors.YELLOW + Colors.BOLD + "║" + " 🅿️  Call Parking Configuration".center(78) + "║" + Colors.ENDC)
        print(Colors.YELLOW + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
        print(Colors.YELLOW + "║  " + Colors.BOLD + "Park Extension: " + Colors.ENDC + 
              Colors.MAGENTA + Colors.BOLD + str(park_config.get('parkext', 'N/A')).ljust(60) + Colors.YELLOW + " ║" + Colors.ENDC)
        print(Colors.YELLOW + "║  " + Colors.BOLD + "Park Range:     " + Colors.ENDC + 
              Colors.CYAN + str(park_config.get('parkpos', 'N/A')).ljust(60) + Colors.YELLOW + " ║" + Colors.ENDC)
        print(Colors.YELLOW + "║  " + Colors.BOLD + "Number of Slots:" + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(park_config.get('numslots', 'N/A')).ljust(60) + Colors.YELLOW + " ║" + Colors.ENDC)
        print(Colors.YELLOW + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    fax_config = analysis["fax_config"]
    if fax_config:
        print("\n" + Colors.GREEN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
        print(Colors.GREEN + Colors.BOLD + "║" + " 📠 Fax Configuration".center(78) + "║" + Colors.ENDC)
        print(Colors.GREEN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
        print(Colors.GREEN + "║  " + Colors.BOLD + "Fax Users: " + Colors.ENDC + 
              Colors.WHITE + Colors.BOLD + str(fax_config.get('users_count', 0)).ljust(65) + Colors.GREEN + " ║" + Colors.ENDC)
        if "settings" in fax_config:
            for key, value in list(fax_config["settings"].items())[:5]:
                print(Colors.GREEN + "║    " + Colors.YELLOW + key.ljust(20) + Colors.ENDC + 
                      ": " + str(value)[:50].ljust(50) + Colors.GREEN + " ║" + Colors.ENDC)
        print(Colors.CYAN + "│" + Colors.ENDC + "  " + Colors.BOLD + "Park Extension: " + Colors.ENDC + 
              Colors.MAGENTA + Colors.BOLD + park_config.get('parkext', 'N/A') + Colors.ENDC)
        print(Colors.CYAN + "│" + Colors.ENDC + "  " + Colors.BOLD + "Park Range:     " + Colors.ENDC + 
              Colors.YELLOW + park_config.get('parkpos', 'N/A') + Colors.ENDC)
        print(Colors.CYAN + "│" + Colors.ENDC + "  " + Colors.BOLD + "Number of Slots:" + Colors.ENDC + 
              Colors.WHITE + str(park_config.get('numslots', 'N/A')) + Colors.ENDC)
        print(Colors.CYAN + "└" + "─" * 69 + Colors.ENDC)
    
    fax_config = analysis["fax_config"]
    if fax_config:
        print("\n" + Colors.CYAN + "┌─ 📠 Fax Configuration " + "─" * 46 + Colors.ENDC)
        print(Colors.CYAN + "│" + Colors.ENDC + "  " + Colors.BOLD + "Fax Users: " + Colors.ENDC + 
              Colors.WHITE + str(fax_config.get('users_count', 0)) + Colors.ENDC)
        if "settings" in fax_config:
            for key, value in list(fax_config["settings"].items())[:5]:
                print(Colors.CYAN + "│" + Colors.ENDC + "    " + Colors.YELLOW + key + Colors.ENDC + 
                      ": " + str(value))
        print(Colors.CYAN + "└" + "─" * 69 + Colors.ENDC)
    
    conf_config = analysis["conferencing_config"]
    if conf_config:
        print("\n" + Colors.CYAN + "┌─ 🎤 Conference Configuration " + "─" * 39 + Colors.ENDC)
        print(Colors.CYAN + "│" + Colors.ENDC + "  " + Colors.BOLD + "Conference Rooms: " + Colors.ENDC + 
              Colors.WHITE + str(conf_config.get('rooms_count', 0)) + Colors.ENDC)
        print(Colors.CYAN + "└" + "─" * 69 + Colors.ENDC)
    
    # Enabled FreePBX Modules Detail with dramatic display
    print("\n" + Colors.GREEN + Colors.BOLD + "╔" + "═" * 68 + "╗" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "║" + Colors.ENDC + 
          Colors.CYAN + Colors.BOLD + " 📋 Enabled FreePBX Modules".center(68) + Colors.ENDC + 
          Colors.GREEN + Colors.BOLD + "║" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "╠" + "═" * 68 + "╣" + Colors.ENDC)
    
    enabled_modules = [m for m in modules if m["enabled"] == "1"]
    for i, module in enumerate(sorted(enabled_modules, key=lambda x: x["modulename"])):
        status_color = Colors.GREEN if module["status"] == "Enabled" else Colors.RED
        status_icon = "●"
        installed_icon = Colors.GREEN + "✓" + Colors.ENDC if module["installed"] == "1" else Colors.RED + "✗" + Colors.ENDC
        
        module_line = (Colors.GREEN + "║ " + Colors.ENDC + 
                      status_color + status_icon + Colors.ENDC + " " +
                      installed_icon + " " +
                      Colors.BOLD + Colors.WHITE + module['modulename'].ljust(30) + Colors.ENDC + 
                      Colors.YELLOW + " v" + module['version'].ljust(15) + Colors.ENDC +
                      Colors.GREEN + " ║" + Colors.ENDC)
        print(module_line)
        print(Colors.GREEN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    print("\n" + Colors.GREEN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "║" + " ✅ Analysis Complete".center(78) + "║" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC + "\n")

if __name__ == "__main__":
    main()