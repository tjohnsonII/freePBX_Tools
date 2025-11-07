#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_comprehensive_analyzer.py
Complete analysis of all major FreePBX components and configurations.
Covers: Announcements, Calendar, Call Flow Control, Call Recording, Conferences,
Directory, Extensions, Follow Me, IVR, Misc Destinations, Paging & Intercom,
Parking, Queues, Ring Groups, Set CallerID, Time Conditions, Time Groups.
✓ Python 3.6 compatible (uses mysql CLI via subprocess; no external modules).
"""

import argparse, json, os, subprocess, sys, time, re
from collections import defaultdict

# ANSI Color codes for professional output
class Colors:
    HEADER = '\033[95m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    ENDC = '\033[0m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header():
    """Print professional header banner"""
    print(Colors.HEADER + Colors.BOLD + """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║        🔬  freePBX Comprehensive Configuration Analyzer       ║
║                                                               ║
║           Deep Analysis of All System Components              ║
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
# Component Analysis Functions
# ---------------------------

def analyze_announcements(**kw):
    """Analyze system announcements."""
    config = {"enabled": False, "announcements": [], "total": 0}
    
    # Try multiple possible table names for announcements
    tables = ["announcement", "announcements"]
    announcement_table = None
    
    for table in tables:
        if has_table(table, **kw):
            announcement_table = table
            break
    
    if not announcement_table:
        return config
    
    config["enabled"] = True
    cols = get_columns(announcement_table, **kw)
    
    # Build query based on available columns
    id_col = "announcement_id" if "announcement_id" in cols else "id" if "id" in cols else "announcementid"
    desc_col = "description" if "description" in cols else "name" if "name" in cols else f"'{id_col}'"
    post_col = "post_dest" if "post_dest" in cols else "return_dest" if "return_dest" in cols else "''"
    
    if id_col in cols:
        announcements = rows_as_dicts(f"""
            SELECT {id_col} as id, {desc_col} as description, 
                   COALESCE({post_col}, '') as post_destination
            FROM {announcement_table} ORDER BY {id_col};
        """, ["id", "description", "post_destination"], **kw)
        
        config["announcements"] = announcements
        config["total"] = len(announcements)
    
    return config

def analyze_calendar(**kw):
    """Analyze calendar module configurations."""
    config = {"enabled": False, "calendars": [], "events": [], "total_calendars": 0}
    
    if has_table("calendar", **kw):
        config["enabled"] = True
        
        calendars = rows_as_dicts("""
            SELECT id, description, 
                   COALESCE(type, '') as calendar_type,
                   COALESCE(url, '') as url,
                   COALESCE(enabled, '1') as enabled
            FROM calendar ORDER BY id;
        """, ["id", "description", "calendar_type", "url", "enabled"], **kw)
        
        config["calendars"] = calendars
        config["total_calendars"] = len(calendars)
        config["enabled_calendars"] = len([c for c in calendars if c["enabled"] == "1"])
    
    # Check for calendar events if table exists
    if has_table("calendar_events", **kw):
        events = rows_as_dicts("""
            SELECT calendar_id, title, 
                   COALESCE(start_time, '') as start_time,
                   COALESCE(end_time, '') as end_time
            FROM calendar_events ORDER BY calendar_id, start_time LIMIT 20;
        """, ["calendar_id", "title", "start_time", "end_time"], **kw)
        
        config["events"] = events
        config["total_events"] = len(events)
    
    return config

def analyze_call_flow_control(**kw):
    """Analyze Call Flow Control module."""
    config = {"enabled": False, "cfc_rules": [], "total_rules": 0}
    
    if has_table("cfc", **kw):
        config["enabled"] = True
        
        cfc_rules = rows_as_dicts("""
            SELECT cfc_id, description,
                   COALESCE(time, '') as time_condition,
                   COALESCE(dest, '') as destination,
                   COALESCE(password, '') as password
            FROM cfc ORDER BY cfc_id;
        """, ["cfc_id", "description", "time_condition", "destination", "password"], **kw)
        
        config["cfc_rules"] = cfc_rules
        config["total_rules"] = len(cfc_rules)
        config["password_protected"] = len([r for r in cfc_rules if r["password"]])
    
    return config

