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
        self.flow_lines = []
        self.indent_level = 0
        
    def add_line(self, text, connector="├──", indent_override=None):
        """Add a line to the flow with proper indentation and connectors."""
        actual_indent = indent_override if indent_override is not None else self.indent_level
        spaces = "│   " * actual_indent
        if actual_indent > 0:
            self.flow_lines.append(f"{spaces[:-4]}{connector} {text}")
        else:
            self.flow_lines.append(text)
    
    def add_box(self, title, content, box_type="normal"):
        """Add a text box to the flow."""
        if box_type == "header":
            # Main header box
            width = max(len(title), len(content)) + 4
            self.add_line("┌" + "─" * width + "┐")
            self.add_line(f"│ {title.center(width-2)} │")
            if content:
                self.add_line("├" + "─" * width + "┤")
                self.add_line(f"│ {content.center(width-2)} │")
            self.add_line("└" + "─" * width + "┘")
        elif box_type == "decision":
            # Diamond-like decision box
            self.add_line("     ┌─────────────────┐")
            self.add_line(f"    ◊  {title[:15]:<15}  ◊")
            if content:
                self.add_line(f"     │ {content[:15]:<15} │")
            self.add_line("     └─────────────────┘")
        else:
            # Normal rectangular box
            width = max(len(title), len(content) if content else 0) + 2
            width = max(width, 20)
            self.add_line("┌" + "─" * width + "┐")
            self.add_line(f"│ {title[:width-2]:<{width-2}} │")
            if content:
                self.add_line(f"│ {content[:width-2]:<{width-2}} │")
            self.add_line("└" + "─" * width + "┘")
    
    def add_branch(self, condition, true_dest, false_dest):
        """Add a branching decision point."""
        self.add_line("│")
        self.add_line("├── TRUE ──┐")
        self.indent_level += 1
        self.parse_destination(true_dest)
        self.indent_level -= 1
        self.add_line("│")
        self.add_line("└── FALSE ─┐")
        self.indent_level += 1
        self.parse_destination(false_dest)
        self.indent_level -= 1
    
    def parse_destination(self, dest_string):
        """Parse FreePBX destination string and add appropriate flow elements."""
        if not dest_string:
            self.add_line("[HANGUP]", "└──")
            return
            
        # Parse different destination types
        dest_lower = dest_string.lower()
        
        if dest_string.startswith("ext-"):
            # Extension
            ext_num = dest_string.split(",")[1] if "," in dest_string else "Unknown"
            ext_info = self.get_extension_info(ext_num)
            self.add_line(f"📞 Extension {ext_num}")
            if ext_info:
                self.add_line(f"   ({ext_info})", "│  ")
        
        elif dest_string.startswith("from-did-direct"):
            # Direct inward dial
            self.add_line("📲 Direct Dial")
        
        elif "ivr-" in dest_string:
            # IVR menu
            ivr_id = self.extract_id_from_dest(dest_string, "ivr-")
            ivr_info = self.get_ivr_info(ivr_id)
            self.add_line(f"🎯 IVR Menu {ivr_id}")
            if ivr_info:
                self.add_line(f"   {ivr_info['name']}", "│  ")
                self.indent_level += 1
                self.add_ivr_options(ivr_id)
                self.indent_level -= 1
        
        elif "app-announcement" in dest_string:
            # Announcement
            ann_id = self.extract_id_from_dest(dest_string, "app-announcement")
            ann_info = self.get_announcement_info(ann_id)
            self.add_line(f"📢 Announcement {ann_id}")
            if ann_info:
                self.add_line(f"   {ann_info}", "│  ")
        
        elif "timeconditions" in dest_string or "tc-" in dest_string:
            # Time condition
            tc_id = self.extract_id_from_dest(dest_string, ["timeconditions", "tc-"])
            tc_info = self.get_timecondition_info(tc_id)
            self.add_line(f"⏰ Time Condition {tc_id}")
            if tc_info:
                self.add_line(f"   {tc_info['name']}", "│  ")
                self.indent_level += 1
                self.add_branch("Time Match", tc_info['true_dest'], tc_info['false_dest'])
                self.indent_level -= 1
        
        elif "rg-" in dest_string or "ringgr" in dest_string:
            # Ring group
            rg_id = self.extract_id_from_dest(dest_string, ["rg-", "ringgr"])
            rg_info = self.get_ringgroup_info(rg_id)
            self.add_line(f"🔔 Ring Group {rg_id}")
            if rg_info:
                self.add_line(f"   {rg_info['description']}", "│  ")
                self.add_line(f"   Strategy: {rg_info['strategy']}", "│  ")
                if rg_info['grplist']:
                    exts = [e.strip() for e in rg_info['grplist'].split('-') if e.strip()][:5]
                    self.add_line(f"   Extensions: {', '.join(exts)}", "│  ")
        
        elif "qq-" in dest_string or "queue" in dest_string:
            # Queue
            q_id = self.extract_id_from_dest(dest_string, ["qq-", "queue"])
            q_info = self.get_queue_info(q_id)
            self.add_line(f"📞 Queue {q_id}")
            if q_info:
                self.add_line(f"   {q_info['description']}", "│  ")
                self.add_line(f"   Strategy: {q_info.get('strategy', 'unknown')}", "│  ")
        
        elif "fm-" in dest_string or "findmefollow" in dest_string:
            # Follow Me
            fm_id = self.extract_id_from_dest(dest_string, ["fm-", "findmefollow"])
            self.add_line(f"📱 Follow Me {fm_id}")
        
        elif "conferences" in dest_string or "conf-" in dest_string:
            # Conference
            conf_id = self.extract_id_from_dest(dest_string, ["conferences", "conf-"])
            conf_info = self.get_conference_info(conf_id)
            self.add_line(f"🎤 Conference {conf_id}")
            if conf_info:
                self.add_line(f"   {conf_info['description']}", "│  ")
        
        elif "vm-" in dest_string or "voicemail" in dest_string:
            # Voicemail
            vm_id = self.extract_id_from_dest(dest_string, ["vm-", "voicemail"])
            self.add_line(f"📧 Voicemail {vm_id}")
        
        elif "park" in dest_string:
            # Call parking
            self.add_line("🅿️  Call Parking")
        
        elif "hangup" in dest_lower or "busy" in dest_lower:
            # Hangup/Busy
            self.add_line("❌ Hangup/Busy")
        
        else:
            # Unknown/Custom destination
            self.add_line(f"❓ Custom: {dest_string[:30]}")
    
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
            SELECT description FROM conferences WHERE exten = '{conf_id}';
        """, ["description"], **self.kw)
        
        return confs[0] if confs else None
    
    def generate_inbound_flow(self, did):
        """Generate ASCII flow for an inbound DID."""
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
        self.flow_lines = []
        self.indent_level = 0
        
        # Header
        title = f"📞 INBOUND CALL FLOW: {did}"
        description = route['description'] if route['description'] else "Unnamed Route"
        self.add_box(title, description, "header")
        self.add_line("")
        
        # CID restriction if present
        if route['cid']:
            self.add_line("🔍 Caller ID Check")
            self.add_line(f"   Must match: {route['cid']}")
            self.add_line("   │")
        
        # Start processing the destination
        self.add_line("📥 INCOMING CALL")
        self.add_line("   │")
        self.indent_level = 0
        self.parse_destination(route['destination'])
        
        return "\n".join(self.flow_lines)

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