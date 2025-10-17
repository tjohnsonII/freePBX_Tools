#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_module_analyzer.py
Comprehensive FreePBX module status and configuration analysis tool.
Evaluates all installed modules and their configurations.
✓ Python 3.6 compatible (uses mysql CLI via subprocess; no external modules).
"""

import argparse, json, os, subprocess, sys, time, re
from collections import defaultdict

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
    
    kw = {
        "socket": args.socket,
        "user": args.db_user,
        "password": args.db_password
    }
    
    print("🔍 FreePBX Module Analysis Starting...")
    print("=" * 60)
    
    # Gather all data
    analysis = {
        "meta": {
            "hostname": os.uname().nodename,
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
    print(f"📋 FreePBX Module Analysis Report")
    print(f"Host: {meta['hostname']}")
    print(f"Generated: {meta['generated_at']}")
    print(f"FreePBX Version: {meta['system_info'].get('freepbx_version', 'unknown')}")
    print(f"Asterisk Version: {meta['system_info'].get('asterisk_version', 'unknown')}")
    print()
    
    # FreePBX Modules Summary
    modules = analysis["freepbx_modules"]
    print("📦 FreePBX Modules Summary")
    print("-" * 40)
    enabled_count = len([m for m in modules if m["enabled"] == "1"])
    installed_count = len([m for m in modules if m["installed"] == "1"])
    print(f"Total modules: {len(modules)}")
    print(f"Enabled: {enabled_count}")
    print(f"Installed: {installed_count}")
    print()
    
    # Core Components Analysis
    core = analysis["core_analysis"]
    print("🏗️  Core Components")
    print("-" * 40)
    
    if "extensions" in core:
        ext = core["extensions"]
        print(f"Extensions: {ext['count']} (Voicemail: {ext['with_voicemail']})")
    
    if "trunks" in core:
        trunks = core["trunks"]
        print(f"Trunks: {trunks['count']} (Enabled: {trunks['enabled']})")
        for tech, count in trunks.get("by_tech", {}).items():
            print(f"  - {tech}: {count}")
    
    if "inbound_routes" in core:
        print(f"Inbound Routes: {core['inbound_routes']['count']}")
    
    if "outbound_routes" in core:
        print(f"Outbound Routes: {core['outbound_routes']['count']}")
    
    if "queues" in core:
        print(f"Queues: {core['queues']['count']}")
    
    if "ringgroups" in core:
        print(f"Ring Groups: {core['ringgroups']['count']}")
    
    if "ivrs" in core:
        print(f"IVRs: {core['ivrs']['count']}")
    
    if "timeconditions" in core:
        print(f"Time Conditions: {core['timeconditions']['count']}")
    
    print()
    
    # Module-specific configurations
    vm_config = analysis["voicemail_config"]
    if vm_config:
        print("📧 Voicemail Configuration")
        print("-" * 40)
        print(f"Mailboxes: {vm_config.get('users_count', 0)}")
        print(f"With Email: {vm_config.get('with_email', 0)}")
        print()
    
    park_config = analysis["parking_config"]
    if park_config:
        print("🅿️  Call Parking Configuration")
        print("-" * 40)
        print(f"Park Extension: {park_config.get('parkext', 'N/A')}")
        print(f"Park Range: {park_config.get('parkpos', 'N/A')}")
        print(f"Number of Slots: {park_config.get('numslots', 'N/A')}")
        print()
    
    fax_config = analysis["fax_config"]
    if fax_config:
        print("📠 Fax Configuration")
        print("-" * 40)
        print(f"Fax Users: {fax_config.get('users_count', 0)}")
        if "settings" in fax_config:
            for key, value in list(fax_config["settings"].items())[:5]:
                print(f"  {key}: {value}")
        print()
    
    conf_config = analysis["conferencing_config"]
    if conf_config:
        print("🎤 Conference Configuration")
        print("-" * 40)
        print(f"Conference Rooms: {conf_config.get('rooms_count', 0)}")
        print()
    
    # Enabled FreePBX Modules Detail
    print("📋 Enabled FreePBX Modules")
    print("-" * 40)
    enabled_modules = [m for m in modules if m["enabled"] == "1"]
    for module in sorted(enabled_modules, key=lambda x: x["modulename"]):
        status_indicators = []
        if module["installed"] == "1":
            status_indicators.append("✅")
        if module["status"] == "Enabled":
            status_indicators.append("🟢")
        elif module["status"] == "Disabled":
            status_indicators.append("🔴")
        
        print(f"{''.join(status_indicators)} {module['modulename']} (v{module['version']})")
    
    print()
    print("=" * 60)
    print("✅ Analysis Complete")

if __name__ == "__main__":
    main()