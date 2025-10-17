#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_paging_fax_analyzer.py
Specialized analyzer for paging systems, overhead speakers, and fax configurations in FreePBX.
Provides detailed analysis of these specific communication features.
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

def get_columns(table, **kw):
    lines = run_mysql(f"DESCRIBE `{table}`;", **kw).splitlines()
    return set([ln.split("\t",1)[0] for ln in lines if ln.strip()])

# ---------------------------
# Paging Analysis Functions
# ---------------------------

def analyze_paging_pro(**kw):
    """Analyze Paging Pro module configuration."""
    config = {"enabled": False, "groups": [], "settings": {}}
    
    # Check if Paging Pro tables exist
    paging_tables = ["paging_config", "paging_groups", "pagingpro"]
    available_tables = [t for t in paging_tables if has_table(t, **kw)]
    
    if not available_tables:
        return config
    
    config["enabled"] = True
    config["available_tables"] = available_tables
    
    # Analyze paging groups
    if has_table("paging_config", **kw):
        groups = rows_as_dicts("""
            SELECT extension, description, 
                   COALESCE(enabled, '1') as enabled,
                   COALESCE(announcement, '') as announcement,
                   COALESCE(force_page, '0') as force_page,
                   COALESCE(duplex, '0') as duplex
            FROM paging_config 
            ORDER BY extension;
        """, ["extension", "description", "enabled", "announcement", "force_page", "duplex"], **kw)
        
        config["groups"] = groups
        config["total_groups"] = len(groups)
        config["enabled_groups"] = len([g for g in groups if g["enabled"] == "1"])
        config["duplex_groups"] = len([g for g in groups if g["duplex"] == "1"])
    
    # Analyze paging group members/devices
    if has_table("paging_groups", **kw):
        members = rows_as_dicts("""
            SELECT grp, device FROM paging_groups ORDER BY grp, device;
        """, ["grp", "device"], **kw)
        
        # Group members by paging group
        members_by_group = defaultdict(list)
        for member in members:
            members_by_group[member["grp"]].append(member["device"])
        
        config["members_by_group"] = dict(members_by_group)
        config["total_member_assignments"] = len(members)
    
    # Check for advanced paging settings
    if has_table("pagingpro", **kw):
        pro_settings = rows_as_dicts("""
            SELECT keyword, value FROM pagingpro;
        """, ["keyword", "value"], **kw)
        config["pro_settings"] = {s["keyword"]: s["value"] for s in pro_settings}
    
    return config

def analyze_overhead_paging(**kw):
    """Analyze overhead paging/intercom configurations."""
    config = {"speakers": [], "zones": [], "settings": {}}
    
    # Check for overhead paging in various possible configurations
    
    # Look for SIP devices that might be overhead speakers
    if has_table("sip", **kw):
        # Common overhead speaker patterns
        overhead_patterns = ["overhead", "speaker", "page", "intercom", "zone"]
        
        speakers = rows_as_dicts("""
            SELECT name, host, context, 
                   COALESCE(description, '') as description,
                   COALESCE(accountcode, '') as accountcode
            FROM sip 
            WHERE name REGEXP 'overhead|speaker|page|intercom|zone' 
               OR description REGEXP 'overhead|speaker|page|intercom|zone'
            ORDER BY name;
        """, ["name", "host", "context", "description", "accountcode"], **kw)
        
        config["sip_speakers"] = speakers
    
    # Check PJSIP endpoints for speakers
    if has_table("ps_endpoints", **kw):
        pjsip_speakers = rows_as_dicts("""
            SELECT id, transport, context,
                   COALESCE(callerid, '') as callerid
            FROM ps_endpoints 
            WHERE id REGEXP 'overhead|speaker|page|intercom|zone'
               OR callerid REGEXP 'overhead|speaker|page|intercom|zone'
            ORDER BY id;
        """, ["id", "transport", "context", "callerid"], **kw)
        
        config["pjsip_speakers"] = pjsip_speakers
    
    # Look for multicast paging configurations
    if has_table("sip", **kw):
        multicast_devices = rows_as_dicts("""
            SELECT name, host, context, type
            FROM sip 
            WHERE host LIKE '224.%' OR host LIKE '239.%'
            ORDER BY name;
        """, ["name", "host", "context", "type"], **kw)
        
        config["multicast_devices"] = multicast_devices
    
    # Check for specific overhead paging modules
    overhead_tables = ["overhead", "overhead_config", "intercom", "intercom_config"]
    for table in overhead_tables:
        if has_table(table, **kw):
            try:
                cols = get_columns(table, **kw)
                # Get first few columns for basic info
                basic_cols = list(cols)[:5]
                data = rows_as_dicts(f"SELECT * FROM {table} LIMIT 10;", basic_cols, **kw)
                config[f"{table}_data"] = data
            except:
                pass
    
    return config

