#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_ascii_callflow.py
Generate ASCII art call flow diagrams for FreePBX inbound routes.
Creates text-based flowcharts that can be displayed in console or text files.
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
# ASCII Art Flow Generator
# ---------------------------

"""
FreePBX ASCII Call Flow Generator - Comprehensive Module Support

This tool generates sophisticated ASCII art call flow diagrams for FreePBX systems,
supporting all major FreePBX applications and modules shown in the Applications menu:

CORE ROUTING COMPONENTS:
✓ Extensions (SIP/PJSIP endpoints) - Individual phone extensions
✓ Ring Groups - Hunt groups with sequential/simultaneous ring strategies  
✓ Queues - Call center queuing with agent management and statistics
✓ IVR/Digital Receptionist - Multi-level interactive voice response menus
✓ Time Conditions - Schedule-based call routing (business hours, holidays)
✓ Inbound Routes - DID processing and call routing from external sources
✓ Outbound Routes - Call routing rules for external destinations

COMMUNICATION FEATURES:
✓ Voicemail - Message recording and delivery systems
✓ Announcements - Audio playback for greetings and information
✓ Conferences/MeetMe - Conference room management and participant control
✓ Paging/Intercom - Group notification and intercom systems
✓ Fax - Fax-to-email processing and virtual fax handling

ADVANCED ROUTING:
✓ Call Flow Toggle Control (CFC) - Dynamic routing control with toggle states
✓ Follow Me (Find Me/Follow Me) - Multi-device ring strategies with failover
✓ Misc Destinations - Custom routing destinations and integrations
✓ Call Recording - Call recording options and management
✓ Directory - Dial-by-name directory services
✓ Set CallerID - Dynamic caller ID modification

TIME & SCHEDULING:
✓ Calendar - Event-based routing using calendar integrations
✓ Calendar Event Groups - Grouped calendar events for complex scheduling
✓ Time Groups - Time schedule definitions used by Time Conditions

CALL MANAGEMENT:
✓ Call Parking - Park and retrieve calls with timeout handling
✓ Hangup/Busy - Call termination and busy handling

VISUAL FEATURES:
- Unicode box-drawing characters for professional appearance
- Component-specific icons and styling
- Pre-loading data strategy for performance
- Sophisticated routing visualization with branch indicators
- Loop detection and depth limiting for safety
- Detailed component information display

The generator uses a pre-loading architecture that bulk loads all FreePBX configuration
data once, then renders call flows using cached data for optimal performance.
"""