def analyze_call_recording(**kw):
    """Analyze call recording configurations."""
    config = {"enabled": False, "settings": {}, "per_extension": []}
    
    # Check for call recording settings
    if has_table("recording", **kw):
        config["enabled"] = True
        
        recordings = rows_as_dicts("""
            SELECT id, displayname, filename,
                   COALESCE(description, '') as description
            FROM recording ORDER BY id;
        """, ["id", "displayname", "filename", "description"], **kw)
        
        config["recordings"] = recordings
        config["total_recordings"] = len(recordings)
    
    # Check users table for recording settings
    if has_table("users", **kw):
        cols = get_columns("users", **kw)
        if "record_in" in cols or "record_out" in cols:
            record_cols = []
            if "record_in" in cols:
                record_cols.append("record_in")
            if "record_out" in cols:
                record_cols.append("record_out")
            
            query_cols = ["extension", "name"] + record_cols
            recording_users = rows_as_dicts(f"""
                SELECT extension, name, {', '.join(record_cols)}
                FROM users WHERE extension != '' ORDER BY extension;
            """, query_cols, **kw)
            
            config["per_extension"] = recording_users
            config["extensions_with_recording"] = len([u for u in recording_users 
                                                     if any(u.get(col) == "Always" for col in record_cols)])
    
    return config

def analyze_conferences(**kw):
    """Analyze conference room configurations."""
    config = {"enabled": False, "conferences": [], "total": 0}
    
    if has_table("conferences", **kw):
        config["enabled"] = True
        
        conferences = rows_as_dicts("""
            SELECT exten, description,
                   COALESCE(users, '0') as max_users,
                   COALESCE(adminpin, '') as admin_pin,
                   COALESCE(userpin, '') as user_pin,
                   COALESCE(music, '') as music_on_hold
            FROM conferences ORDER BY exten;
        """, ["exten", "description", "max_users", "admin_pin", "user_pin", "music_on_hold"], **kw)
        
        config["conferences"] = conferences
        config["total"] = len(conferences)
        config["with_admin_pin"] = len([c for c in conferences if c["admin_pin"]])
        config["with_user_pin"] = len([c for c in conferences if c["user_pin"]])
    
    return config

def analyze_directory(**kw):
    """Analyze directory configurations."""
    config = {"enabled": False, "directories": [], "entries": []}
    
    if has_table("directory", **kw):
        config["enabled"] = True
        
        directories = rows_as_dicts("""
            SELECT dirname, description,
                   COALESCE(announcement, '') as announcement,
                   COALESCE(context, '') as context
            FROM directory ORDER BY dirname;
        """, ["dirname", "description", "announcement", "context"], **kw)
        
        config["directories"] = directories
    
    # Check for directory entries
    if has_table("directory_details", **kw):
        entries = rows_as_dicts("""
            SELECT dir, selection, dest,
                   COALESCE(audio, '') as audio_file
            FROM directory_details ORDER BY dir, selection;
        """, ["dir", "selection", "dest", "audio_file"], **kw)
        
        config["entries"] = entries
        config["total_entries"] = len(entries)
    
    return config

def analyze_extensions(**kw):
    """Comprehensive extension analysis."""
    config = {"enabled": False, "extensions": [], "features": {}}
    
    if has_table("users", **kw):
        config["enabled"] = True
        
        cols = get_columns("users", **kw)
        
        # Build comprehensive extension query
        base_cols = ["extension", "name"]
        optional_cols = ["voicemail", "mohclass", "outboundcid", "record_in", "record_out", 
                        "noanswer_dest", "busy_dest", "chanunavail_dest"]
        
        available_cols = base_cols + [col for col in optional_cols if col in cols]
        
        extensions = rows_as_dicts(f"""
            SELECT {', '.join(available_cols)}
            FROM users WHERE extension != '' ORDER BY CAST(extension AS UNSIGNED);
        """, available_cols, **kw)
        
        config["extensions"] = extensions
        config["total"] = len(extensions)
        
        # Analyze features
        if "voicemail" in cols:
            config["features"]["voicemail_enabled"] = len([e for e in extensions if e.get("voicemail") == "enabled"])
        if "record_in" in cols:
            config["features"]["recording_enabled"] = len([e for e in extensions if e.get("record_in") == "Always"])
        if "outboundcid" in cols:
            config["features"]["custom_callerid"] = len([e for e in extensions if e.get("outboundcid")])
    
    return config