def analyze_fax_configuration(**kw):
    """Comprehensive fax configuration analysis."""
    config = {"enabled": False, "engine": "unknown", "users": [], "settings": {}}
    
    # Check fax module status
    fax_tables = ["fax_details", "fax_users", "fax_incoming", "fax_outgoing", "fax", "fax_config"]
    available_fax_tables = [t for t in fax_tables if has_table(t, **kw)]
    
    if not available_fax_tables:
        return config
    
    config["enabled"] = True
    config["available_tables"] = available_fax_tables
    
    # Analyze fax engine settings
    if has_table("fax_details", **kw):
        fax_settings = rows_as_dicts("""
            SELECT keyword, value FROM fax_details ORDER BY keyword;
        """, ["keyword", "value"], **kw)
        
        config["settings"] = {s["keyword"]: s["value"] for s in fax_settings}
        
        # Determine fax engine
        if "faxengine" in config["settings"]:
            config["engine"] = config["settings"]["faxengine"]
        elif "res_fax_spandsp" in config["settings"]:
            config["engine"] = "spandsp"
        elif "res_fax_digium" in config["settings"]:
            config["engine"] = "digium"
    
    # Analyze fax users
    if has_table("fax_users", **kw):
        fax_users = rows_as_dicts("""
            SELECT user, 
                   COALESCE(ringlength, '0') as ringlength,
                   COALESCE(legacy_email, '') as legacy_email,
                   COALESCE(attachformat, 'pdf') as attachformat
            FROM fax_users ORDER BY user;
        """, ["user", "ringlength", "legacy_email", "attachformat"], **kw)
        
        config["users"] = fax_users
        config["total_users"] = len(fax_users)
        config["users_with_email"] = len([u for u in fax_users if u["legacy_email"]])
    
    # Analyze incoming fax routes
    if has_table("fax_incoming", **kw):
        incoming_fax = rows_as_dicts("""
            SELECT extension, 
                   COALESCE(cidnum, '') as cidnum,
                   COALESCE(destination, '') as destination,
                   COALESCE(faxemail, '') as faxemail,
                   COALESCE(faxexten, '') as faxexten
            FROM fax_incoming ORDER BY extension;
        """, ["extension", "cidnum", "destination", "faxemail", "faxexten"], **kw)
        
        config["incoming_routes"] = incoming_fax
        config["total_incoming_routes"] = len(incoming_fax)
    
    # Check for outbound fax configurations
    if has_table("fax_outgoing", **kw):
        outgoing_fax = rows_as_dicts("""
            SELECT pattern, 
                   COALESCE(destination, '') as destination,
                   COALESCE(faxheader, '') as faxheader
            FROM fax_outgoing ORDER BY pattern;
        """, ["pattern", "destination", "faxheader"], **kw)
        
        config["outgoing_routes"] = outgoing_fax
    
    # Check fax detection settings
    config["fax_detection"] = {}
    if "faxdetect" in config["settings"]:
        config["fax_detection"]["method"] = config["settings"]["faxdetect"]
    if "faxdetect_timeout" in config["settings"]:
        config["fax_detection"]["timeout"] = config["settings"]["faxdetect_timeout"]
    
    return config

def get_asterisk_fax_modules():
    """Check which Asterisk fax modules are loaded."""
    modules = {}
    
    stdout, stderr, rc = run_command("asterisk -rx 'module show like fax'")
    if rc == 0:
        for line in stdout.split('\n'):
            if 'res_fax' in line or 'app_fax' in line:
                parts = line.split()
                if len(parts) >= 2:
                    module_name = parts[0]
                    status = "loaded" if "Loaded" in line else "not_loaded"
                    modules[module_name] = status
    
    return modules