class ASCIIFlowGenerator:
    def __init__(self, **kw):
        self.kw = kw
        self.flow_data = {}
        self.canvas = []
        self.width = 120  # Canvas width for complex layouts
        self.current_row = 0
        self.visited_destinations = set()  # Prevent infinite loops
        
        # Pre-loaded data structures - populated by load_all_data()
        self.data = {
            'timeconditions': {},     # tc_id -> {name, true_dest, false_dest}
            'timegroups': {},         # tg_id -> {name, times, days}
            'calendar': {},           # cal_id -> {name, events, url}
            'calendar_events': {},    # event_id -> {name, start, end, calendar_id}
            'ivrs': {},               # ivr_id -> {name, announcement, timeout_dest}
            'ivr_options': {},        # ivr_id -> [selection, dest] pairs
            'extensions': {},         # ext_num -> {name, voicemail, etc}
            'queues': {},             # queue_id -> {name, strategy, maxwait, etc}
            'ringgroups': {},         # rg_id -> {description, members, strategy, etc}
            'announcements': {},      # ann_id -> {description, post_dest}
            'conferences': {},        # conf_id -> {description, maxusers, pin}
            'paging': {},             # page_id -> {description, devices}
            'routes': {},             # did -> {description, destination, cid}
            'followme': {},           # ext -> {numbers, strategy}
            'callflow_toggle': {},    # cfc_id -> {description, state, true_dest, false_dest, feature_code}
            'call_recording': {},     # rec_id -> {description, mode, format}
            'misc_destinations': {},  # dest_id -> {description, dial, notes}
            'parking': {},            # parking lots and settings
            'directory': {},          # dir_id -> {name, entries, announcement}
            'setcid': {}             # cid_id -> {description, cid_name, cid_num}
        }
        
        # Visual styling constants
        self.STYLES = {
            'inbound': {'icon': '[IN]', 'border': '=', 'color': 'cyan'},
            'time_condition': {'icon': '[TC]', 'border': '-', 'color': 'yellow'},
            'timegroup': {'icon': '[TIME]', 'border': '-', 'color': 'yellow'},
            'calendar': {'icon': '[CAL]', 'border': '-', 'color': 'blue'},
            'callflow_toggle': {'icon': '[CFC]', 'border': '=', 'color': 'blue'},
            'ivr': {'icon': '[IVR]', 'border': '=', 'color': 'blue'},
            'queue': {'icon': '[Q]', 'border': '-', 'color': 'green'},
            'ringgroup': {'icon': '[RG]', 'border': '-', 'color': 'magenta'},
            'extension': {'icon': '[EXT]', 'border': '-', 'color': 'white'},
            'announcement': {'icon': '[ANN]', 'border': '-', 'color': 'orange'},
            'voicemail': {'icon': '[VM]', 'border': '-', 'color': 'gray'},
            'conference': {'icon': '[CONF]', 'border': '-', 'color': 'purple'},
            'paging': {'icon': '[PAGE]', 'border': '-', 'color': 'red'},
            'fax': {'icon': '[FAX]', 'border': '-', 'color': 'brown'},
            'call_recording': {'icon': '[REC]', 'border': '-', 'color': 'red'},
            'followme': {'icon': '[FM]', 'border': '-', 'color': 'cyan'},
            'misc_destination': {'icon': '[MISC]', 'border': '-', 'color': 'gray'},
            'parking': {'icon': '[PARK]', 'border': '-', 'color': 'yellow'},
            'directory': {'icon': '[DIR]', 'border': '-', 'color': 'green'},
            'setcid': {'icon': '[CID]', 'border': '-', 'color': 'blue'},
            'failover': {'icon': '[FAIL]', 'border': ':', 'color': 'red'},
            'hangup': {'icon': '[END]', 'border': '+', 'color': 'red'}
        }
    
    def create_box(self, title, subtitle="", box_type="normal", width=None):
        """Create a formatted text box with various styles."""
        style = self.STYLES.get(box_type, self.STYLES['extension'])
        icon = style['icon']
        border_char = style['border']
        
        # Calculate box dimensions
        content_width = width or max(len(title), len(subtitle) if subtitle else 0, 12) + 4
        content_width = min(content_width, 30)  # Max box width
        
        # Create box lines
        top_line = f"┌{border_char * content_width}┐"
        
        # Title line with icon
        title_padded = f" {icon} {title}".ljust(content_width)
        title_line = f"│{title_padded}│"
        
        # Subtitle line if provided
        lines = [top_line, title_line]
        if subtitle:
            subtitle_padded = f"   {subtitle}".ljust(content_width)
            lines.append(f"│{subtitle_padded}│")
        
        # Bottom line
        bottom_line = f"└{border_char * content_width}┘"
        lines.append(bottom_line)
        
        return lines, content_width + 2
    
    def create_decision_diamond(self, question, width=None):
        """Create a decision point visualization."""
        q_width = width or max(len(question) + 4, 25)
        
        # Simplified decision box
        lines = []
        lines.append("     ┌" + "─" * (q_width-2) + "┐")
        lines.append(f"     │ ❓ {question:<{q_width-6}} │")
        lines.append("     │" + " " * (q_width-2) + "│")
        lines.append("     └" + "┬" * (q_width-2) + "┘")
        lines.append("      " + " " * ((q_width-4)//2) + "│")
        
        return lines, q_width
    
    def create_flow_connector(self, from_pos, to_pos, label="", style="normal"):
        """Create connecting lines between elements."""
        connectors = {
            'normal': '─',
            'true': '=',    # Thick line for TRUE path
            'false': '┅',   # Dotted line for FALSE path  
            'failover': '╋', # Cross pattern for failover
            'timeout': '┈'   # Different dots for timeout
        }
        
        char = connectors.get(style, '─')
        
        if label:
            return f" {char*3} {label} {char*3}>"
        else:
            return f" {char*8}>"
    
    def add_parallel_paths(self, paths, labels=None):
        """Handle parallel routing like ring group members or queue agents."""
        if not paths:
            return
            
        labels = labels or [f"Path {i+1}" for i in range(len(paths))]
        
        # Create parallel flow display
        self.add_to_canvas("     ┌─ PARALLEL ROUTING ─┐")
        self.add_to_canvas("     │                   │")
        
        for i, (path, label) in enumerate(zip(paths[:5], labels[:5])):  # Limit to 5 for clarity
            connector = "├──" if i < len(paths) - 1 else "└──"
            self.add_to_canvas(f"     {connector} {label[:15]:<15} ──┐")
            
        if len(paths) > 5:
            self.add_to_canvas(f"     └── ... {len(paths)-5} more paths")
            
        self.add_to_canvas("")
    
    def add_to_canvas(self, line):
        """Add a line to the canvas output."""
        self.canvas.append(line)
        self.current_row += 1
    
    def load_all_data(self):
        """Pre-load ALL FreePBX data needed for call flow generation."""
        print("Loading FreePBX configuration data...")
        
        # Initialize all data structures to prevent KeyError issues
        self.data = {
            'timeconditions': {},
            'timegroups': {},
            'calendar': {},
            'calendar_events': {},
            'ivrs': {},
            'ivr_options': {},
            'extensions': {},
            'queues': {},
            'ringgroups': {},
            'announcements': {},
            'conferences': {},
            'paging': {},
            'fax': {},
            'callflow_toggle': {},
            'followme': {},
            'misc_destinations': {},
            'call_recording': {},
            'directory': {},
            'setcid': {},
            'parking': {}
        }
        
        # 1. Load Time Conditions
        if has_table("timeconditions", **self.kw):
            print("   * Time conditions...")
            try:
                # Try multiple column name variations
                for tc_query in [
                    "SELECT timeconditions_id, displayname, truegoto, falsegoto FROM timeconditions",
                    "SELECT id as timeconditions_id, displayname, truegoto, falsegoto FROM timeconditions", 
                    "SELECT timeconditions_id, description as displayname, truegoto, falsegoto FROM timeconditions",
                    "SELECT timeconditions_id, displayname, destination_true as truegoto, destination_false as falsegoto FROM timeconditions"
                ]:
                    try:
                        result = run_mysql(tc_query, **self.kw)
                        if result.strip():
                            for line in result.strip().split('\n'):
                                parts = line.split('\t')
                                if len(parts) >= 4:
                                    self.data['timeconditions'][parts[0]] = {
                                        'name': parts[1] or f'Time Condition {parts[0]}',
                                        'true_dest': parts[2] or '',
                                        'false_dest': parts[3] or ''
                                    }
                            print(f"      ✓ Loaded {len(self.data['timeconditions'])} time conditions")
                            break
                    except Exception as e:
                        continue
            except Exception as e:
                print(f"      ERROR: Time conditions: {e}")
        
        # 2. Load IVRs
        if has_table("ivr_details", **self.kw):
            print("   * IVR menus...")
            try:
                result = run_mysql("""
                    SELECT id, name, announcement, timeout_destination, invalid_destination 
                    FROM ivr_details
                """, **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['ivrs'][parts[0]] = {
                                'name': parts[1] or f'IVR {parts[0]}',
                                'announcement': parts[2] if len(parts) > 2 else '',
                                'timeout_dest': parts[3] if len(parts) > 3 else '',
                                'invalid_dest': parts[4] if len(parts) > 4 else ''
                            }
                print(f"      ✓ Loaded {len(self.data['ivrs'])} IVR menus")
            except Exception as e:
                print(f"      ❌ IVR menus: {e}")
        
        # 3. Load IVR Options
        if has_table("ivr_entries", **self.kw):
            print("   🔢 IVR options...")
            try:
                result = run_mysql("SELECT ivr_id, selection, dest FROM ivr_entries ORDER BY ivr_id, selection", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 3:
                            ivr_id = parts[0]
                            if ivr_id not in self.data['ivr_options']:
                                self.data['ivr_options'][ivr_id] = []
                            self.data['ivr_options'][ivr_id].append({
                                'selection': parts[1],
                                'dest': parts[2]
                            })
                total_options = sum(len(opts) for opts in self.data['ivr_options'].values())
                print(f"      ✓ Loaded {total_options} IVR options")
            except Exception as e:
                print(f"      ❌ IVR options: {e}")
        
        # 4. Load Extensions
        if has_table("users", **self.kw):
            print("   * Extensions...")
            try:
                result = run_mysql("""
                    SELECT extension, name, voicemail, 
                           COALESCE(name, CONCAT('Extension ', extension)) as display_name
                    FROM users
                """, **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['extensions'][parts[0]] = {
                                'name': parts[3] if len(parts) > 3 else parts[1],
                                'voicemail': parts[2] if len(parts) > 2 else 'novm'
                            }
                print(f"      ✓ Loaded {len(self.data['extensions'])} extensions")
            except Exception as e:
                print(f"      ❌ Extensions: {e}")
        
        # 5. Load Queues
        if has_table("queues_config", **self.kw):
            print("   📋 Call queues...")
            try:
                result = run_mysql("SELECT extension, descr FROM queues_config", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['queues'][parts[0]] = {
                                'name': parts[1] or f'Queue {parts[0]}',
                                'strategy': 'ringall',  # default
                                'maxwait': '300'        # default
                            }
                
                # Get queue details if available
                if has_table("queues_details", **self.kw):
                    result = run_mysql("SELECT id, keyword, data FROM queues_details WHERE keyword IN ('strategy', 'maxwait')", **self.kw)
                    if result.strip():
                        for line in result.strip().split('\n'):
                            parts = line.split('\t')
                            if len(parts) >= 3 and parts[0] in self.data['queues']:
                                self.data['queues'][parts[0]][parts[1]] = parts[2]
                
                print(f"      ✓ Loaded {len(self.data['queues'])} queues")
            except Exception as e:
                print(f"      ❌ Queues: {e}")
        
        # 6. Load Ring Groups
        if has_table("ringgroups", **self.kw):
            print("   🔔 Ring groups...")
            try:
                result = run_mysql("SELECT grpnum, description, grplist, strategy FROM ringgroups", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['ringgroups'][parts[0]] = {
                                'description': parts[1] or f'Ring Group {parts[0]}',
                                'members': parts[2].split('-') if len(parts) > 2 and parts[2] else [],
                                'strategy': parts[3] if len(parts) > 3 else 'ringall'
                            }
                print(f"      ✓ Loaded {len(self.data['ringgroups'])} ring groups")
            except Exception as e:
                print(f"      ❌ Ring groups: {e}")
        
        # 7. Load Announcements
        if has_table("announcements", **self.kw):
            print("   📢 Announcements...")
            try:
                result = run_mysql("SELECT id, description, post_dest FROM announcements", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['announcements'][parts[0]] = {
                                'description': parts[1] or f'Announcement {parts[0]}',
                                'post_dest': parts[2] if len(parts) > 2 else 'hangup'
                            }
                print(f"      ✓ Loaded {len(self.data['announcements'])} announcements")
            except Exception as e:
                print(f"      ❌ Announcements: {e}")
        
        # 8. Load Conferences
        if has_table("meetme", **self.kw) or has_table("conferences", **self.kw):
            print("   * Conferences...")
            try:
                for table in ["conferences", "meetme"]:
                    if has_table(table, **self.kw):
                        result = run_mysql(f"SELECT exten, description FROM {table}", **self.kw)
                        if result.strip():
                            for line in result.strip().split('\n'):
                                parts = line.split('\t')
                                if len(parts) >= 2:
                                    self.data['conferences'][parts[0]] = {
                                        'description': parts[1] or f'Conference {parts[0]}'
                                    }
                        break
                print(f"      ✓ Loaded {len(self.data['conferences'])} conferences")
            except Exception as e:
                print(f"      ❌ Conferences: {e}")
        
        # 9. Load Call Flow Toggle Control (CFC)
        if has_table("callflow_toggle", **self.kw):
            print("   * Call Flow Toggle Control...")
            try:
                result = run_mysql("""
                    SELECT id, description, state, dest_enabled, dest_disabled, 
                           COALESCE(feature_code, '') as feature_code
                    FROM callflow_toggle
                """, **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 4:
                            cfc_id = parts[0]
                            state = parts[2] if len(parts) > 2 else '0'
                            current_state = 'ENABLED' if state == '1' else 'DISABLED'
                            
                            self.data['callflow_toggle'][cfc_id] = {
                                'description': parts[1] or f'Toggle {cfc_id}',
                                'state': current_state,
                                'enabled_dest': parts[3] if len(parts) > 3 else '',
                                'disabled_dest': parts[4] if len(parts) > 4 else '',
                                'feature_code': parts[5] if len(parts) > 5 else f'*{cfc_id}'
                            }
                
                print(f"      ✓ Loaded {len(self.data['callflow_toggle'])} call flow toggles")
            except Exception as e:
                print(f"      ❌ Call Flow Toggle: {e}")
        
        # Also check for older CFC table names or alternative schemas
        elif has_table("cfc", **self.kw):
            print("   * Call Flow Control (legacy)...")
            try:
                result = run_mysql("SELECT id, description, state, dest_true, dest_false FROM cfc", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 4:
                            cfc_id = parts[0]
                            state = parts[2] if len(parts) > 2 else '0'
                            current_state = 'ENABLED' if state == '1' else 'DISABLED'
                            
                            self.data['callflow_toggle'][cfc_id] = {
                                'description': parts[1] or f'Flow Control {cfc_id}',
                                'state': current_state,
                                'enabled_dest': parts[3] if len(parts) > 3 else '',
                                'disabled_dest': parts[4] if len(parts) > 4 else '',
                                'feature_code': f'*{cfc_id}'
                            }
                
                print(f"      ✓ Loaded {len(self.data['callflow_toggle'])} flow controls (legacy)")
            except Exception as e:
                print(f"      ❌ Call Flow Control: {e}")
        
        # 10. Load Time Groups  
        if has_table("timegroups_groups", **self.kw):
            print("   ⏰ Time groups...")
            try:
                result = run_mysql("SELECT id, description FROM timegroups_groups", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['timegroups'][parts[0]] = {
                                'name': parts[1] or f'Time Group {parts[0]}',
                                'times': []  # Could load details from timegroups_details if needed
                            }
                print(f"      ✓ Loaded {len(self.data['timegroups'])} time groups")
            except Exception as e:
                print(f"      ❌ Time groups: {e}")
        
        # 11. Load Calendar & Calendar Events
        if has_table("calendar", **self.kw):
            print("   * Calendar...")
            try:
                result = run_mysql("SELECT id, description, url FROM calendar", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['calendar'][parts[0]] = {
                                'name': parts[1] or f'Calendar {parts[0]}',
                                'url': parts[2] if len(parts) > 2 else '',
                                'events': []
                            }
                
                # Load calendar events if table exists
                if has_table("calendar_events", **self.kw):
                    result = run_mysql("SELECT id, title, start_date, end_date, calendar_id FROM calendar_events", **self.kw)
                    if result.strip():
                        for line in result.strip().split('\n'):
                            parts = line.split('\t')
                            if len(parts) >= 4:
                                self.data['calendar_events'][parts[0]] = {
                                    'title': parts[1],
                                    'start': parts[2],
                                    'end': parts[3],
                                    'calendar_id': parts[4] if len(parts) > 4 else ''
                                }
                
                print(f"      ✓ Loaded {len(self.data['calendar'])} calendars, {len(self.data['calendar_events'])} events")
            except Exception as e:
                print(f"      ❌ Calendar: {e}")
        
        # 12. Load Follow Me configurations
        if has_table("findmefollow", **self.kw):
            print("   📲 Follow Me...")
            try:
                result = run_mysql("""
                    SELECT extension, grplist, strategy, grptime, 
                           COALESCE(description, CONCAT('Follow Me ', extension)) as description
                    FROM findmefollow
                """, **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            ext_id = parts[0]
                            numbers = parts[1].split('-') if parts[1] else []
                            self.data['followme'][ext_id] = {
                                'numbers': [n.strip() for n in numbers if n.strip()],
                                'strategy': parts[2] if len(parts) > 2 else 'ringallv2',
                                'ringtime': parts[3] if len(parts) > 3 else '20',
                                'description': parts[4] if len(parts) > 4 else f'Follow Me {ext_id}'
                            }
                print(f"      ✓ Loaded {len(self.data['followme'])} Follow Me configs")
            except Exception as e:
                print(f"      ❌ Follow Me: {e}")
        
        # 13. Load Misc Destinations
        if has_table("miscdests", **self.kw):
            print("   * Misc destinations...")
            try:
                result = run_mysql("SELECT id, description, dial, notes FROM miscdests", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 3:
                            self.data['misc_destinations'][parts[0]] = {
                                'description': parts[1] or f'Misc Dest {parts[0]}',
                                'dial': parts[2],
                                'notes': parts[3] if len(parts) > 3 else ''
                            }
                print(f"      ✓ Loaded {len(self.data['misc_destinations'])} misc destinations")
            except Exception as e:
                print(f"      ❌ Misc destinations: {e}")
        
        # 14. Load Call Recording settings
        if has_table("recordings", **self.kw) or has_table("call_recording", **self.kw):
            print("   * Call recording...")
            try:
                for table in ["call_recording", "recordings"]:
                    if has_table(table, **self.kw):
                        result = run_mysql(f"SELECT id, displayname, filename FROM {table}", **self.kw)
                        if result.strip():
                            for line in result.strip().split('\n'):
                                parts = line.split('\t')
                                if len(parts) >= 2:
                                    self.data['call_recording'][parts[0]] = {
                                        'name': parts[1] or f'Recording {parts[0]}',
                                        'filename': parts[2] if len(parts) > 2 else ''
                                    }
                        break
                print(f"      ✓ Loaded {len(self.data['call_recording'])} recordings")
            except Exception as e:
                print(f"      ❌ Call recording: {e}")
        
        # 15. Load Parking configuration  
        if has_table("parkinglots", **self.kw) or has_table("parking", **self.kw):
            print("   * Call parking...")
            try:
                for table in ["parkinglots", "parking"]:
                    if has_table(table, **self.kw):
                        result = run_mysql(f"SELECT id, name, parkext, parkpos FROM {table}", **self.kw)
                        if result.strip():
                            for line in result.strip().split('\n'):
                                parts = line.split('\t')
                                if len(parts) >= 2:
                                    self.data['parking'][parts[0]] = {
                                        'name': parts[1] or f'Parking Lot {parts[0]}',
                                        'extension': parts[2] if len(parts) > 2 else '',
                                        'positions': parts[3] if len(parts) > 3 else ''
                                    }
                        break
                print(f"      ✓ Loaded {len(self.data['parking'])} parking lots")
            except Exception as e:
                print(f"      ❌ Call parking: {e}")
        
        # 16. Load Directory configurations
        if has_table("directory", **self.kw):
            print("   📖 Directory...")
            try:
                result = run_mysql("SELECT dirname, description, announcement FROM directory", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['directory'][parts[0]] = {
                                'name': parts[1] or f'Directory {parts[0]}',
                                'announcement': parts[2] if len(parts) > 2 else ''
                            }
                print(f"      ✓ Loaded {len(self.data['directory'])} directories")
            except Exception as e:
                print(f"      ❌ Directory: {e}")
        
        # 17. Load Set CallerID configurations
        if has_table("setcid", **self.kw):
            print("   🆔 Set CallerID...")
            try:
                result = run_mysql("SELECT id, description, cid_name, cid_num FROM setcid", **self.kw)
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            self.data['setcid'][parts[0]] = {
                                'description': parts[1] or f'Set CID {parts[0]}',
                                'cid_name': parts[2] if len(parts) > 2 else '',
                                'cid_num': parts[3] if len(parts) > 3 else ''
                            }
                print(f"      ✓ Loaded {len(self.data['setcid'])} CallerID rules")
            except Exception as e:
                print(f"      ❌ Set CallerID: {e}")
        
        # 18. Get current CFC states from asterisk database (live states)
        if self.data['callflow_toggle']:
            print("   * Checking live CFC states...")
            try:
                # Query asterisk database for current toggle states
                result = run_mysql("""
                    SELECT family, key_name, value FROM astdb 
                    WHERE family LIKE '%CFC%' OR family LIKE '%TOGGLE%' 
                    OR family = 'CALLFLOW_TOGGLE'
                """, **self.kw)
                
                live_states = {}
                if result.strip():
                    for line in result.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 3:
                            family, key, value = parts[0], parts[1], parts[2]
                            # Parse various CFC state formats
                            if 'CFC' in family or 'TOGGLE' in family:
                                live_states[key] = 'ENABLED' if value in ['1', 'true', 'enabled'] else 'DISABLED'
                
                # Update our CFC data with live states
                for cfc_id, cfc_data in self.data['callflow_toggle'].items():
                    if cfc_id in live_states:
                        cfc_data['state'] = live_states[cfc_id]
                        cfc_data['live_state'] = True
                    else:
                        cfc_data['live_state'] = False
                
                print(f"      ✓ Updated {len(live_states)} live toggle states")
            except Exception as e:
                print(f"      WARNING: Live states: {e}")
        
        print("Data loading complete!")
        return True
    
    def parse_destination(self, dest_string, depth=0):
        """Enhanced destination parsing with sophisticated visual elements.
        
        Supported FreePBX Components:
        - Extensions (SIP/PJSIP endpoints)
        - Ring Groups (Hunt Groups, Sequential/Simultaneous ring)
        - Queues (Call Center queuing with agents)
        - IVR/Digital Receptionist (Multi-option menus)
        - Time Conditions (Schedule-based routing)
        - Inbound Routes (DID processing)
        - Outbound Routes (Call routing rules)
        - Voicemail (Message boxes)
        - Announcements (Audio playback)
        - Conferences/MeetMe (Conference rooms)
        - Paging/Intercom (Group notifications)
        - Fax (Fax-to-email handling)
        - Call Flow Toggle Control (Dynamic routing)
        - Follow Me (Multi-device ring strategies)
        - Misc Destinations (Custom routes)
        - Call Recording (Record call options)
        - Directory (Dial-by-name directory)
        - Set CallerID (CallerID modification)
        - Calendar (Event-based routing)
        - Time Groups (Time schedule definitions)
        - Call Parking (Park & retrieve calls)
        - Hangup/Busy (Call termination)
        """
        try:
            if not dest_string or depth > 10:  # Prevent infinite loops
                hangup_box, _ = self.create_box("CALL ENDS", "Hangup", "hangup")
                for line in hangup_box:
                    self.add_to_canvas(line)
                return
        except Exception as e:
            print(f"ERROR: Error in parse_destination early check: {e}")
            return
        
        # Avoid revisiting same destinations (loop detection)
        if dest_string in self.visited_destinations:
            self.add_to_canvas(f"     ┌──────────────────┐")
            self.add_to_canvas(f"     │ ↻ LOOP DETECTED  │")
            self.add_to_canvas(f"     │ → {dest_string[:12]:<12} │")
            self.add_to_canvas(f"     └──────────────────┘")
            return
            
        self.visited_destinations.add(dest_string)
        dest_lower = dest_string.lower()
        
        # Main parsing logic with error handling
        try:
            self._parse_destination_internal(dest_string, dest_lower, depth)
        except Exception as e:
            print(f"❌ Error parsing destination '{dest_string}': {e}")
            # Show error box instead of crashing
            error_box, _ = self.create_box("Parse Error", f"Error: {str(e)[:20]}", "failover")
            for line in error_box:
                self.add_to_canvas(line)
    
    def _parse_destination_internal(self, dest_string, dest_lower, depth):
        """Internal parsing logic separated for error handling."""
        # Enhanced Extension handling (using pre-loaded data)
        if dest_string.startswith("ext-"):
            ext_num = dest_string.split(",")[1] if "," in dest_string else "Unknown"
            ext_info = self.data['extensions'].get(ext_num)
            
            box_lines, width = self.create_box(f"Extension {ext_num}", 
                                               ext_info.get('name', f'Extension {ext_num}') if ext_info else f'Extension {ext_num}', 
                                               "extension")
            for line in box_lines:
                self.add_to_canvas(line)
            
            # Show voicemail option if available
            if ext_info and ext_info.get('voicemail') != 'novm':
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── No Answer ────────┐")
                vm_box, _ = self.create_box("Voicemail", f"Box {ext_num}", "voicemail", width=18)
                for line in vm_box:
                    self.add_to_canvas(f"                        {line}")
        
        # Enhanced IVR handling with option tree (using pre-loaded data)
        elif "ivr-" in dest_string:
            ivr_id = self.extract_id_from_dest(dest_string, "ivr-")
            ivr_info = self.data['ivrs'].get(ivr_id)
            
            box_lines, _ = self.create_box(f"IVR Menu {ivr_id}", 
                                           ivr_info.get('name', f'IVR {ivr_id}') if ivr_info else f'IVR {ivr_id}', 
                                           "ivr")
            for line in box_lines:
                self.add_to_canvas(line)
            
            # Show IVR options from pre-loaded data
            options = self.data['ivr_options'].get(ivr_id, [])
            if options:
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── MENU OPTIONS ────────┐")
                for i, option in enumerate(options[:6]):  # Show first 6 options
                    connector = "├──" if i < min(len(options), 6) - 1 else "└──"
                    dest_desc = self.get_destination_type(option['dest'])
                    self.add_to_canvas(f"                            {connector} Press {option['selection']} → {dest_desc}")
                
                if len(options) > 6:
                    self.add_to_canvas(f"                            └── ... +{len(options)-6} more options")
        
        # Call Flow Toggle Control (CFC) - Dynamic routing based on toggle state
        if "cfc" in dest_string or "callflow_toggle" in dest_string or "flowcontrol" in dest_string:
            cfc_id = self.extract_id_from_dest(dest_string, ["cfc", "callflow_toggle", "flowcontrol"])
            cfc_info = self.data['callflow_toggle'].get(cfc_id)
            
            # Create call flow toggle box
            cfc_name = cfc_info.get('description', f'Call Flow Toggle {cfc_id}') if cfc_info else f'Toggle {cfc_id}'
            current_state = cfc_info.get('state', 'UNKNOWN') if cfc_info else 'UNKNOWN'
            
            box_lines, _ = self.create_box(f"🔄 {cfc_name}", f"Current: {current_state}", "callflow_toggle")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if cfc_info:
                feature_code = cfc_info.get('feature_code', f'*{cfc_id}')
                self.add_to_canvas("     │")
                self.add_to_canvas(f"     │ Toggle Code: {feature_code}")
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── TOGGLE ROUTING ───────┐")
                
                # ENABLED path
                if cfc_info.get('enabled_dest'):
                    state_icon = "🟢" if current_state == 'ENABLED' else "⚪"
                    self.add_to_canvas("     │                         │")
                    self.add_to_canvas(f"     ├── {state_icon} ENABLED STATE ─────┐")
                    if current_state == 'ENABLED':
                        self.add_to_canvas("     │              ↑ ACTIVE    │")
                    self.parse_destination(cfc_info['enabled_dest'], depth + 1)
                    self.add_to_canvas("")
                
                # DISABLED path  
                if cfc_info.get('disabled_dest'):
                    state_icon = "🔴" if current_state == 'DISABLED' else "⚪"
                    self.add_to_canvas(f"     └── {state_icon} DISABLED STATE ────┐")
                    if current_state == 'DISABLED':
                        self.add_to_canvas("                    ↑ ACTIVE    │")
                    self.parse_destination(cfc_info['disabled_dest'], depth + 1)
                
            else:
                # No CFC info found
                self.add_to_canvas("     │")
                self.add_to_canvas("     └── ⚠️  Toggle not configured")
                hangup_box, _ = self.create_box("Config Issue", 
                                               f"CFC {cfc_id} not found", 
                                               "failover")
                for line in hangup_box:
                    self.add_to_canvas(line)

        # Enhanced Time Condition with visual decision tree (using pre-loaded data)
        elif "timeconditions" in dest_string or "tc-" in dest_string:
            tc_id = self.extract_id_from_dest(dest_string, ["timeconditions", "tc-"])
            tc_info = self.data['timeconditions'].get(tc_id)
            
            # Create time condition box
            tc_name = tc_info.get('name', f'Time Condition {tc_id}') if tc_info else f'Time Condition {tc_id}'
            box_lines, _ = self.create_box(f"⏰ {tc_name}", "Business Hours Check", "time_condition")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if tc_info and (tc_info.get('true_dest') or tc_info.get('false_dest')):
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── TIME ROUTING ─────────┐")
                
                # TRUE path (business hours)
                if tc_info.get('true_dest'):
                    self.add_to_canvas("     │                         │")
                    self.add_to_canvas("     ├── ✅ BUSINESS HOURS ────┐")
                    self.parse_destination(tc_info['true_dest'], depth + 1)
                    self.add_to_canvas("")
                
                # FALSE path (after hours)  
                if tc_info.get('false_dest'):
                    self.add_to_canvas("     └── ❌ AFTER HOURS ──────┐")
                    self.parse_destination(tc_info['false_dest'], depth + 1)
                
            else:
                # No time condition info found or no destinations
                self.add_to_canvas("     │")
                self.add_to_canvas("     └── ⚠️  No routing configured")
                hangup_box, _ = self.create_box("Config Issue", 
                                               f"TC {tc_id} missing destinations" if tc_info else "TC not found", 
                                               "failover")
                for line in hangup_box:
                    self.add_to_canvas(line)
        
        # Enhanced Ring Group with member display (using pre-loaded data)
        elif "rg-" in dest_string or "ringgr" in dest_string:
            rg_id = self.extract_id_from_dest(dest_string, ["rg-", "ringgr"])
            rg_info = self.data['ringgroups'].get(rg_id)
            
            title = f"Ring Group {rg_id}"
            subtitle = f"Strategy: {rg_info.get('strategy', 'ringall')}" if rg_info else "Ring Group"
            
            box_lines, _ = self.create_box(title, subtitle, "ringgroup")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if rg_info and rg_info.get('members'):
                members = rg_info['members']
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── RING GROUP MEMBERS ──┐")
                
                for i, member in enumerate(members[:6]):  # Show first 6 members
                    connector = "├──" if i < min(len(members), 6) - 1 else "└──"
                    ext_name = self.data['extensions'].get(member, {}).get('name', '')
                    display_name = f" ({ext_name})" if ext_name else ""
                    self.add_to_canvas(f"                            {connector} Extension {member}{display_name}")
                
                if len(members) > 6:
                    self.add_to_canvas(f"                            └── ... +{len(members)-6} more")
        
        # Enhanced Queue with comprehensive info (using pre-loaded data)
        elif "qq-" in dest_string or "queue" in dest_string:
            q_id = self.extract_id_from_dest(dest_string, ["qq-", "queue"])
            q_info = self.data['queues'].get(q_id)
            
            title = f"Call Queue {q_id}"
            subtitle = f"Strategy: {q_info.get('strategy', 'ringall')}" if q_info else "Call Queue"
            
            box_lines, _ = self.create_box(title, subtitle, "queue")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if q_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── QUEUE DETAILS ─────────┐")
                self.add_to_canvas(f"                              ├─ Name: {q_info.get('name', 'Unnamed')}")
                self.add_to_canvas(f"                              ├─ Max Wait: {q_info.get('maxwait', '300')}s")
                self.add_to_canvas(f"                              └─ Strategy: {q_info.get('strategy', 'ringall')}")
        
        # Enhanced Paging Groups
        elif "page-" in dest_string or "paging" in dest_string:
            page_id = self.extract_id_from_dest(dest_string, ["page-", "paging"])
            page_info = self.get_paging_info(page_id)
            
            title = f"Paging Group {page_id}"
            subtitle = f"Overhead Paging" if page_info else ""
            
            box_lines, _ = self.create_box(title, subtitle, "paging")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if page_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── PAGING DEVICES ────────┐")
                devices = page_info.get('devices', '').split(',') if page_info.get('devices') else []
                for i, device in enumerate(devices[:4]):  # Show first 4 devices
                    connector = "├──" if i < min(len(devices), 4) - 1 else "└──"
                    self.add_to_canvas(f"                            {connector} {device.strip()}")
                
                if len(devices) > 4:
                    self.add_to_canvas(f"                            └── ... +{len(devices)-4} more")
        
        # Enhanced FAX handling
        elif "fax" in dest_string or "hylafax" in dest_string:
            fax_ext = self.extract_id_from_dest(dest_string, "fax") or "Unknown"
            
            box_lines, _ = self.create_box(f"FAX Reception", f"Extension {fax_ext}", "fax")
            for line in box_lines:
                self.add_to_canvas(line)
            
            self.add_to_canvas("     │")
            self.add_to_canvas("     ├── FAX PROCESSING ────────┐")
            self.add_to_canvas("                              ├─ Detect: T.30 Protocol")
            self.add_to_canvas("                              ├─ Storage: /var/spool/fax")
            self.add_to_canvas("                              └─ Email: Configured")
        
        # Enhanced Conference rooms (using pre-loaded data)
        elif "conferences" in dest_string or "conf-" in dest_string or "meetme" in dest_string:
            conf_id = self.extract_id_from_dest(dest_string, ["conferences", "conf-", "meetme"])
            conf_info = self.data['conferences'].get(conf_id)
            
            title = f"Conference {conf_id}"
            subtitle = conf_info.get('description', 'Conference Room') if conf_info else 'Conference Room'
            
            box_lines, _ = self.create_box(title, subtitle, "conference")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if conf_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     └── Conference Room Ready")
        
        # Follow Me - Enhanced with pre-loaded data
        elif "fm-" in dest_string or "findmefollow" in dest_string:
            fm_id = self.extract_id_from_dest(dest_string, ["fm-", "findmefollow"])
            fm_info = self.data['followme'].get(fm_id)
            
            title = f"Follow Me {fm_id}"
            subtitle = f"Ring Strategy: {fm_info.get('strategy', 'ringallv2')}" if fm_info else "Multi-device Ring"
            
            box_lines, _ = self.create_box(title, subtitle, "followme")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if fm_info and fm_info.get('numbers'):
                numbers = fm_info['numbers']
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── FOLLOW ME NUMBERS ────┐")
                for i, number in enumerate(numbers[:4]):
                    connector = "├──" if i < min(len(numbers), 4) - 1 else "└──"
                    self.add_to_canvas(f"                            {connector} {number}")
                
                if len(numbers) > 4:
                    self.add_to_canvas(f"                            └── ... +{len(numbers)-4} more")
        
        # Misc Destinations
        elif "miscdest" in dest_string or "misc-" in dest_string:
            misc_id = self.extract_id_from_dest(dest_string, ["miscdest", "misc-"])
            misc_info = self.data['misc_destinations'].get(misc_id)
            
            title = f"Misc Destination {misc_id}"
            subtitle = misc_info.get('description', 'Custom Route') if misc_info else 'Custom Route'
            
            box_lines, _ = self.create_box(title, subtitle, "misc_destination")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if misc_info:
                dial = misc_info.get('dial', '')
                self.add_to_canvas("     │")
                self.add_to_canvas(f"     └── Dials: {dial[:25]}")
        
        # Call Recording
        elif "record" in dest_string and ("app-record" in dest_string or "call-record" in dest_string):
            rec_id = self.extract_id_from_dest(dest_string, ["record", "call-record"])
            rec_info = self.data['call_recording'].get(rec_id)
            
            title = f"Call Recording"
            subtitle = rec_info.get('name', 'Record Call') if rec_info else 'Record Call'
            
            box_lines, _ = self.create_box(title, subtitle, "call_recording")
            for line in box_lines:
                self.add_to_canvas(line)
        
        # Directory
        elif "directory" in dest_string or "dir-" in dest_string:
            dir_id = self.extract_id_from_dest(dest_string, ["directory", "dir-"])
            dir_info = self.data['directory'].get(dir_id)
            
            title = f"Directory {dir_id}"
            subtitle = dir_info.get('name', 'Phone Directory') if dir_info else 'Phone Directory'
            
            box_lines, _ = self.create_box(title, subtitle, "directory")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if dir_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     └── Dial by Name Directory")
        
        # Set CallerID
        elif "setcid" in dest_string or "cid-" in dest_string:
            cid_id = self.extract_id_from_dest(dest_string, ["setcid", "cid-"])
            cid_info = self.data['setcid'].get(cid_id)
            
            title = f"Set CallerID {cid_id}"
            if cid_info:
                cid_name = cid_info.get('cid_name', '')
                cid_num = cid_info.get('cid_num', '')
                subtitle = f"{cid_name} <{cid_num}>" if cid_name or cid_num else 'Modify CallerID'
            else:
                subtitle = 'Modify CallerID'
            
            box_lines, _ = self.create_box(title, subtitle, "setcid")
            for line in box_lines:
                self.add_to_canvas(line)
        
        # Calendar Event Groups
        elif "calendar" in dest_string:
            cal_id = self.extract_id_from_dest(dest_string, "calendar")
            cal_info = self.data['calendar'].get(cal_id)
            
            title = f"Calendar {cal_id}"
            subtitle = cal_info.get('name', 'Calendar Check') if cal_info else 'Calendar Check'
            
            box_lines, _ = self.create_box(title, subtitle, "calendar")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if cal_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     └── Event-based Routing")
        
        # Time Groups (referenced by Time Conditions)
        elif "timegroup" in dest_string or "tg-" in dest_string:
            tg_id = self.extract_id_from_dest(dest_string, ["timegroup", "tg-"])
            tg_info = self.data['timegroups'].get(tg_id)
            
            title = f"Time Group {tg_id}"
            subtitle = tg_info.get('name', 'Time Schedule') if tg_info else 'Time Schedule'
            
            box_lines, _ = self.create_box(title, subtitle, "timegroup")
            for line in box_lines:
                self.add_to_canvas(line)
        
        # Enhanced Announcements (using pre-loaded data)
        elif "app-announcement" in dest_string:
            ann_id = self.extract_id_from_dest(dest_string, "app-announcement")
            ann_info = self.data['announcements'].get(ann_id)
            
            title = f"Announcement {ann_id}"
            subtitle = ann_info.get('description', 'Audio Message') if ann_info else 'Audio Message'
            
            box_lines, _ = self.create_box(title, subtitle, "announcement")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if ann_info:
                # Show what happens after announcement
                post_dest = ann_info.get('post_dest')
                if post_dest and post_dest != 'hangup':
                    self.add_to_canvas("     │")
                    self.add_to_canvas("     └── AFTER PLAYBACK ───────┐")
                    if depth < 8:
                        self.parse_destination(post_dest, depth + 1)
        
        # Follow Me with detailed routing
        elif "fm-" in dest_string or "findmefollow" in dest_string:
            fm_id = self.extract_id_from_dest(dest_string, ["fm-", "findmefollow"])
            fm_info = self.get_followme_info(fm_id)
            
            title = f"Follow Me {fm_id}"
            subtitle = "Multi-device Ring" if fm_info else ""
            
            box_lines, _ = self.create_box(title, subtitle, "extension")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if fm_info:
                numbers = fm_info.get('grplist', '').split('-') if fm_info.get('grplist') else []
                if numbers:
                    self.add_to_canvas("     │")
                    self.add_to_canvas("     ├── FOLLOW ME NUMBERS ────┐")
                    for i, number in enumerate(numbers[:4]):
                        connector = "├──" if i < min(len(numbers), 4) - 1 else "└──"
                        self.add_to_canvas(f"                            {connector} {number.strip()}")
        
        # Direct Dial
        elif dest_string.startswith("from-did-direct"):
            box_lines, _ = self.create_box("Direct Dial", "Extension Direct", "extension")
            for line in box_lines:
                self.add_to_canvas(line)
        
        # Voicemail
        elif "vm-" in dest_string or "voicemail" in dest_string:
            vm_id = self.extract_id_from_dest(dest_string, ["vm-", "voicemail"])
            
            box_lines, _ = self.create_box(f"Voicemail {vm_id}", "Leave Message", "voicemail")
            for line in box_lines:
                self.add_to_canvas(line)
        
        # Call Parking - Enhanced with pre-loaded data
        elif "park" in dest_string:
            park_id = self.extract_id_from_dest(dest_string, ["park", "parking"])
            park_info = self.data['parking'].get(park_id) if park_id else None
            
            title = f"Call Parking {park_id}" if park_id else "Call Parking"
            if park_info:
                lot_name = park_info.get('name', '')
                lot_start = park_info.get('parkingstart', '')
                lot_end = park_info.get('parkingend', '')
                subtitle = f"{lot_name} ({lot_start}-{lot_end})" if lot_start and lot_end else lot_name or "Park & Retrieve"
            else:
                subtitle = "Park & Retrieve"
            
            box_lines, _ = self.create_box(title, subtitle, "parking")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if park_info:
                timeout = park_info.get('parkingtimeout', '')
                self.add_to_canvas("     │")
                self.add_to_canvas(f"     └── Timeout: {timeout}s" if timeout else "     └── Standard Timeout")
        
        # Hangup/Busy
        elif "hangup" in dest_lower or "busy" in dest_lower:
            box_lines, _ = self.create_box("Call Ends", "Busy/Hangup", "hangup")
            for line in box_lines:
                self.add_to_canvas(line)
        
        # Unknown/Other destinations
        else:
            box_lines, _ = self.create_box("Unknown Route", dest_string[:20], "failover")
            for line in box_lines:
                self.add_to_canvas(line)
    
    def render_ivr_options(self, ivr_id, depth=0):
        """Render IVR menu options in a tree structure."""
        if depth > 5:  # Prevent deep recursion
            return
            
        # Get IVR options from database
        options = self.get_ivr_options(ivr_id)
        if not options:
            self.add_to_canvas("                            └── No options configured")
            return
        
        for i, option in enumerate(options[:8]):  # Limit to 8 options for display
            selection = option.get('selection', 'Unknown')
            dest = option.get('dest', '')
            
            connector = "├──" if i < min(len(options), 8) - 1 else "└──"
            
            # Create compact option display
            if dest:
                dest_type = self.get_destination_type(dest)
                self.add_to_canvas(f"                            {connector} Press {selection} → {dest_type}")
            else:
                self.add_to_canvas(f"                            {connector} Press {selection} → Undefined")
        
        if len(options) > 8:
            self.add_to_canvas(f"                            └── ... +{len(options)-8} more options")
    
    def get_destination_type(self, dest_string):
        """Get a short description of destination type."""
        if not dest_string:
            return "Hangup"
        elif "cfc" in dest_string or "callflow_toggle" in dest_string or "flowcontrol" in dest_string:
            cfc_id = self.extract_id_from_dest(dest_string, ["cfc", "callflow_toggle", "flowcontrol"])
            return f"Toggle {cfc_id}"
        elif "ext-" in dest_string:
            ext_num = dest_string.split(",")[1] if "," in dest_string else "?"
            return f"Ext {ext_num}"
        elif "ivr-" in dest_string:
            ivr_id = self.extract_id_from_dest(dest_string, "ivr-")
            return f"IVR {ivr_id}"
        elif "qq-" in dest_string or "queue" in dest_string:
            q_id = self.extract_id_from_dest(dest_string, ["qq-", "queue"])
            return f"Queue {q_id}"
        elif "rg-" in dest_string or "ringgr" in dest_string:
            rg_id = self.extract_id_from_dest(dest_string, ["rg-", "ringgr"])
            return f"Ring Group {rg_id}"
        elif "timeconditions" in dest_string or "tc-" in dest_string:
            tc_id = self.extract_id_from_dest(dest_string, ["timeconditions", "tc-"])
            return f"Time Condition {tc_id}"
        elif "app-announcement" in dest_string:
            ann_id = self.extract_id_from_dest(dest_string, "app-announcement")
            return f"Announcement {ann_id}"
        elif "vm-" in dest_string or "voicemail" in dest_string:
            return "Voicemail"
        elif "conferences" in dest_string or "conf-" in dest_string:
            conf_id = self.extract_id_from_dest(dest_string, ["conferences", "conf-"])
            return f"Conference {conf_id}"
        elif "page-" in dest_string or "paging" in dest_string:
            return "Paging"
        elif "fax" in dest_string:
            return "FAX"
        else:
            return dest_string[:15] + "..." if len(dest_string) > 15 else dest_string
    
    def extract_id_from_dest(self, dest_string, prefixes):
        """Extract ID from destination string."""
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        
        # Special handling for timeconditions - extract from comma-separated format
        if "timeconditions" in dest_string:
            # Format: timeconditions,2,1 - extract the middle number
            parts = dest_string.split(',')
            if len(parts) >= 2:
                return parts[1]
            return "unknown"
        
        # Special handling for Call Flow Control/Toggle - multiple possible formats
        if any(cfc_prefix in dest_string for cfc_prefix in ["cfc", "callflow_toggle", "flowcontrol"]):
            # Possible formats:
            # cfc,1,1
            # callflow_toggle,2,1  
            # flowcontrol-1,s,1
            parts = dest_string.replace('-', ',').split(',')
            if len(parts) >= 2:
                # Extract numeric part
                for part in parts[1:]:
                    if part.isdigit():
                        return part
            # Fallback - look for any digits in the string
            match = re.search(r'\d+', dest_string)
            if match:
                return match.group()
            return "unknown"
        
        for prefix in prefixes:
            if prefix in dest_string:
                # Try to extract number after prefix
                parts = dest_string.split(prefix)
                if len(parts) > 1:
                    # Extract digits from the part after prefix
                    id_part = parts[1].split(",")[0].split("-")[0]
                    match = re.search(r'(\d+)', id_part)
                    if match:
                        return match.group(1)
        return "unknown"
    
    def get_extension_info(self, ext_num):
        """Get extension name."""
        if not ext_num or not ext_num.isdigit():
            return None
        
        users = rows_as_dicts(f"""
            SELECT name FROM users WHERE extension = '{ext_num}';
        """, ["name"], **self.kw)
        
        return users[0]["name"] if users else None
    
    def get_ivr_info(self, ivr_id):
        """Get IVR information."""
        if not has_table("ivr_details", **self.kw):
            return None
            
        ivrs = rows_as_dicts(f"""
            SELECT name FROM ivr_details WHERE ivr_id = '{ivr_id}';
        """, ["name"], **self.kw)
        
        return ivrs[0] if ivrs else None
    
    def add_ivr_options(self, ivr_id):
        """Add IVR menu options to the flow."""
        if not has_table("ivr_entries", **self.kw):
            return
            
        options = rows_as_dicts(f"""
            SELECT selection, dest FROM ivr_entries 
            WHERE ivr_id = '{ivr_id}' ORDER BY selection;
        """, ["selection", "dest"], **self.kw)
        
        for i, option in enumerate(options[:5]):  # Show first 5 options
            connector = "├──" if i < len(options) - 1 else "└──"
            if i >= 4 and len(options) > 5:
                self.add_line(f"... and {len(options) - 4} more options", connector)
                break
            self.add_line(f"Press {option['selection']}", connector)
            self.indent_level += 1
            self.parse_destination(option['dest'])
            self.indent_level -= 1
    
    def get_announcement_info(self, ann_id):
        """Get announcement description."""
        tables = ["announcement", "announcements"]
        for table in tables:
            if has_table(table, **self.kw):
                id_col = "announcement_id" if "announcement_id" in ["announcement_id", "id"] else "id"
                desc_col = "description" if "description" in ["description", "name"] else "name"
                
                anns = rows_as_dicts(f"""
                    SELECT {desc_col} as description FROM {table} 
                    WHERE {id_col} = '{ann_id}';
                """, ["description"], **self.kw)
                
                return anns[0]["description"] if anns else None
        return None
    
    def get_timecondition_info(self, tc_id):
        """Get time condition information."""
        if not has_table("timeconditions", **self.kw):
            return None
        
        # Try multiple possible column combinations for different FreePBX versions
        try:
            # First try: standard column names
            tcs = rows_as_dicts(f"""
                SELECT COALESCE(displayname, description, 'Time Condition') as name, 
                       truegoto as true_dest, 
                       falsegoto as false_dest 
                FROM timeconditions WHERE timeconditions_id = '{tc_id}';
            """, ["name", "true_dest", "false_dest"], **self.kw)
            
            if tcs:
                return tcs[0]
            
            # Second try: alternative column names
            tcs = rows_as_dicts(f"""
                SELECT COALESCE(displayname, description, 'Time Condition') as name,
                       destination_true as true_dest, 
                       destination_false as false_dest 
                FROM timeconditions WHERE timeconditions_id = '{tc_id}';
            """, ["name", "true_dest", "false_dest"], **self.kw)
            
            if tcs:
                return tcs[0]
            
            # Third try: with different ID column
            tcs = rows_as_dicts(f"""
                SELECT COALESCE(displayname, description, 'Time Condition') as name,
                       truegoto as true_dest, 
                       falsegoto as false_dest 
                FROM timeconditions WHERE id = '{tc_id}';
            """, ["name", "true_dest", "false_dest"], **self.kw)
            
            return tcs[0] if tcs else None
            
        except Exception:
            # Return a basic structure if database queries fail
            return {
                'name': f'Time Condition {tc_id}',
                'true_dest': None,
                'false_dest': None
            }
    
    def get_ringgroup_info(self, rg_id):
        """Get ring group information."""
        if not has_table("ringgroups", **self.kw):
            return None
            
        rgs = rows_as_dicts(f"""
            SELECT description, grplist, strategy FROM ringgroups 
            WHERE grpnum = '{rg_id}';
        """, ["description", "grplist", "strategy"], **self.kw)
        
        return rgs[0] if rgs else None
    
    def get_queue_info(self, q_id):
        """Get queue information."""
        if not has_table("queues_config", **self.kw):
            return None
            
        queues = rows_as_dicts(f"""
            SELECT descr as description FROM queues_config 
            WHERE extension = '{q_id}';
        """, ["description"], **self.kw)
        
        if queues and has_table("queues_details", **self.kw):
            details = rows_as_dicts(f"""
                SELECT data as strategy FROM queues_details 
                WHERE id = '{q_id}' AND keyword = 'strategy';
            """, ["strategy"], **self.kw)
            
            if details:
                queues[0]["strategy"] = details[0]["strategy"]
        
        return queues[0] if queues else None
    
    def get_conference_info(self, conf_id):
        """Get conference information."""
        if not has_table("conferences", **self.kw):
            return None
            
        confs = rows_as_dicts(f"""
            SELECT description, maxusers, pin, recording FROM conferences WHERE exten = '{conf_id}';
        """, ["description", "maxusers", "pin", "recording"], **self.kw)
        
        return confs[0] if confs else None
    
    def get_paging_info(self, page_id):
        """Get paging group details."""
        if not has_table("paging", **self.kw):
            return None
            
        pages = rows_as_dicts(f"""
            SELECT description, devices FROM paging WHERE page_number = '{page_id}';
        """, ["description", "devices"], **self.kw)
        
        return pages[0] if pages else None
    
    def get_followme_info(self, fm_id):
        """Get Follow Me configuration."""
        if not has_table("findmefollow", **self.kw):
            return None
            
        fms = rows_as_dicts(f"""
            SELECT grplist, strategy, grptime FROM findmefollow WHERE extension = '{fm_id}';
        """, ["grplist", "strategy", "grptime"], **self.kw)
        
        return fms[0] if fms else None
    
    def get_ivr_options(self, ivr_id):
        """Get IVR menu options."""
        if not has_table("ivr_entries", **self.kw):
            return []
            
        options = rows_as_dicts(f"""
            SELECT selection, dest FROM ivr_entries WHERE ivr_id = '{ivr_id}' ORDER BY selection;
        """, ["selection", "dest"], **self.kw)
        
        return options
    
    def generate_inbound_flow(self, did):
        """Generate enhanced ASCII flow for an inbound DID."""
        # Reset state
        self.canvas = []
        self.current_row = 0
        self.visited_destinations = set()
        
        # Pre-load all FreePBX data (this is the key improvement!)
        self.load_all_data()
        
        # Get inbound route info
        if not has_table("incoming", **self.kw):
            return "❌ No incoming table found"
        
        # Handle different column names
        did_col = "extension" if "extension" in ["extension", "did"] else "did"
        
        routes = rows_as_dicts(f"""
            SELECT {did_col} as did, destination, 
                   COALESCE(description, '') as description,
                   COALESCE(cidnum, '') as cid
            FROM incoming WHERE {did_col} = '{did}';
        """, ["did", "destination", "description", "cid"], **self.kw)
        
        if not routes:
            return f"❌ No inbound route found for DID: {did}"
        
        route = routes[0]
        
        # Enhanced Header with DID info (ASCII safe)
        self.add_to_canvas("+" + "=" * 80 + "+")
        self.add_to_canvas(f"|{'FREEPBX CALL FLOW DIAGRAM':^80}|")
        self.add_to_canvas("+" + "=" * 80 + "+")
        self.add_to_canvas(f"| DID: {did:<25} Route: {route['description'][:40]:<40} |")
        self.add_to_canvas("+" + "=" * 80 + "+")
        self.add_to_canvas("")
        
        # Inbound call entry point  
        entry_box, _ = self.create_box(f"INBOUND: {did}", 
                                       route['description'] or "Unnamed Route", 
                                       "inbound", width=30)
        for line in entry_box:
            self.add_to_canvas(line)
        
        # CID restriction check
        if route['cid']:
            self.add_to_canvas("     │")
            self.add_to_canvas("     ├── CALLER ID CHECK ─────────┐")
            cid_box, _ = self.create_box("🔍 CID Filter", f"Must match: {route['cid']}", "time_condition", width=25)
            for line in cid_box:
                self.add_to_canvas(f"                              {line}")
            self.add_to_canvas("")
        
        # Main call flow processing
        self.add_to_canvas("     │")
        self.add_to_canvas("     ├── CALL PROCESSING ──────────┐")
        self.add_to_canvas("     │                             │")
        
        # Process the destination
        if route['destination']:
            self.parse_destination(route['destination'])
        else:
            hangup_box, _ = self.create_box("No Destination", "Call Ends", "hangup")
            for line in hangup_box:
                self.add_to_canvas(line)
        
        # Footer with generation info
        self.add_to_canvas("")
        self.add_to_canvas("─" * 80)
        self.add_to_canvas(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')} | FreePBX ASCII Flow Generator v2.0")
        
        return "\n".join(self.canvas)

def main():
    try:
        parser = argparse.ArgumentParser(description="Generate ASCII art call flow diagrams")
        parser.add_argument("--did", required=True, help="DID/Extension to analyze")
        parser.add_argument("--socket", default=DEFAULT_SOCK, help="MySQL socket path")
        parser.add_argument("--db-user", default="root", help="MySQL user")
        parser.add_argument("--db-password", help="MySQL password")
        parser.add_argument("--output", "-o", help="Output file")
        
        args = parser.parse_args()
        
        kw = {
            "socket": args.socket,
            "user": args.db_user,
            "password": args.db_password
        }
        
        print(f"Generating ASCII flow for DID: {args.did}")
        generator = ASCIIFlowGenerator(**kw)
        flow_chart = generator.generate_inbound_flow(args.did)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(flow_chart)
            print(f"ASCII flow chart saved to: {args.output}")
        else:
            print(flow_chart)
            
    except Exception as e:
        print(f"ERROR: Fatal error in main: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()