def analyze_followme(**kw):
    """Analyze Follow Me configurations."""
    config = {"enabled": False, "followme_configs": [], "total": 0}
    
    if has_table("findmefollow", **kw):
        config["enabled"] = True
        
        followme = rows_as_dicts("""
            SELECT grpnum, strategy,
                   COALESCE(grptime, '20') as ring_time,
                   COALESCE(grplist, '') as number_list,
                   COALESCE(annmsg_id, '') as announcement,
                   COALESCE(postdest, '') as no_answer_destination
            FROM findmefollow ORDER BY grpnum;
        """, ["grpnum", "strategy", "ring_time", "number_list", "announcement", "no_answer_destination"], **kw)
        
        config["followme_configs"] = followme
        config["total"] = len(followme)
        
        # Analyze number lists
        total_numbers = 0
        for fm in followme:
            if fm["number_list"]:
                numbers = [n.strip() for n in fm["number_list"].split("-") if n.strip()]
                total_numbers += len(numbers)
        
        config["total_followme_numbers"] = total_numbers
    
    return config

def analyze_ivr(**kw):
    """Analyze IVR (Interactive Voice Response) configurations."""
    config = {"enabled": False, "ivrs": [], "options": [], "total_ivrs": 0}
    
    if has_table("ivr_details", **kw):
        config["enabled"] = True
        
        ivrs = rows_as_dicts("""
            SELECT ivr_id, name,
                   COALESCE(announcement, '') as announcement,
                   COALESCE(directdial, '') as direct_dial,
                   COALESCE(timeout_time, '10') as timeout,
                   COALESCE(invalid_loops, '3') as invalid_loops
            FROM ivr_details ORDER BY ivr_id;
        """, ["ivr_id", "name", "announcement", "direct_dial", "timeout", "invalid_loops"], **kw)
        
        config["ivrs"] = ivrs
        config["total_ivrs"] = len(ivrs)
    
    # Analyze IVR options/entries
    if has_table("ivr_entries", **kw):
        options = rows_as_dicts("""
            SELECT ivr_id, selection, dest
            FROM ivr_entries ORDER BY ivr_id, selection;
        """, ["ivr_id", "selection", "dest"], **kw)
        
        config["options"] = options
        config["total_options"] = len(options)
        
        # Group options by IVR
        options_by_ivr = defaultdict(list)
        for option in options:
            options_by_ivr[option["ivr_id"]].append(option)
        config["options_by_ivr"] = dict(options_by_ivr)
    
    return config

def analyze_misc_destinations(**kw):
    """Analyze miscellaneous destinations."""
    config = {"enabled": False, "destinations": [], "total": 0}
    
    if has_table("miscdests", **kw):
        config["enabled"] = True
        
        destinations = rows_as_dicts("""
            SELECT id, description, dest
            FROM miscdests ORDER BY id;
        """, ["id", "description", "dest"], **kw)
        
        config["destinations"] = destinations
        config["total"] = len(destinations)
    
    return config

def analyze_parking(**kw):
    """Analyze call parking configurations."""
    config = {"enabled": False, "lots": [], "settings": {}}
    
    if has_table("parking", **kw):
        config["enabled"] = True
        
        parking_lots = rows_as_dicts("""
            SELECT parkext, parkpos, numslots,
                   COALESCE(parkingtime, '45') as timeout,
                   COALESCE(comebacktoorigin, 'yes') as comeback_to_origin
            FROM parking ORDER BY parkext;
        """, ["parkext", "parkpos", "numslots", "timeout", "comeback_to_origin"], **kw)
        
        config["lots"] = parking_lots
        config["total_lots"] = len(parking_lots)
        
        if parking_lots:
            total_slots = sum(int(lot.get("numslots", 0) or 0) for lot in parking_lots)
            config["total_parking_slots"] = total_slots
    
    return config