def analyze_dial_plan_features(**kw):
    """Analyze dialplan for paging and fax features."""
    features = {"paging_codes": [], "fax_codes": [], "intercom_codes": []}
    
    # Look for feature codes in the dialplan
    if has_table("featurecodes", **kw):
        feature_codes = rows_as_dicts("""
            SELECT modulename, featurename, defaultcode, 
                   COALESCE(customcode, defaultcode) as current_code,
                   COALESCE(enabled, '1') as enabled
            FROM featurecodes 
            WHERE modulename IN ('paging', 'fax', 'intercom', 'pagingpro')
               OR featurename LIKE '%pag%'
               OR featurename LIKE '%fax%'
               OR featurename LIKE '%intercom%'
            ORDER BY modulename, featurename;
        """, ["modulename", "featurename", "defaultcode", "current_code", "enabled"], **kw)
        
        for code in feature_codes:
            if "pag" in code["modulename"].lower() or "pag" in code["featurename"].lower():
                features["paging_codes"].append(code)
            elif "fax" in code["modulename"].lower() or "fax" in code["featurename"].lower():
                features["fax_codes"].append(code)
            elif "intercom" in code["modulename"].lower() or "intercom" in code["featurename"].lower():
                features["intercom_codes"].append(code)
    
    return features

def main():
    parser = argparse.ArgumentParser(description="Analyze FreePBX paging, overhead speakers, and fax configurations")
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
    
    print("📞 FreePBX Paging, Overhead & Fax Analysis")
    print("=" * 50)
    
    # Gather all analysis data
    analysis = {
        "meta": {
            "hostname": os.uname().nodename,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        },
        "paging_pro": analyze_paging_pro(**kw),
        "overhead_paging": analyze_overhead_paging(**kw),
        "fax_config": analyze_fax_configuration(**kw),
        "asterisk_fax_modules": get_asterisk_fax_modules(),
        "dialplan_features": analyze_dial_plan_features(**kw)
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
        print_analysis_report(analysis)
        
        if args.output:
            with open(args.output, 'w') as f:
                import sys
                old_stdout = sys.stdout
                sys.stdout = f
                print_analysis_report(analysis)
                sys.stdout = old_stdout
            print(f"✅ Analysis saved to {args.output}")

def print_analysis_report(analysis):
    """Print detailed text analysis report."""
    meta = analysis["meta"]
    print(f"📋 Paging, Overhead & Fax Analysis Report")
    print(f"Host: {meta['hostname']}")
    print(f"Generated: {meta['generated_at']}")
    print()
    
    # Paging Pro Analysis
    paging = analysis["paging_pro"]
    print("📢 PAGING PRO CONFIGURATION")
    print("-" * 40)
    if paging["enabled"]:
        print(f"✅ Paging Pro Module: ENABLED")
        print(f"   Total Groups: {paging.get('total_groups', 0)}")
        print(f"   Active Groups: {paging.get('enabled_groups', 0)}")
        print(f"   Duplex Groups: {paging.get('duplex_groups', 0)}")
        print(f"   Member Assignments: {paging.get('total_member_assignments', 0)}")
        
        if paging.get("groups"):
            print("\n   📋 Paging Groups:")
            for group in paging["groups"][:10]:  # Show first 10
                status = "🟢" if group["enabled"] == "1" else "🔴"
                duplex = " (Duplex)" if group["duplex"] == "1" else ""
                print(f"     {status} {group['extension']}: {group['description']}{duplex}")
                
                # Show members for this group
                members = paging.get("members_by_group", {}).get(group["extension"], [])
                if members:
                    print(f"        Members: {', '.join(members[:5])}" + 
                          ("..." if len(members) > 5 else ""))
        
        if paging.get("pro_settings"):
            print("\n   ⚙️  Advanced Settings:")
            for key, value in list(paging["pro_settings"].items())[:5]:
                print(f"     {key}: {value}")
    else:
        print("❌ Paging Pro Module: NOT CONFIGURED")
    print()
    
    # Overhead Paging Analysis
    overhead = analysis["overhead_paging"]
    print("📻 OVERHEAD PAGING/SPEAKERS")
    print("-" * 40)
    
    sip_speakers = overhead.get("sip_speakers", [])
    pjsip_speakers = overhead.get("pjsip_speakers", [])
    multicast = overhead.get("multicast_devices", [])
    
    if sip_speakers or pjsip_speakers or multicast:
        if sip_speakers:
            print(f"🔊 SIP Overhead Speakers: {len(sip_speakers)}")
            for speaker in sip_speakers[:5]:
                print(f"   • {speaker['name']}: {speaker['description']} ({speaker['host']})")
        
        if pjsip_speakers:
            print(f"🔊 PJSIP Overhead Speakers: {len(pjsip_speakers)}")
            for speaker in pjsip_speakers[:5]:
                print(f"   • {speaker['id']}: {speaker['callerid']}")
        
        if multicast:
            print(f"📡 Multicast Devices: {len(multicast)}")
            for device in multicast[:5]:
                print(f"   • {device['name']}: {device['host']} (multicast)")
        
        # Show any additional overhead tables found
        overhead_data_keys = [k for k in overhead.keys() if k.endswith("_data")]
        if overhead_data_keys:
            print(f"\n   📊 Additional overhead config tables: {len(overhead_data_keys)}")
    else:
        print("❌ No overhead paging devices detected")
    print()
    
    # Fax Configuration Analysis
    fax = analysis["fax_config"]
    print("📠 FAX CONFIGURATION")
    print("-" * 40)
    if fax["enabled"]:
        print(f"✅ Fax Module: ENABLED")
        print(f"   Engine: {fax['engine'].upper()}")
        print(f"   Fax Users: {fax.get('total_users', 0)}")
        print(f"   Users with Email: {fax.get('users_with_email', 0)}")
        print(f"   Incoming Routes: {fax.get('total_incoming_routes', 0)}")
        
        # Fax detection settings
        detection = fax.get("fax_detection", {})
        if detection:
            print(f"\n   🔍 Fax Detection:")
            if "method" in detection:
                print(f"     Method: {detection['method']}")
            if "timeout" in detection:
                print(f"     Timeout: {detection['timeout']}s")
        
        # Show sample users
        if fax.get("users"):
            print(f"\n   👥 Fax Users (showing first 5):")
            for user in fax["users"][:5]:
                email_status = "📧" if user["legacy_email"] else "📭"
                print(f"     {email_status} {user['user']} (format: {user['attachformat']})")
        
        # Show incoming routes
        if fax.get("incoming_routes"):
            print(f"\n   📥 Incoming Fax Routes:")
            for route in fax["incoming_routes"][:5]:
                print(f"     • DID {route['extension']} → {route['destination']}")
        
        # Key settings
        key_settings = ["faxengine", "localstationid", "faxheader", "faxdetect"]
        relevant_settings = {k: v for k, v in fax.get("settings", {}).items() if k in key_settings}
        if relevant_settings:
            print(f"\n   ⚙️  Key Settings:")
            for key, value in relevant_settings.items():
                print(f"     {key}: {value}")
    else:
        print("❌ Fax Module: NOT CONFIGURED")
    
    # Asterisk fax modules
    ast_fax = analysis["asterisk_fax_modules"]
    if ast_fax:
        print(f"\n   🔧 Asterisk Fax Modules:")
        for module, status in ast_fax.items():
            status_icon = "✅" if status == "loaded" else "❌"
            print(f"     {status_icon} {module}")
    print()
    
    # Dialplan Features
    features = analysis["dialplan_features"]
    print("☎️  DIALPLAN FEATURE CODES")
    print("-" * 40)
    
    all_codes = features["paging_codes"] + features["fax_codes"] + features["intercom_codes"]
    if all_codes:
        for code in all_codes:
            enabled_icon = "🟢" if code["enabled"] == "1" else "🔴"
            print(f"  {enabled_icon} {code['current_code']}: {code['featurename']} ({code['modulename']})")
    else:
        print("❌ No paging/fax/intercom feature codes found")
    
    print()
    print("=" * 50)
    print("✅ Specialized Analysis Complete")

if __name__ == "__main__":
    main()