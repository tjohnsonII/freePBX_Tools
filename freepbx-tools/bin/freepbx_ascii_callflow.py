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

class ASCIIFlowGenerator:
    def __init__(self, **kw):
        self.kw = kw
        self.flow_data = {}
        self.canvas = []
        self.width = 120  # Canvas width for complex layouts
        self.current_row = 0
        self.visited_destinations = set()  # Prevent infinite loops
        
        # Visual styling constants
        self.STYLES = {
            'inbound': {'icon': '📞', 'border': '═', 'color': 'cyan'},
            'time_condition': {'icon': '🕒', 'border': '─', 'color': 'yellow'},
            'ivr': {'icon': '🎯', 'border': '═', 'color': 'blue'},
            'queue': {'icon': '📋', 'border': '─', 'color': 'green'},
            'ringgroup': {'icon': '🔔', 'border': '─', 'color': 'magenta'},
            'extension': {'icon': '📱', 'border': '─', 'color': 'white'},
            'announcement': {'icon': '📢', 'border': '─', 'color': 'orange'},
            'voicemail': {'icon': '📧', 'border': '─', 'color': 'gray'},
            'conference': {'icon': '🎤', 'border': '─', 'color': 'purple'},
            'paging': {'icon': '📯', 'border': '─', 'color': 'red'},
            'fax': {'icon': '📠', 'border': '─', 'color': 'brown'},
            'failover': {'icon': '⚠️', 'border': '┅', 'color': 'red'},
            'hangup': {'icon': '📞', 'border': '╋', 'color': 'red'}
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
        """Create a diamond-shaped decision box for time conditions, IVR choices."""
        q_width = width or len(question) + 6
        q_width = max(q_width, 20)
        
        # Diamond shape using Unicode
        lines = []
        lines.append(f"     {'╱' + ' ' * (q_width-2) + '╲'}")
        lines.append(f"    ╱ {question.center(q_width-2)} ╲")
        lines.append(f"   ╱ {'?' * (q_width-2)} ╲")
        lines.append(f"  ╲ {'Decision Point'.center(q_width-2)} ╱")
        lines.append(f"   ╲ {' ' * (q_width-2)} ╱")
        lines.append(f"    ╲{'_' * (q_width-2)}╱")
        
        return lines, q_width
    
    def create_flow_connector(self, from_pos, to_pos, label="", style="normal"):
        """Create connecting lines between elements."""
        connectors = {
            'normal': '─',
            'true': '═',    # Thick line for TRUE path
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
    
    def parse_destination(self, dest_string, depth=0):
        """Enhanced destination parsing with sophisticated visual elements."""
        if not dest_string or depth > 10:  # Prevent infinite loops
            hangup_box, _ = self.create_box("CALL ENDS", "Hangup", "hangup")
            for line in hangup_box:
                self.add_to_canvas(line)
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
        
        # Enhanced Extension handling
        if dest_string.startswith("ext-"):
            ext_num = dest_string.split(",")[1] if "," in dest_string else "Unknown"
            ext_info = self.get_extension_info(ext_num)
            
            box_lines, width = self.create_box(f"Extension {ext_num}", 
                                               ext_info.get('name', 'No Name') if ext_info else '', 
                                               "extension")
            for line in box_lines:
                self.add_to_canvas(line)
            
            # Show voicemail option if available
            if ext_info and ext_info.get('voicemail'):
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── No Answer ────────┐")
                vm_box, _ = self.create_box("Voicemail", f"Box {ext_num}", "voicemail", width=18)
                for line in vm_box:
                    self.add_to_canvas(f"                        {line}")
        
        # Enhanced IVR handling with option tree
        elif "ivr-" in dest_string:
            ivr_id = self.extract_id_from_dest(dest_string, "ivr-")
            ivr_info = self.get_ivr_info(ivr_id)
            
            box_lines, _ = self.create_box(f"IVR Menu {ivr_id}", 
                                           ivr_info.get('name', 'Unnamed Menu') if ivr_info else '', 
                                           "ivr")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if ivr_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── MENU OPTIONS ────────┐")
                self.render_ivr_options(ivr_id, depth + 1)
        
        # Enhanced Time Condition with visual decision tree
        elif "timeconditions" in dest_string or "tc-" in dest_string:
            tc_id = self.extract_id_from_dest(dest_string, ["timeconditions", "tc-"])
            tc_info = self.get_timecondition_info(tc_id)
            
            # Create decision diamond
            question = f"Time Match: {tc_info.get('name', f'TC-{tc_id}') if tc_info else f'TC-{tc_id}'}"
            diamond_lines, width = self.create_decision_diamond(question)
            for line in diamond_lines:
                self.add_to_canvas(line)
            
            if tc_info:
                # TRUE path (business hours)
                self.add_to_canvas("           │")
                self.add_to_canvas("      ┌────┴────┐")
                self.add_to_canvas("      │  TRUE   │ ╔═══ BUSINESS HOURS ═══╗")
                self.add_to_canvas("      │ (Match) │")
                self.add_to_canvas("      └────┬────┘")
                self.add_to_canvas("           │")
                
                if tc_info.get('true_dest'):
                    self.parse_destination(tc_info['true_dest'], depth + 1)
                
                # FALSE path (after hours)  
                self.add_to_canvas("")
                self.add_to_canvas("      ┌─────────┐")
                self.add_to_canvas("      │  FALSE  │ ╠═══ AFTER HOURS ═══╣")
                self.add_to_canvas("      │(No Match│")
                self.add_to_canvas("      └────┬────┘")
                self.add_to_canvas("           │")
                
                if tc_info.get('false_dest'):
                    self.parse_destination(tc_info['false_dest'], depth + 1)
        
        # Enhanced Ring Group with member display
        elif "rg-" in dest_string or "ringgr" in dest_string:
            rg_id = self.extract_id_from_dest(dest_string, ["rg-", "ringgr"])
            rg_info = self.get_ringgroup_info(rg_id)
            
            title = f"Ring Group {rg_id}"
            subtitle = f"Strategy: {rg_info.get('strategy', 'Unknown')}" if rg_info else ""
            
            box_lines, _ = self.create_box(title, subtitle, "ringgroup")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if rg_info and rg_info.get('grplist'):
                members = [e.strip() for e in rg_info['grplist'].split('-') if e.strip()]
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── RING GROUP MEMBERS ──┐")
                
                for i, member in enumerate(members[:6]):  # Show first 6 members
                    connector = "├──" if i < min(len(members), 6) - 1 else "└──"
                    self.add_to_canvas(f"                            {connector} Extension {member}")
                
                if len(members) > 6:
                    self.add_to_canvas(f"                            └── ... +{len(members)-6} more")
                
                # Show failover destination
                if rg_info.get('postdest'):
                    self.add_to_canvas("")
                    self.add_to_canvas("     ├── NO ANSWER FAILOVER ──┐")
                    failover_box, _ = self.create_box("Failover Route", "No Answer", "failover", width=16)
                    for line in failover_box:
                        self.add_to_canvas(f"                            {line}")
        
        # Enhanced Queue with comprehensive info
        elif "qq-" in dest_string or "queue" in dest_string:
            q_id = self.extract_id_from_dest(dest_string, ["qq-", "queue"])
            q_info = self.get_queue_info(q_id)
            
            title = f"Call Queue {q_id}"
            subtitle = f"Strategy: {q_info.get('strategy', 'Unknown')}" if q_info else ""
            
            box_lines, _ = self.create_box(title, subtitle, "queue")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if q_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── QUEUE DETAILS ─────────┐")
                self.add_to_canvas(f"                              ├─ Max Wait: {q_info.get('maxwait', 'Unlimited')}")
                self.add_to_canvas(f"                              ├─ Retry: {q_info.get('retry', 'Default')}s")
                self.add_to_canvas(f"                              └─ Agents: Dynamic")
                
                # Show queue failover destinations
                failovers = []
                if q_info.get('eventfail'): failovers.append(('Agent Fail', q_info['eventfail']))
                if q_info.get('eventmemberhangup'): failovers.append(('Timeout', q_info['eventmemberhangup']))
                
                for fail_type, fail_dest in failovers:
                    self.add_to_canvas("")
                    self.add_to_canvas(f"     ├── {fail_type.upper()} ROUTE ──┐")
                    # Recursively parse failover destination
                    if depth < 8:  # Prevent deep recursion
                        self.parse_destination(fail_dest, depth + 1)
        
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
        
        # Enhanced Conference rooms
        elif "conferences" in dest_string or "conf-" in dest_string:
            conf_id = self.extract_id_from_dest(dest_string, ["conferences", "conf-"])
            conf_info = self.get_conference_info(conf_id)
            
            title = f"Conference {conf_id}"
            subtitle = conf_info.get('description', 'Conference Room') if conf_info else 'Conference Room'
            
            box_lines, _ = self.create_box(title, subtitle, "conference")
            for line in box_lines:
                self.add_to_canvas(line)
            
            if conf_info:
                self.add_to_canvas("     │")
                self.add_to_canvas("     ├── CONFERENCE OPTIONS ────┐")
                self.add_to_canvas(f"                              ├─ Max Users: {conf_info.get('maxusers', 'Unlimited')}")
                self.add_to_canvas(f"                              ├─ PIN Required: {'Yes' if conf_info.get('pin') else 'No'}")
                self.add_to_canvas(f"                              └─ Recording: {'Yes' if conf_info.get('recording') else 'No'}")
        
        # Enhanced Announcements
        elif "app-announcement" in dest_string:
            ann_id = self.extract_id_from_dest(dest_string, "app-announcement")
            ann_info = self.get_announcement_info(ann_id)
            
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
        
        # Call Parking
        elif "park" in dest_string:
            box_lines, _ = self.create_box("Call Parking", "Park & Retrieve", "extension")
            for line in box_lines:
                self.add_to_canvas(line)
        
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
            
        tcs = rows_as_dicts(f"""
            SELECT displayname as name, destination_true as true_dest, 
                   destination_false as false_dest
            FROM timeconditions WHERE timeconditions_id = '{tc_id}';
        """, ["name", "true_dest", "false_dest"], **self.kw)
        
        return tcs[0] if tcs else None
    
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
        
        # Enhanced Header with DID info
        self.add_to_canvas("╔" + "═" * 80 + "╗")
        self.add_to_canvas(f"║{'📞 FREEPBX CALL FLOW DIAGRAM':^80}║")
        self.add_to_canvas("╠" + "═" * 80 + "╣")
        self.add_to_canvas(f"║ DID: {did:<25} Route: {route['description'][:40]:<40} ║")
        self.add_to_canvas("╚" + "═" * 80 + "╝")
        self.add_to_canvas("")
        
        # Inbound call entry point
        entry_box, _ = self.create_box(f"📞 INBOUND: {did}", 
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
    
    generator = ASCIIFlowGenerator(**kw)
    flow_chart = generator.generate_inbound_flow(args.did)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(flow_chart)
        print(f"✅ ASCII flow chart saved to: {args.output}")
    else:
        print(flow_chart)

if __name__ == "__main__":
    main()