def analyze_queues(**kw):
    """Comprehensive queue analysis."""
    config = {"enabled": False, "queues": [], "members": [], "total": 0}
    
    if has_table("queues_config", **kw) and has_table("queues_details", **kw):
        config["enabled"] = True
        
        # Get queue configurations
        queues = rows_as_dicts("""
            SELECT extension, descr as description
            FROM queues_config ORDER BY extension;
        """, ["extension", "description"], **kw)
        
        # Get queue details (strategy, timeout, etc.)
        details = rows_as_dicts("""
            SELECT id,
                   MAX(CASE WHEN keyword='strategy' THEN data END) as strategy,
                   MAX(CASE WHEN keyword='timeout' THEN data END) as timeout,
                   MAX(CASE WHEN keyword='retry' THEN data END) as retry_time,
                   MAX(CASE WHEN keyword='maxlen' THEN data END) as max_length,
                   MAX(CASE WHEN keyword='announce-frequency' THEN data END) as announce_freq
            FROM queues_details GROUP BY id;
        """, ["id", "strategy", "timeout", "retry_time", "max_length", "announce_freq"], **kw)
        
        # Combine queue info with details
        details_dict = {d["id"]: d for d in details}
        for queue in queues:
            queue_details = details_dict.get(queue["extension"], {})
            queue.update(queue_details)
        
        config["queues"] = queues
        config["total"] = len(queues)
        
        # Analyze queue members
        static_members = rows_as_dicts("""
            SELECT id, 
                   GROUP_CONCAT(data ORDER BY data SEPARATOR ',') as members
            FROM queues_details 
            WHERE keyword='member' 
            GROUP BY id;
        """, ["id", "members"], **kw)
        
        config["static_members"] = static_members
        
        # Dynamic members if available
        if has_table("queue_members", **kw):
            dynamic_members = rows_as_dicts("""
                SELECT queue_name, interface, penalty
                FROM queue_members ORDER BY queue_name, interface;
            """, ["queue_name", "interface", "penalty"], **kw)
            config["dynamic_members"] = dynamic_members
    
    return config

def analyze_ring_groups(**kw):
    """Analyze ring group configurations."""
    config = {"enabled": False, "ring_groups": [], "total": 0}
    
    if has_table("ringgroups", **kw):
        config["enabled"] = True
        
        ring_groups = rows_as_dicts("""
            SELECT grpnum, description, grplist, strategy,
                   COALESCE(grptime, '20') as ring_time,
                   COALESCE(postdest, '') as no_answer_destination,
                   COALESCE(annmsg_id, '') as announcement
            FROM ringgroups ORDER BY grpnum;
        """, ["grpnum", "description", "grplist", "strategy", "ring_time", "no_answer_destination", "announcement"], **kw)
        
        config["ring_groups"] = ring_groups
        config["total"] = len(ring_groups)
        
        # Analyze ring strategies
        strategies = defaultdict(int)
        total_extensions = 0
        
        for rg in ring_groups:
            strategies[rg.get("strategy", "unknown")] += 1
            if rg.get("grplist"):
                exts = [e.strip() for e in rg["grplist"].split("-") if e.strip()]
                total_extensions += len(exts)
        
        config["strategies_count"] = dict(strategies)
        config["total_ring_group_extensions"] = total_extensions
    
    return config

def analyze_set_callerid(**kw):
    """Analyze Set CallerID configurations."""
    config = {"enabled": False, "callerid_rules": [], "total": 0}
    
    if has_table("setcid", **kw):
        config["enabled"] = True
        
        callerid_rules = rows_as_dicts("""
            SELECT setcid_id, description,
                   COALESCE(cid_name, '') as caller_name,
                   COALESCE(cid_num, '') as caller_number,
                   COALESCE(dest, '') as destination
            FROM setcid ORDER BY setcid_id;
        """, ["setcid_id", "description", "caller_name", "caller_number", "destination"], **kw)
        
        config["callerid_rules"] = callerid_rules
        config["total"] = len(callerid_rules)
    
    return config

def analyze_time_conditions(**kw):
    """Analyze time condition configurations."""
    config = {"enabled": False, "time_conditions": [], "total": 0}
    
    if has_table("timeconditions", **kw):
        config["enabled"] = True
        
        cols = get_columns("timeconditions", **kw)
        
        # Handle different schema versions
        time_col = "timegroupid" if "timegroupid" in cols else "time" if "time" in cols else "0"
        true_col = "destination_true" if "destination_true" in cols else "truegoto" if "truegoto" in cols else "''"
        false_col = "destination_false" if "destination_false" in cols else "falsegoto" if "falsegoto" in cols else "''"
        name_col = "displayname" if "displayname" in cols else "name" if "name" in cols else "CONCAT('TC-', timeconditions_id)"
        
        time_conditions = rows_as_dicts(f"""
            SELECT timeconditions_id, {name_col} as name,
                   {time_col} as time_group_id,
                   COALESCE({true_col}, '') as true_destination,
                   COALESCE({false_col}, '') as false_destination
            FROM timeconditions ORDER BY timeconditions_id;
        """, ["timeconditions_id", "name", "time_group_id", "true_destination", "false_destination"], **kw)
        
        config["time_conditions"] = time_conditions
        config["total"] = len(time_conditions)
    
    return config

def analyze_time_groups(**kw):
    """Analyze time group configurations."""
    config = {"enabled": False, "time_groups": [], "rules": [], "total": 0}
    
    if has_table("timegroups_details", **kw):
        config["enabled"] = True
        
        # Get time group rules
        rules = rows_as_dicts("""
            SELECT id, timegroupid, time
            FROM timegroups_details ORDER BY timegroupid, id;
        """, ["id", "timegroupid", "time"], **kw)
        
        config["rules"] = rules
        config["total_rules"] = len(rules)
        
        # Group rules by time group
        groups_dict = defaultdict(list)
        for rule in rules:
            groups_dict[rule["timegroupid"]].append(rule)
        
        # Create time groups summary
        time_groups = []
        for tg_id, tg_rules in groups_dict.items():
            time_groups.append({
                "timegroupid": tg_id,
                "rule_count": len(tg_rules),
                "rules": tg_rules
            })
        
        config["time_groups"] = time_groups
        config["total"] = len(time_groups)
    
    return config

def main():
    print_header()
    
    parser = argparse.ArgumentParser(description="Comprehensive FreePBX component analysis")
    parser.add_argument("--socket", default=DEFAULT_SOCK, help="MySQL socket path")
    parser.add_argument("--db-user", default="root", help="MySQL user")
    parser.add_argument("--db-password", help="MySQL password")
    parser.add_argument("--output", "-o", help="Output file (JSON format)")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")
    parser.add_argument("--component", help="Analyze specific component only", 
                       choices=["announcements", "calendar", "callflow", "recording", "conferences",
                               "directory", "extensions", "followme", "ivr", "misc", "parking",
                               "queues", "ringgroups", "callerid", "timeconditions", "timegroups"])
    
    args = parser.parse_args()
    
    kw = {
        "socket": args.socket,
        "user": args.db_user,
        "password": args.db_password
    }
    
    # Component analysis mapping
    components = {
        "announcements": ("📢 Announcements", analyze_announcements),
        "calendar": ("📅 Calendar", analyze_calendar),
        "callflow": ("🔀 Call Flow Control", analyze_call_flow_control),
        "recording": ("🎙️  Call Recording", analyze_call_recording),
        "conferences": ("🎤 Conferences", analyze_conferences),
        "directory": ("📖 Directory", analyze_directory),
        "extensions": ("☎️  Extensions", analyze_extensions),
        "followme": ("📱 Follow Me", analyze_followme),
        "ivr": ("🎯 IVR", analyze_ivr),
        "misc": ("🔧 Misc Destinations", analyze_misc_destinations),
        "parking": ("🅿️  Parking", analyze_parking),
        "queues": ("📞 Queues", analyze_queues),
        "ringgroups": ("🔔 Ring Groups", analyze_ring_groups),
        "callerid": ("🆔 Set CallerID", analyze_set_callerid),
        "timeconditions": ("⏰ Time Conditions", analyze_time_conditions),
        "timegroups": ("⏱️  Time Groups", analyze_time_groups)
    }
    
    # Analyze components
    try:
        hostname = os.uname().nodename  # type: ignore
    except AttributeError:
        hostname = os.environ.get('HOSTNAME', 'unknown')
    
    analysis = {
        "meta": {
            "hostname": hostname,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }
    }
    
    if args.component:
        # Analyze single component
        if args.component in components:
            title, analyzer = components[args.component]
            print(Colors.CYAN + f"🔍 Analyzing {title}..." + Colors.ENDC)
            analysis[args.component] = analyzer(**kw)
        else:
            print(Colors.RED + f"❌ Unknown component: {args.component}" + Colors.ENDC)
            import sys
            sys.exit(1)
    else:
        # Analyze all components
        total = len(components)
        for i, (comp_key, (title, analyzer)) in enumerate(components.items(), 1):
            print(Colors.CYAN + f"[{i}/{total}] " + Colors.BOLD + f"{title}..." + Colors.ENDC)
            analysis[comp_key] = analyzer(**kw)
    
    print("")  # Blank line
    
    if args.format == "json":
        output = json.dumps(analysis, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(Colors.GREEN + Colors.BOLD + "✓ Analysis saved to: " + Colors.ENDC + 
                  Colors.CYAN + args.output + Colors.ENDC)
        else:
            print(output)
    else:
        print_comprehensive_report(analysis, args.component)
        
        if args.output:
            with open(args.output, 'w') as f:
                import sys
                old_stdout = sys.stdout
                sys.stdout = f
                print_comprehensive_report(analysis, args.component)
                sys.stdout = old_stdout
            print(f"✅ Analysis saved to {args.output}")

def print_comprehensive_report(analysis, single_component=None):
    """Print comprehensive analysis report with beautiful tables and colors."""
    meta = analysis["meta"]
    
    # Header box
    print(Colors.CYAN + Colors.BOLD + "\n╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "║" + Colors.YELLOW + " 📊 freePBX COMPREHENSIVE ANALYSIS REPORT ".center(78) + Colors.CYAN + "║" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "╠" + "═" * 78 + "╣" + Colors.ENDC)
    print(Colors.CYAN + "║ " + Colors.WHITE + Colors.BOLD + "Host:      " + Colors.GREEN + Colors.BOLD + meta['hostname'].ljust(65) + Colors.CYAN + " ║" + Colors.ENDC)
    print(Colors.CYAN + "║ " + Colors.WHITE + Colors.BOLD + "Generated: " + Colors.YELLOW + meta['generated_at'].ljust(65) + Colors.CYAN + " ║" + Colors.ENDC)
    print(Colors.CYAN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Component titles and emojis mapping
    components_info = [
        ("announcements", "📢", "ANNOUNCEMENTS"),
        ("calendar", "📅", "CALENDAR"),
        ("callflow", "🔀", "CALL FLOW CONTROL"),
        ("recording", "🎙️", "CALL RECORDING"),
        ("conferences", "🎤", "CONFERENCES"),
        ("directory", "📖", "DIRECTORY"),
        ("extensions", "☎️", "EXTENSIONS"),
        ("followme", "📱", "FOLLOW ME"),
        ("ivr", "🎯", "IVR (INTERACTIVE VOICE RESPONSE)"),
        ("misc", "🔧", "MISC DESTINATIONS"),
        ("parking", "🅿️", "CALL PARKING"),
        ("queues", "📞", "QUEUES"),
        ("ringgroups", "🔔", "RING GROUPS"),
        ("callerid", "🆔", "SET CALLER ID"),
        ("timeconditions", "⏰", "TIME CONDITIONS"),
        ("timegroups", "⏱️", "TIME GROUPS")
    ]
    
    component_count = 0
    
    # Print analysis for each component
    for comp_key, emoji, title in components_info:
        if comp_key not in analysis:
            continue
            
        if single_component and comp_key != single_component:
            continue
            
        data = analysis[comp_key]
        component_count += 1
        
        # Component header
        print(f"\n{Colors.CYAN}{Colors.BOLD}[{component_count}/16] {emoji}  {title}{Colors.ENDC}")
        
        if not data.get("enabled", False):
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.RED + "❌ Module not configured or not available".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
            continue
            
        # Component-specific reporting with tables
        if comp_key == "announcements":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Total Announcements: {data['total']}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            if data["announcements"]:
                for ann in data["announcements"][:10]:
                    post = f"{Colors.YELLOW} → {ann['post_destination']}{Colors.RESET}" if ann['post_destination'] else ""
                    ann_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{Colors.BOLD}{ann['id']}:{Colors.RESET} {ann['description']}{post}"
                    # Strip ANSI to calculate padding
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ann_line)
                    padding = " " * max(0, 78 - len(visible_text))
                    print(Colors.CYAN + "║ " + Colors.RESET + ann_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                    
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "calendar":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Total Calendars: {data['total_calendars']}  │  Enabled: {data.get('enabled_calendars', 0)}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for cal in data["calendars"][:8]:
                status = f"{Colors.GREEN}🟢{Colors.RESET}" if cal["enabled"] == "1" else f"{Colors.RED}🔴{Colors.RESET}"
                cal_line = f"  {status} {Colors.WHITE}{cal['description']}{Colors.RESET} {Colors.CYAN}({cal['calendar_type']}){Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', cal_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + cal_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                    
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "callflow":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Total CFC Rules: {data['total_rules']}  │  Password Protected: {data.get('password_protected', 0)}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for rule in data["cfc_rules"][:8]:
                pwd = f" {Colors.RED}🔒{Colors.RESET}" if rule['password'] else ""
                rule_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{rule['description']}{Colors.RESET}{pwd} {Colors.YELLOW}→{Colors.RESET} {rule['destination'][:35]}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', rule_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + rule_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                    
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "recording":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            recordings_count = data.get('total_recordings', len(data.get("recordings", [])))
            exts_with_rec = data.get('extensions_with_recording', 'N/A')
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ System Recordings: {recordings_count}  │  Extensions with Recording: {exts_with_rec}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for rec in data.get("recordings", [])[:8]:
                rec_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{rec['displayname']}{Colors.RESET} {Colors.YELLOW}({rec['filename']}){Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', rec_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + rec_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "conferences":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Conference Rooms: {data['total']}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.WHITE + f"   With Admin PIN: {data.get('with_admin_pin', 0)}  │  With User PIN: {data.get('with_user_pin', 0)}".ljust(78) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for conf in data["conferences"][:8]:
                pins = []
                if conf['admin_pin']: pins.append(f"{Colors.RED}Admin{Colors.RESET}")
                if conf['user_pin']: pins.append(f"{Colors.GREEN}User{Colors.RESET}")
                pin_info = f" ({', '.join(pins)} PIN)" if pins else ""
                conf_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{Colors.BOLD}{conf['exten']}:{Colors.RESET} {conf['description']}{pin_info}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', conf_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + conf_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "directory":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Directories: {len(data['directories'])}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            if "total_entries" in data:
                print(Colors.CYAN + "║ " + Colors.WHITE + f"   Total Entries: {data['total_entries']}".ljust(78) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for dir_entry in data["directories"][:8]:
                dir_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{dir_entry['dirname']}:{Colors.RESET} {dir_entry['description']}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', dir_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + dir_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "extensions":
            features = data.get("features", {})
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Total Extensions: {data['total']}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            
            if "voicemail_enabled" in features:
                print(Colors.CYAN + "║ " + Colors.WHITE + f"   With Voicemail: {Colors.YELLOW}{Colors.BOLD}{features['voicemail_enabled']}{Colors.RESET}  │  ".ljust(91) + 
                      f"With Recording: {Colors.YELLOW}{Colors.BOLD}{features.get('recording_enabled', 0)}{Colors.RESET}  │  " + 
                      f"Custom CallerID: {Colors.YELLOW}{Colors.BOLD}{features.get('custom_callerid', 0)}{Colors.RESET}".ljust(78) + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "followme":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Follow Me Configs: {data['total']}  │  Total Numbers: {data.get('total_followme_numbers', 0)}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for fm in data["followme_configs"][:8]:
                numbers = len([n for n in fm['number_list'].split('-') if n.strip()]) if fm['number_list'] else 0
                fm_line = f"  {Colors.CYAN}•{Colors.RESET} Ext {Colors.WHITE}{Colors.BOLD}{fm['grpnum']}{Colors.RESET}: {Colors.YELLOW}{numbers} numbers{Colors.RESET}, {Colors.GREEN}{fm['strategy']}{Colors.RESET} strategy"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', fm_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + fm_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "ivr":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ IVR Menus: {data['total_ivrs']}  │  Total Options: {data.get('total_options', 0)}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for ivr in data["ivrs"][:8]:
                option_count = len(data.get("options_by_ivr", {}).get(ivr["ivr_id"], []))
                ivr_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{Colors.BOLD}{ivr['ivr_id']}:{Colors.RESET} {ivr['name']} {Colors.YELLOW}({option_count} options){Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ivr_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + ivr_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "misc":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Misc Destinations: {data['total']}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for dest in data["destinations"][:10]:
                dest_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{dest['description']}{Colors.RESET} {Colors.YELLOW}→{Colors.RESET} {dest['dest'][:35]}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', dest_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + dest_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "parking":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Parking Lots: {data.get('total_lots', 0)}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            if "total_parking_slots" in data:
                print(Colors.CYAN + "║ " + Colors.WHITE + f"   Total Slots: {data['total_parking_slots']}".ljust(78) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for lot in data["lots"]:
                lot_line = f"  {Colors.CYAN}•{Colors.RESET} Extension {Colors.WHITE}{Colors.BOLD}{lot['parkext']}{Colors.RESET}: {Colors.YELLOW}{lot['numslots']} slots{Colors.RESET} {Colors.CYAN}({lot['parkpos']}){Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', lot_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + lot_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "queues":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Queues: {data['total']}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for queue in data["queues"][:10]:
                strategy = queue.get('strategy', 'unknown')
                timeout = queue.get('timeout', 'default')
                q_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{Colors.BOLD}{queue['extension']}:{Colors.RESET} {queue['description'][:30]} {Colors.YELLOW}({strategy}, {timeout}s){Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', q_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + q_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "ringgroups":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Ring Groups: {data['total']}  │  Total Extensions: {data.get('total_ring_group_extensions', 0)}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            
            strategies = data.get('strategies_count', {})
            if strategies:
                strat_line = "   "
                for strategy, count in list(strategies.items())[:3]:
                    strat_line += f"{Colors.YELLOW}{strategy}{Colors.RESET}: {Colors.WHITE}{count}{Colors.RESET}  │  "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', strat_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + strat_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for rg in data["ring_groups"][:8]:
                ext_count = len([e for e in rg['grplist'].split('-') if e.strip()]) if rg['grplist'] else 0
                rg_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{Colors.BOLD}{rg['grpnum']}:{Colors.RESET} {rg['description'][:35]} {Colors.YELLOW}({ext_count} exts, {rg['strategy']}){Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', rg_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + rg_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "callerid":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ CallerID Rules: {data['total']}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for rule in data["callerid_rules"][:10]:
                cid_info = f"{rule['caller_name']} <{rule['caller_number']}>" if rule['caller_name'] or rule['caller_number'] else "Default"
                cid_line = f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{rule['description']}{Colors.RESET}: {Colors.YELLOW}{cid_info}{Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', cid_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + cid_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "timeconditions":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Time Conditions: {data['total']}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for tc in data["time_conditions"][:10]:
                print(Colors.CYAN + "║ " + Colors.RESET + f"  {Colors.CYAN}•{Colors.RESET} {Colors.WHITE}{Colors.BOLD}{tc['name']}{Colors.RESET}: Group {Colors.YELLOW}{tc['time_group_id']}{Colors.RESET}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
                true_line = f"     {Colors.GREEN}True{Colors.RESET}  → {tc['true_destination'][:55]}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', true_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + true_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
                false_line = f"     {Colors.RED}False{Colors.RESET} → {tc['false_destination'][:55]}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', false_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + false_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
                
        elif comp_key == "timegroups":
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.ENDC)
            print(Colors.CYAN + "║ " + Colors.GREEN + Colors.BOLD + f"✅ Time Groups: {data['total']}  │  Total Rules: {data.get('total_rules', 0)}".ljust(87) + Colors.CYAN + " ║" + Colors.ENDC)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.ENDC)
            
            for tg in data["time_groups"][:10]:
                tg_line = f"  {Colors.CYAN}•{Colors.RESET} Group {Colors.WHITE}{Colors.BOLD}{tg['timegroupid']}{Colors.RESET}: {Colors.YELLOW}{tg['rule_count']} rules{Colors.RESET}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', tg_line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + Colors.RESET + tg_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                
                for rule in tg["rules"][:3]:
                    rule_line = f"     - {Colors.GREEN}{rule['time']}{Colors.RESET}"
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', rule_line)
                    padding = " " * max(0, 78 - len(visible_text))
                    print(Colors.CYAN + "║ " + Colors.RESET + rule_line + padding + Colors.CYAN + " ║" + Colors.ENDC)
                    
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.ENDC)
    
    # Final summary
    print("\n" + Colors.GREEN + Colors.BOLD + "╔" + "═" * 78 + "╗" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "║" + " ✅ Comprehensive Analysis Complete ".center(78) + "║" + Colors.ENDC)
    print(Colors.GREEN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.ENDC + "\n")

if __name__ == "__main__":
    main()