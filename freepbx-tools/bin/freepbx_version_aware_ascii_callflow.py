#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freePBX Complete Version-Aware ASCII Call Flow Generator
Handles FreePBX 2.8 - 16.x, Asterisk 1.8 - 18.x, MySQL/MariaDB variations

This comprehensive version addresses ALL schema variations across FreePBX versions:
- Python 3.6 compatibility (subprocess.run syntax)
- Table name variations (incoming vs inbound_routes, timeconditions vs time_conditions)
- Column name differences (toggle_mode vs mode, mohclass vs rvolume, etc.)
- Version-specific detection and adaptation
"""

import argparse
import json
import subprocess
import sys
import os
import re
import time
from collections import defaultdict

# ANSI Color codes
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

class FreePBXUniversalCollector:
    """Universal FreePBX collector handling all version variations."""
    
    def __init__(self, socket=None, user="root", password=None):
        self.socket = socket or "/var/lib/mysql/mysql.sock"
        self.user = user
        self.password = password
        
        # Version information
        self.freepbx_version = None
        self.asterisk_version = None
        self.db_version = None
        self.freepbx_major = None
        self.asterisk_major = None
        
        # Schema mapping
        self.all_tables = []
        self.schema_map = {}
        self.data = {}
        
    def analyze_system(self):
        """Complete system analysis with version detection and schema discovery."""
        print(Colors.CYAN + Colors.BOLD + "\n╔" + "═" * 78 + "╗" + Colors.RESET)
        print(Colors.CYAN + Colors.BOLD + "║" + Colors.YELLOW + " 🔍 COMPREHENSIVE freePBX SYSTEM ANALYSIS ".center(78) + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + Colors.BOLD + "╚" + "═" * 78 + "╝" + Colors.RESET)
        
        # Phase 1: Version Detection
        self._detect_asterisk_version()
        self._detect_freepbx_version()
        self._detect_database_version()
        self._discover_all_tables()
        
        # System Profile Box
        print(Colors.CYAN + "\n╔" + "═" * 78 + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.WHITE + " 📊 SYSTEM PROFILE".ljust(87) + Colors.CYAN + " ║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.RESET)
        print(Colors.CYAN + "║ " + Colors.WHITE + "freePBX:   " + Colors.GREEN + Colors.BOLD + f"{self.freepbx_version or 'Unknown'}".ljust(25) + Colors.RESET + 
              Colors.WHITE + "│ Major: " + Colors.YELLOW + Colors.BOLD + f"{self.freepbx_major or 'Unknown'}".ljust(30) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
        print(Colors.CYAN + "║ " + Colors.WHITE + "Asterisk:  " + Colors.GREEN + Colors.BOLD + f"{self.asterisk_version or 'Unknown'}".ljust(25) + Colors.RESET + 
              Colors.WHITE + "│ Major: " + Colors.YELLOW + Colors.BOLD + f"{self.asterisk_major or 'Unknown'}".ljust(30) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
        print(Colors.CYAN + "║ " + Colors.WHITE + "Database:  " + Colors.GREEN + Colors.BOLD + f"{self.db_version or 'Unknown'}".ljust(65) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
        print(Colors.CYAN + "║ " + Colors.WHITE + "Tables:    " + Colors.CYAN + Colors.BOLD + f"{len(self.all_tables)} discovered".ljust(65) + Colors.RESET + Colors.CYAN + " ║" + Colors.RESET)
        print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.RESET)
        
        # Phase 2: Schema Discovery
        self._discover_schema_mappings()
        
        # Phase 3: Data Collection
        self._collect_all_data()
        
    def _detect_asterisk_version(self):
        """Detect Asterisk version with Python 3.6 compatibility."""
        try:
            # Python 3.6 compatible subprocess call
            result = subprocess.run(
                ["asterisk", "-V"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True, 
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout:
                match = re.search(r'Asterisk (\d+\.\d+\.\d+)', result.stdout)
                if match:
                    self.asterisk_version = match.group(1)
                    self.asterisk_major = int(self.asterisk_version.split('.')[0])
                    print(f"   ✓ Asterisk: {self.asterisk_version}")
                    return
                    
            # Try alternative paths
            for path in ["/usr/sbin/asterisk", "/opt/asterisk/sbin/asterisk"]:
                if os.path.exists(path):
                    result = subprocess.run(
                        [path, "-V"], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        universal_newlines=True, 
                        timeout=10
                    )
                    if result.returncode == 0 and "Asterisk" in result.stdout:
                        match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
                        if match:
                            self.asterisk_version = match.group(1)
                            self.asterisk_major = int(self.asterisk_version.split('.')[0])
                            print(f"   ✓ Asterisk: {self.asterisk_version} (from {path})")
                            return
                            
        except Exception as e:
            print(f"   ⚠ Asterisk detection error: {e}")
            
        print("   ❌ Could not detect Asterisk version")
        
    def _detect_freepbx_version(self):
        """Comprehensive FreePBX version detection."""
        
        # Method 1: /etc/schmooze/pbx-version
        try:
            if os.path.exists("/etc/schmooze/pbx-version"):
                with open("/etc/schmooze/pbx-version", "r") as f:
                    content = f.read().strip()
                    match = re.search(r'(\d+\.\d+\.\d+)', content)
                    if match:
                        self.freepbx_version = match.group(1)
                        self.freepbx_major = int(self.freepbx_version.split('.')[0])
                        print(f"   ✓ FreePBX: {self.freepbx_version} (from file)")
                        return
        except:
            pass
            
        # Method 2: Database admin table
        try:
            result = self._query("SELECT value FROM admin WHERE variable = 'version' LIMIT 1")
            if result:
                version = result.strip()
                if re.match(r'\d+\.\d+', version):
                    self.freepbx_version = version
                    self.freepbx_major = int(version.split('.')[0])
                    print(f"   ✓ FreePBX: {self.freepbx_version} (from admin table)")
                    return
        except:
            pass
            
        # Method 3: Module framework version
        try:
            result = self._query("SELECT version FROM modules WHERE modulename = 'framework' LIMIT 1")
            if result:
                version = result.strip()
                if re.match(r'\d+\.\d+', version):
                    self.freepbx_version = version
                    self.freepbx_major = int(version.split('.')[0])
                    print(f"   ✓ FreePBX: {self.freepbx_version} (from modules)")
                    return
        except:
            pass
            
        print("   ❌ Could not detect FreePBX version")
        
    def _detect_database_version(self):
        """Detect database version."""
        try:
            result = self._query("SELECT VERSION()")
            if result:
                self.db_version = result.strip()
                if "MariaDB" in self.db_version:
                    print(f"   ✓ Database: {self.db_version}")
                else:
                    print(f"   ✓ Database: MySQL {self.db_version}")
                return
        except:
            pass
            
        print("   ❌ Could not detect database version")
        
    def _discover_all_tables(self):
        """Discover all available tables."""
        try:
            result = self._query("SHOW TABLES")
            if result:
                self.all_tables = [t.strip() for t in result.split('\n') if t.strip()]
                print(f"   ✓ Database schema: {len(self.all_tables)} tables discovered")
        except Exception as e:
            print(f"   ❌ Table discovery failed: {e}")
            
    def _discover_schema_mappings(self):
        """Discover and map schema for all call flow components."""
        print(Colors.CYAN + "\n╔" + "═" * 78 + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW + " 🗂️  ADAPTIVE SCHEMA MAPPING ".center(78) + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.RESET)
        
        mappings = [
            ("inbound_routes", self._map_inbound_routes),
            ("time_conditions", self._map_time_conditions),
            ("extensions", self._map_extensions),
            ("ring_groups", self._map_ring_groups),
            ("ivr_menus", self._map_ivr_menus),
            ("ivr_options", self._map_ivr_options),
            ("queues", self._map_queues),
            ("announcements", self._map_announcements),
            ("trunks", self._map_trunks),
            ("setcid", self._map_setcid),
            ("misc_destinations", self._map_misc_destinations),
        ]
        
        successful_mappings = 0
        for component, mapper_func in mappings:
            try:
                mapping = mapper_func()
                if mapping:
                    self.schema_map[component] = mapping
                    successful_mappings += 1
                    comp_name = component.replace('_', ' ').title()
                    table_name = mapping['table']
                    field_count = len(mapping['fields'])
                    
                    line = f"  {Colors.GREEN}✓{Colors.RESET} {Colors.WHITE}{comp_name}:{Colors.RESET} {Colors.CYAN}{table_name}{Colors.RESET} {Colors.YELLOW}→ {field_count} fields{Colors.RESET}"
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    padding = " " * max(0, 78 - len(visible_text))
                    print(Colors.CYAN + "║ " + line + padding + " ║" + Colors.RESET)
                else:
                    comp_name = component.replace('_', ' ').title()
                    line = f"  {Colors.RED}❌{Colors.RESET} {Colors.WHITE}{comp_name}:{Colors.RESET} No compatible table found"
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    padding = " " * max(0, 78 - len(visible_text))
                    print(Colors.CYAN + "║ " + line + padding + " ║" + Colors.RESET)
            except Exception as e:
                comp_name = component.replace('_', ' ').title()
                line = f"  {Colors.RED}❌{Colors.RESET} {Colors.WHITE}{comp_name}:{Colors.RESET} Mapping error"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + line + padding + " ║" + Colors.RESET)
                
        print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.RESET)
        summary_line = f" 📊 SCHEMA MAPPING: {Colors.GREEN}{Colors.BOLD}{successful_mappings}{Colors.RESET}/{Colors.CYAN}{len(mappings)}{Colors.RESET} components mapped "
        visible_text = re.sub(r'\x1b\[[0-9;]*m', '', summary_line)
        padding = " " * max(0, 78 - len(visible_text))
        print(Colors.CYAN + "║" + summary_line + padding + "║" + Colors.RESET)
        print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.RESET)
        
    def _map_inbound_routes(self):
        """Map inbound routes table with all variations."""
        candidates = ['incoming', 'inbound_routes', 'did_routes']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # DID field variations
                    for field in ['extension', 'did', 'cidnum']:
                        if field in columns:
                            fields['did'] = field
                            break
                            
                    # Description field variations
                    for field in ['description', 'descr', 'name']:
                        if field in columns:
                            fields['description'] = field
                            break
                            
                    # Destination field variations
                    for field in ['destination', 'dest', 'goto']:
                        if field in columns:
                            fields['destination'] = field
                            break
                            
                    if 'did' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_time_conditions(self):
        """Map time conditions - handles FreePBX 12.7.8 vs newer differences."""
        candidates = ['timeconditions', 'time_conditions']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # ID field
                    for field in ['timeconditions_id', 'id']:
                        if field in columns:
                            fields['id'] = field
                            break
                            
                    # Name field
                    for field in ['displayname', 'description', 'name']:
                        if field in columns:
                            fields['name'] = field
                            break
                            
                    # True destination
                    for field in ['truegoto', 'true_dest']:
                        if field in columns:
                            fields['true_dest'] = field
                            break
                            
                    # False destination
                    for field in ['falsegoto', 'false_dest']:
                        if field in columns:
                            fields['false_dest'] = field
                            break
                            
                    # Mode field - CRITICAL: handle toggle_mode vs mode
                    for field in ['mode', 'toggle_mode']:
                        if field in columns:
                            fields['mode'] = field
                            break
                            
                    if 'id' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_extensions(self):
        """Map extensions/users table variations."""
        candidates = ['users', 'extensions', 'sip_conf']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # Extension number
                    for field in ['extension', 'ext', 'number']:
                        if field in columns:
                            fields['extension'] = field
                            break
                            
                    # Name
                    for field in ['name', 'displayname', 'description']:
                        if field in columns:
                            fields['name'] = field
                            break
                            
                    if 'extension' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_ring_groups(self):
        """Map ring groups - handles mohclass vs rvolume differences."""
        candidates = ['ringgroups', 'ring_groups']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # Group number
                    for field in ['grpnum', 'group_num', 'extension']:
                        if field in columns:
                            fields['group_num'] = field
                            break
                            
                    # Description
                    for field in ['description', 'descr', 'name']:
                        if field in columns:
                            fields['description'] = field
                            break
                            
                    # Member list
                    for field in ['grplist', 'member_list']:
                        if field in columns:
                            fields['member_list'] = field
                            break
                            
                    # CRITICAL: Music on hold - handle mohclass vs rvolume
                    for field in ['mohclass', 'rvolume']:
                        if field in columns:
                            fields['moh'] = field
                            break
                    
                    # Failover destination - handle different field names
                    for field in ['postdest', 'dest', 'destination', 'failover_dest']:
                        if field in columns:
                            fields['failover_dest'] = field
                            break
                            
                    if 'group_num' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_ivr_menus(self):
        """Map IVR menus table variations."""
        candidates = ['ivr_details', 'ivr', 'ivr_menus']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # ID field
                    for field in ['id', 'ivr_id']:
                        if field in columns:
                            fields['id'] = field
                            break
                            
                    # Name
                    for field in ['name', 'displayname', 'description']:
                        if field in columns:
                            fields['name'] = field
                            break
                    
                    # Timeout destination
                    for field in ['timeout_destination', 'timeout_dest']:
                        if field in columns:
                            fields['timeout_dest'] = field
                            break
                    
                    # Invalid destination  
                    for field in ['invalid_destination', 'invalid_dest']:
                        if field in columns:
                            fields['invalid_dest'] = field
                            break
                            
                    if 'id' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_ivr_options(self):
        """Map IVR options/entries table variations."""
        candidates = ['ivr_entries', 'ivr_options']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # IVR ID
                    for field in ['ivr_id', 'menu_id']:
                        if field in columns:
                            fields['ivr_id'] = field
                            break
                            
                    # Selection
                    for field in ['selection', 'digit']:
                        if field in columns:
                            fields['selection'] = field
                            break
                            
                    # Destination
                    for field in ['dest', 'destination']:
                        if field in columns:
                            fields['dest'] = field
                            break
                            
                    if 'ivr_id' in fields and 'selection' in fields and 'dest' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_queues(self):
        """Map queues table - handles keyword vs descr variations."""
        candidates = ['queues_config', 'queues']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # Queue extension
                    for field in ['extension', 'queueno']:
                        if field in columns:
                            fields['extension'] = field
                            break
                            
                    # CRITICAL: Description - handle keyword vs descr
                    for field in ['descr', 'description', 'keyword']:
                        if field in columns:
                            fields['description'] = field
                            break
                            
                    if 'extension' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_announcements(self):
        """Map announcements table - handles filename variations."""
        candidates = ['announcement', 'announcements']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # ID
                    for field in ['announcement_id', 'id']:
                        if field in columns:
                            fields['id'] = field
                            break
                            
                    # Description
                    for field in ['description', 'name']:
                        if field in columns:
                            fields['description'] = field
                            break
                            
                    # CRITICAL: Filename - handle filename variations
                    for field in ['filename', 'file']:
                        if field in columns:
                            fields['filename'] = field
                            break
                            
                    if 'id' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _map_trunks(self):
        """Map trunks table variations."""
        candidates = ['trunks', 'trunk_configs']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # Trunk name
                    for field in ['trunkid', 'name']:
                        if field in columns:
                            fields['name'] = field
                            break
                            
                    # Description
                    for field in ['description', 'descr']:
                        if field in columns:
                            fields['description'] = field
                            break
                            
                    if 'name' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
    
    def _map_setcid(self):
        """Map Set Caller ID table."""
        candidates = ['setcid', 'set_callerid']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # ID field
                    for field in ['cid_id', 'id']:
                        if field in columns:
                            fields['id'] = field
                            break
                    
                    # Description
                    for field in ['description', 'descr', 'name']:
                        if field in columns:
                            fields['description'] = field
                            break
                    
                    # Caller ID Name
                    for field in ['cid_name', 'name']:
                        if field in columns:
                            fields['cid_name'] = field
                            break
                    
                    # Caller ID Number
                    for field in ['cid_num', 'number']:
                        if field in columns:
                            fields['cid_num'] = field
                            break
                    
                    # Destination
                    for field in ['dest', 'destination']:
                        if field in columns:
                            fields['dest'] = field
                            break
                    
                    if 'id' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
    
    def _map_misc_destinations(self):
        """Map Misc Destinations table."""
        candidates = ['miscdests', 'misc_destinations']
        
        for table in candidates:
            if table in self.all_tables:
                columns = self._describe_table(table)
                if columns:
                    fields = {}
                    
                    # ID field
                    for field in ['id', 'dest_id']:
                        if field in columns:
                            fields['id'] = field
                            break
                    
                    # Description
                    for field in ['description', 'descr', 'name']:
                        if field in columns:
                            fields['description'] = field
                            break
                    
                    # Destination
                    for field in ['destdial', 'dest', 'destination']:
                        if field in columns:
                            fields['dest'] = field
                            break
                    
                    if 'id' in fields:
                        return {'table': table, 'columns': columns, 'fields': fields}
        return None
        
    def _collect_all_data(self):
        """Collect data using discovered schema mappings."""
        print(Colors.CYAN + "\n╔" + "═" * 78 + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW + " 📊 VERSION-AWARE DATA COLLECTION ".center(78) + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.RESET)
        
        total_items = 0
        for component, schema in self.schema_map.items():
            try:
                data = self._collect_component_data(component, schema)
                self.data[component] = data
                count = len(data) if data else 0
                total_items += count
                
                status = f"{Colors.GREEN}✓{Colors.RESET}" if count > 0 else f"{Colors.YELLOW}○{Colors.RESET}"
                comp_name = component.replace('_', ' ').title()
                count_str = f"{Colors.CYAN}{Colors.BOLD}{count}{Colors.RESET} items"
                
                line = f"  {status} {Colors.WHITE}{comp_name}:{Colors.RESET} {count_str}"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + line + padding + " ║" + Colors.RESET)
                
                # Show sample data with indentation
                if count > 0 and count <= 2:
                    for item in data:
                        sample_line = self._format_sample_item(component, item)
                        if sample_line:
                            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', sample_line)
                            padding = " " * max(0, 78 - len(visible_text))
                            print(Colors.CYAN + "║ " + sample_line + padding + " ║" + Colors.RESET)
                elif count > 2:
                    for item in data[:2]:
                        sample_line = self._format_sample_item(component, item)
                        if sample_line:
                            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', sample_line)
                            padding = " " * max(0, 78 - len(visible_text))
                            print(Colors.CYAN + "║ " + sample_line + padding + " ║" + Colors.RESET)
                    more_line = f"      {Colors.YELLOW}... and {count - 2} more{Colors.RESET}"
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', more_line)
                    padding = " " * max(0, 78 - len(visible_text))
                    print(Colors.CYAN + "║ " + more_line + padding + " ║" + Colors.RESET)
                    
            except Exception as e:
                comp_name = component.replace('_', ' ').title()
                line = f"  {Colors.RED}❌{Colors.RESET} {Colors.WHITE}{comp_name}:{Colors.RESET} Collection error"
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', line)
                padding = " " * max(0, 78 - len(visible_text))
                print(Colors.CYAN + "║ " + line + padding + " ║" + Colors.RESET)
        
        # Collect toggle controls
        try:
            self.data['toggle_controls'] = []
            count = 0
            total_items += count
            
            status = f"{Colors.YELLOW}○{Colors.RESET}"
            line = f"  {status} {Colors.WHITE}Toggle Controls:{Colors.RESET} {Colors.CYAN}{Colors.BOLD}{count}{Colors.RESET} items"
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', line)
            padding = " " * max(0, 78 - len(visible_text))
            print(Colors.CYAN + "║ " + line + padding + " ║" + Colors.RESET)
                    
        except Exception as e:
            line = f"  {Colors.RED}❌{Colors.RESET} {Colors.WHITE}Toggle Controls:{Colors.RESET} Collection error"
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', line)
            padding = " " * max(0, 78 - len(visible_text))
            print(Colors.CYAN + "║ " + line + padding + " ║" + Colors.RESET)
                
        print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.RESET)
        summary_line = f" 🎯 TOTAL CONFIGURATION ITEMS: {Colors.GREEN}{Colors.BOLD}{total_items}{Colors.RESET} "
        visible_text = re.sub(r'\x1b\[[0-9;]*m', '', summary_line)
        padding = " " * max(0, 78 - len(visible_text))
        print(Colors.CYAN + "║" + summary_line + padding + "║" + Colors.RESET)
        print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.RESET)
    
    def _format_sample_item(self, component, item):
        """Format a sample item for display."""
        if component == 'inbound_routes':
            did = item.get('did', 'N/A')
            desc = item.get('description', 'No description')[:40]
            return f"      {Colors.CYAN}•{Colors.RESET} DID {Colors.GREEN}{did}{Colors.RESET}: {desc}"
        elif component == 'time_conditions':
            name = item.get('name', 'Unnamed')[:50]
            return f"      {Colors.CYAN}•{Colors.RESET} TC: {Colors.WHITE}{name}{Colors.RESET}"
        elif component == 'extensions':
            ext = item.get('extension', 'N/A')
            name = item.get('name', 'Unnamed')[:40]
            return f"      {Colors.CYAN}•{Colors.RESET} Ext {Colors.YELLOW}{ext}{Colors.RESET}: {name}"
        elif component == 'ring_groups':
            grp = item.get('grpnum', 'N/A')
            desc = item.get('description', 'No description')[:40]
            return f"      {Colors.CYAN}•{Colors.RESET} RG {Colors.MAGENTA}{grp}{Colors.RESET}: {desc}"
        elif component == 'ivr_menus':
            ivr_id = item.get('id', 'N/A')
            name = item.get('name', 'Unnamed')[:40]
            return f"      {Colors.CYAN}•{Colors.RESET} IVR {Colors.BLUE}{ivr_id}{Colors.RESET}: {name}"
        else:
            # Generic format for other components
            first_val = next(iter(item.values())) if item else 'N/A'
            if isinstance(first_val, str):
                return f"      {Colors.CYAN}•{Colors.RESET} {first_val[:60]}"
        return None
        
    def _collect_component_data(self, component, schema):
        """Collect data for a specific component."""
        table = schema['table']
        fields = schema['fields']
        
        # Build SELECT clause
        select_fields = []
        for logical_name, column_name in fields.items():
            select_fields.append(f"{column_name} AS {logical_name}")
            
        query = f"SELECT {', '.join(select_fields)} FROM {table}"
        
        # Add ORDER BY
        if 'id' in fields:
            query += f" ORDER BY {fields['id']}"
        elif 'extension' in fields:
            query += f" ORDER BY CAST({fields['extension']} AS UNSIGNED)"
            
        try:
            result = self._query(query)
            if result:
                data = []
                for line in result.split('\n'):
                    if line.strip():
                        values = line.split('\t')
                        row = {}
                        for i, logical_name in enumerate(fields.keys()):
                            row[logical_name] = values[i] if i < len(values) else ''
                        data.append(row)
                return data
        except Exception as e:
            print(f"      Query error: {e}")
            
        return []
        
    def _print_sample_item(self, component, item):
        """Print sample data for an item."""
        if component == 'inbound_routes':
            print(f"      • DID {item.get('did', 'N/A')}: {item.get('description', 'Unnamed')} → {item.get('destination', 'Unknown')}")
        elif component == 'time_conditions':
            print(f"      • TC{item.get('id', 'N/A')}: {item.get('name', 'Unnamed')}")
        elif component == 'extensions':
            print(f"      • Ext {item.get('extension', 'N/A')}: {item.get('name', 'Unnamed')}")
        elif component == 'ring_groups':
            print(f"      • RG{item.get('group_num', 'N/A')}: {item.get('description', 'Unnamed')}")
        else:
            key = item.get('id') or item.get('extension') or item.get('name') or 'N/A'
            desc = item.get('description') or item.get('name') or 'No description'
            print(f"      • {key}: {desc}")
            
    def _describe_table(self, table):
        """Get table column information."""
        try:
            result = self._query(f"DESCRIBE {table}")
            if result:
                columns = {}
                for line in result.split('\n'):
                    if line.strip():
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            columns[parts[0]] = parts[1]
                return columns
        except:
            pass
        return {}
        
    def _query(self, sql):
        """Execute MySQL query with Python 3.6 compatibility."""
        cmd = ["mysql", "-NBe", sql, "asterisk", "-u", self.user]
        if self.socket:
            cmd.extend(["-S", self.socket])
            
        try:
            # Python 3.6 compatible subprocess call
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True, 
                timeout=30
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            return None

    def generate_ascii_callflow(self, did=None):
        """Generate ASCII call flow diagrams for DIDs."""
        print(Colors.CYAN + "\n╔" + "═" * 78 + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.YELLOW + " 📞 ASCII CALL FLOW GENERATION ".center(78) + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.RESET)
        
        if not self.data.get('inbound_routes'):
            print(Colors.RED + "\n   ⚠ No inbound routes found - cannot generate call flows" + Colors.RESET)
            return
        
        if did:
            self._generate_single_did_flow(did)
        else:
            self._generate_all_flows()
    
    def _generate_all_flows(self):
        """Generate ASCII call flows for all inbound routes."""
        print(Colors.CYAN + "\n╔" + "═" * 78 + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.GREEN + " 🎯 GENERATING ASCII CALL FLOWS FOR ALL DIDS ".center(78) + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.RESET)
        
        inbound_routes = self.data.get('inbound_routes', [])
        if not inbound_routes:
            print(Colors.RED + "❌ No inbound routes found" + Colors.RESET)
            return
        
        print(Colors.GREEN + f"\n✓ Found {len(inbound_routes)} inbound routes\n" + Colors.RESET)
        
        for route in inbound_routes:
            did = route.get('did') or 'Unknown'
            description = route.get('description') or f"Route for {did}"
            destination = route.get('destination') or 'Unknown'
            
            print(Colors.CYAN + "╔" + "═" * 78 + "╗" + Colors.RESET)
            print(Colors.CYAN + "║ " + Colors.WHITE + Colors.BOLD + f"📞 DID: {Colors.GREEN}{did}{Colors.RESET} {Colors.WHITE}- {description[:50]}".ljust(87) + Colors.CYAN + " ║" + Colors.RESET)
            print(Colors.CYAN + "╠" + "═" * 78 + "╣" + Colors.RESET)
            
            # Show human-readable destination
            destination_display = self._resolve_destination_display(destination) if destination != 'Unknown' else destination
            dest_line = f"  {Colors.YELLOW}→{Colors.RESET} Destination: {Colors.CYAN}{destination_display[:58]}{Colors.RESET}"
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', dest_line)
            padding = " " * max(0, 78 - len(visible_text))
            print(Colors.CYAN + "║ " + dest_line + padding + " ║" + Colors.RESET)
            print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.RESET)
            
            # Generate flow visualization
            self._render_simple_flow(did, route)
            print()  # Add spacing between routes
    
    def _generate_single_did_flow(self, did):
        """Generate ASCII flow for a specific DID."""
        print(Colors.CYAN + "\n╔" + "═" * 78 + "╗" + Colors.RESET)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.GREEN + f" 🎯 GENERATING ASCII CALL FLOW FOR DID: {did} ".center(88) + Colors.CYAN + "║" + Colors.RESET)
        print(Colors.CYAN + "╚" + "═" * 78 + "╝" + Colors.RESET)
        
        # Find the DID in inbound routes
        route = None
        for r in self.data.get('inbound_routes', []):
            if r.get('did') == did:
                route = r
                break
        
        if not route:
            print(Colors.RED + f"\n❌ No inbound route found for DID: {did}" + Colors.RESET)
            return
    def _render_simple_flow(self, did, route):
        """Render a complete ASCII call flow tree."""
        print(Colors.CYAN + "\n╔" + "═" * 68 + "╗" + Colors.RESET)
        header = f" 📞 CALL FLOW: {Colors.GREEN}{Colors.BOLD}{did}{Colors.RESET} "
        visible_text = re.sub(r'\x1b\[[0-9;]*m', '', header)
        padding = " " * max(0, 68 - len(visible_text))
        print(Colors.CYAN + "║" + header + padding + "║" + Colors.RESET)
        print(Colors.CYAN + "╠" + "═" * 68 + "╣" + Colors.RESET)
        
        destination = route.get('destination', '')
        description = route.get('description', 'Unknown Route')
        
        incoming_line = f" {Colors.YELLOW}📱{Colors.RESET} Incoming Call: {Colors.GREEN}{Colors.BOLD}{did}{Colors.RESET} {Colors.WHITE}({description[:30]}){Colors.RESET} "
        visible_text = re.sub(r'\x1b\[[0-9;]*m', '', incoming_line)
        padding = " " * max(0, 68 - len(visible_text))
        print(Colors.CYAN + "║" + incoming_line + padding + "║" + Colors.RESET)
        
        pipe_line = f" {Colors.CYAN}│{Colors.RESET} "
        visible_text = re.sub(r'\x1b\[[0-9;]*m', '', pipe_line)
        padding = " " * max(0, 68 - len(visible_text))
        print(Colors.CYAN + "║" + pipe_line + padding + "║" + Colors.RESET)
        
        if destination:
            self._render_destination_tree(destination, " ", True)
        else:
            no_dest_line = f" {Colors.CYAN}└─{Colors.RESET} {Colors.RED}❓ No destination configured{Colors.RESET} "
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', no_dest_line)
            padding = " " * max(0, 68 - len(visible_text))
            print(Colors.CYAN + "║" + no_dest_line + padding + "║" + Colors.RESET)
        
        print(Colors.CYAN + "╚" + "═" * 68 + "╝" + Colors.RESET)

    def _render_destination_tree(self, destination, prefix="", is_last=True, visited=None, depth=0):
        """Recursively render the complete call tree for a destination with colors."""
        if visited is None:
            visited = set()
        
        # Prevent infinite loops
        if destination in visited or depth > 10:
            connector = "└─" if is_last else "├─"
            loop_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.RED}🔄 Loop detected or max depth reached{Colors.RESET}: {Colors.YELLOW}{destination[:30]}{Colors.RESET} "
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', loop_line)
            padding = " " * max(0, 68 - len(visible_text))
            print(Colors.CYAN + "║" + loop_line + padding + "║" + Colors.RESET)
            return
        
        visited.add(destination)
        
        # Parse destination
        if ',' in destination:
            dest_parts = destination.split(',')
            dest_type = dest_parts[0]
            dest_id = dest_parts[1] if len(dest_parts) > 1 else 'Unknown'
            
            # Handle special cases where the ID is embedded in the type
            if dest_type.startswith('ivr-'):
                dest_id = dest_type[4:]  # Extract ID from "ivr-77" -> "77"
                dest_type = 'ivr'
            # ext-group destinations are already correctly parsed, no special handling needed
        else:
            dest_type = destination
            dest_id = destination
        
        connector = "└─" if is_last else "├─"
        child_prefix = prefix + ("   " if is_last else "│  ")
        
        if dest_type == 'timeconditions':
            tc = self._find_time_condition(dest_id)
            if tc:
                tc_name = tc.get('name', dest_id)
                
                # Show time condition with enhanced display for toggle controls
                if 'toggle' in tc_name.lower():
                    tc_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.MAGENTA}⏰{Colors.RESET} Time Condition: {Colors.YELLOW}{tc_name}{Colors.RESET} {Colors.WHITE}(Toggle Control){Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', tc_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + tc_line + padding + "║" + Colors.RESET)
                    
                    toggle_line = f" {child_prefix}{Colors.CYAN}├─{Colors.RESET} {Colors.BLUE}🎛️{Colors.RESET}  Toggle: Use feature codes to override "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', toggle_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + toggle_line + padding + "║" + Colors.RESET)
                    
                    pipe_line = f" {child_prefix}{Colors.CYAN}│{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', pipe_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + pipe_line + padding + "║" + Colors.RESET)
                else:
                    tc_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.MAGENTA}⏰{Colors.RESET} Time Condition: {Colors.YELLOW}{tc_name}{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', tc_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + tc_line + padding + "║" + Colors.RESET)
                    
                    pipe_line = f" {child_prefix}{Colors.CYAN}│{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', pipe_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + pipe_line + padding + "║" + Colors.RESET)
                
                # Get appropriate labels for this time condition
                true_label, false_label = self._get_time_condition_labels(tc)
                
                true_dest = tc.get('true_dest', '')
                false_dest = tc.get('false_dest', '')
                
                # Render true branch
                branch_line = f" {child_prefix}{Colors.CYAN}├─{Colors.RESET} {Colors.GREEN}{true_label}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', branch_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + branch_line + padding + "║" + Colors.RESET)
                if true_dest:
                    self._render_destination_tree(true_dest, child_prefix + "│  ", False, visited.copy(), depth + 1)
                else:
                    no_dest_line = f" {child_prefix}{Colors.CYAN}│  └─{Colors.RESET} {Colors.RED}❓ No true destination{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', no_dest_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + no_dest_line + padding + "║" + Colors.RESET)
                
                pipe_line = f" {child_prefix}{Colors.CYAN}│{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', pipe_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + pipe_line + padding + "║" + Colors.RESET)
                
                # Render false branch
                branch_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.RED}{false_label}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', branch_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + branch_line + padding + "║" + Colors.RESET)
                if false_dest:
                    self._render_destination_tree(false_dest, child_prefix + "   ", True, visited.copy(), depth + 1)
                else:
                    no_dest_line = f" {child_prefix}   {Colors.CYAN}└─{Colors.RESET} {Colors.RED}❓ No false destination{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', no_dest_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + no_dest_line + padding + "║" + Colors.RESET)
            else:
                tc_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.MAGENTA}⏰{Colors.RESET} Time Condition: {Colors.YELLOW}{dest_id}{Colors.RESET} {Colors.RED}(details not found){Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', tc_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + tc_line + padding + "║" + Colors.RESET)
        
        elif dest_type == 'ext-group':
            rg = self._find_ring_group(dest_id)
            if rg:
                rg_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}🔔{Colors.RESET} Ring Group: {Colors.GREEN}{rg.get('description', dest_id)}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', rg_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + rg_line + padding + "║" + Colors.RESET)
                
                # Show ring group members
                if rg.get('member_list'):
                    members = [m for m in rg['member_list'].split('-') if m]
                    members_line = f" {child_prefix}{Colors.CYAN}├─{Colors.RESET} {Colors.YELLOW}👥{Colors.RESET} Members: "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', members_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + members_line + padding + "║" + Colors.RESET)
                    for i, member in enumerate(members):  # Show ALL members
                        mem_connector = "├─" if i < len(members) - 1 else "└─"
                        ext = self._find_extension(member)
                        ext_name = ext.get('name', 'Unknown') if ext else 'Unknown'
                        member_line = f" {child_prefix}{Colors.CYAN}│  {mem_connector}{Colors.RESET} {Colors.GREEN}📞{Colors.RESET} {Colors.BOLD}{member}{Colors.RESET} {Colors.WHITE}({ext_name}){Colors.RESET} "
                        visible_text = re.sub(r'\x1b\[[0-9;]*m', '', member_line)
                        padding = " " * max(0, 68 - len(visible_text))
                        print(Colors.CYAN + "║" + member_line + padding + "║" + Colors.RESET)
                
                # Show failover destination if exists - use correct field mapping
                failover_dest = rg.get('failover_dest', '') or rg.get('postdest', '') or rg.get('dest', '')
                if failover_dest and failover_dest != 'app-blackhole,hangup,1':
                    pipe_line = f" {child_prefix}{Colors.CYAN}│{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', pipe_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + pipe_line + padding + "║" + Colors.RESET)
                    
                    failover_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.YELLOW}🔀{Colors.RESET} No Answer Failover: "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', failover_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + failover_line + padding + "║" + Colors.RESET)
                    self._render_destination_tree(failover_dest, child_prefix + "   ", True, visited.copy(), depth + 1)
                else:
                    end_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.RED}🔚{Colors.RESET} No failover (call ends) "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', end_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + end_line + padding + "║" + Colors.RESET)
            else:
                rg_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}🔔{Colors.RESET} Ring Group: {Colors.YELLOW}{dest_id}{Colors.RESET} {Colors.RED}(details not found){Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', rg_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + rg_line + padding + "║" + Colors.RESET)
        
        elif dest_type == 'ivr':
            ivr = self._find_ivr_menu(dest_id)
            if ivr:
                ivr_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.MAGENTA}🎵{Colors.RESET} IVR Menu: {Colors.YELLOW}{ivr.get('name', dest_id)}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ivr_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + ivr_line + padding + "║" + Colors.RESET)
                
                # Show IVR options
                options = self._find_ivr_options(dest_id)
                if options:
                    opts_line = f" {child_prefix}{Colors.CYAN}├─{Colors.RESET} {Colors.BLUE}🔢{Colors.RESET} Options: "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', opts_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + opts_line + padding + "║" + Colors.RESET)
                    
                    for i, opt in enumerate(options):  # Show ALL options
                        is_last_option = (i == len(options) - 1)
                        opt_connector = "└─" if is_last_option else "├─"
                        selection = opt.get('selection', '?')
                        opt_dest = opt.get('dest', 'Unknown')
                        
                        if opt_dest and opt_dest != 'Unknown':
                            # Check if we can recursively follow this destination
                            if depth < 10 and opt_dest not in visited:
                                # Get a short description first
                                dest_summary = self._resolve_destination_display(opt_dest)
                                opt_line = f" {child_prefix}{Colors.CYAN}│  {opt_connector}{Colors.RESET} {Colors.GREEN}[{selection}]{Colors.RESET} {Colors.YELLOW}→{Colors.RESET} {Colors.WHITE}{dest_summary[:40]}{Colors.RESET} "
                                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', opt_line)
                                padding = " " * max(0, 68 - len(visible_text))
                                print(Colors.CYAN + "║" + opt_line + padding + "║" + Colors.RESET)
                                
                                # Then recursively follow the destination tree
                                new_visited = visited.copy()
                                new_visited.add(opt_dest)
                                option_prefix = f"{child_prefix}│  {'   ' if is_last_option else '│  '}"
                                self._render_destination_tree(opt_dest, option_prefix, True, new_visited, depth + 1)
                            else:
                                # Just show summary if we hit depth limit or loop
                                dest_summary = self._resolve_destination_display(opt_dest)
                                opt_line = f" {child_prefix}{Colors.CYAN}│  {opt_connector}{Colors.RESET} {Colors.GREEN}[{selection}]{Colors.RESET} {Colors.YELLOW}→{Colors.RESET} {Colors.WHITE}{dest_summary[:40]}{Colors.RESET} "
                                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', opt_line)
                                padding = " " * max(0, 68 - len(visible_text))
                                print(Colors.CYAN + "║" + opt_line + padding + "║" + Colors.RESET)
                                if opt_dest in visited:
                                    loop_line = f" {child_prefix}│  {'   ' if is_last_option else '│  '}{Colors.CYAN}└─{Colors.RESET} {Colors.RED}🔄 (Already visited - loop prevention){Colors.RESET} "
                                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', loop_line)
                                    padding = " " * max(0, 68 - len(visible_text))
                                    print(Colors.CYAN + "║" + loop_line + padding + "║" + Colors.RESET)
                        else:
                            opt_line = f" {child_prefix}{Colors.CYAN}│  {opt_connector}{Colors.RESET} {Colors.GREEN}[{selection}]{Colors.RESET} {Colors.YELLOW}→{Colors.RESET} {Colors.RED}Unknown destination{Colors.RESET} "
                            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', opt_line)
                            padding = " " * max(0, 68 - len(visible_text))
                            print(Colors.CYAN + "║" + opt_line + padding + "║" + Colors.RESET)
                
                # Show timeout and invalid handling
                timeout_dest = ivr.get('timeout_dest')
                invalid_dest = ivr.get('invalid_dest')
                
                if timeout_dest or invalid_dest:
                    if timeout_dest and invalid_dest and timeout_dest == invalid_dest:
                        # Same destination for both
                        dest_summary = self._resolve_destination_display(timeout_dest)
                        timeout_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.YELLOW}⏱️{Colors.RESET} Timeout/Invalid {Colors.YELLOW}→{Colors.RESET} {Colors.WHITE}{dest_summary[:40]}{Colors.RESET} "
                        visible_text = re.sub(r'\x1b\[[0-9;]*m', '', timeout_line)
                        padding = " " * max(0, 68 - len(visible_text))
                        print(Colors.CYAN + "║" + timeout_line + padding + "║" + Colors.RESET)
                    else:
                        # Different destinations or only one configured
                        if timeout_dest:
                            dest_summary = self._resolve_destination_display(timeout_dest)
                            timeout_line = f" {child_prefix}{Colors.CYAN}├─{Colors.RESET} {Colors.YELLOW}⏱️{Colors.RESET} Timeout {Colors.YELLOW}→{Colors.RESET} {Colors.WHITE}{dest_summary[:40]}{Colors.RESET} "
                            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', timeout_line)
                            padding = " " * max(0, 68 - len(visible_text))
                            print(Colors.CYAN + "║" + timeout_line + padding + "║" + Colors.RESET)
                        
                        if invalid_dest:
                            dest_summary = self._resolve_destination_display(invalid_dest)
                            invalid_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.RED}❌{Colors.RESET} Invalid Input {Colors.YELLOW}→{Colors.RESET} {Colors.WHITE}{dest_summary[:40]}{Colors.RESET} "
                            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', invalid_line)
                            padding = " " * max(0, 68 - len(visible_text))
                            print(Colors.CYAN + "║" + invalid_line + padding + "║" + Colors.RESET)
                else:
                    no_handling_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.RED}🔚{Colors.RESET} {Colors.WHITE}(No timeout/invalid handling configured){Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', no_handling_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + no_handling_line + padding + "║" + Colors.RESET)
            else:
                ivr_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.MAGENTA}🎵{Colors.RESET} IVR Menu: {Colors.YELLOW}{dest_id}{Colors.RESET} {Colors.RED}(details not found){Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ivr_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + ivr_line + padding + "║" + Colors.RESET)
        
        elif dest_type == 'from-did-direct':
            ext = self._find_extension(dest_id)
            if ext:
                ext_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.GREEN}📞{Colors.RESET} Extension {Colors.BOLD}{dest_id}{Colors.RESET}: {Colors.WHITE}{ext.get('name', 'Unknown')}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ext_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + ext_line + padding + "║" + Colors.RESET)
                
                vm_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.BLUE}📧{Colors.RESET} Voicemail: {Colors.WHITE}{ext.get('name', 'Unknown')}{Colors.RESET} {Colors.YELLOW}(ext {dest_id}){Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', vm_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + vm_line + padding + "║" + Colors.RESET)
            else:
                ext_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.GREEN}📞{Colors.RESET} Extension {Colors.BOLD}{dest_id}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ext_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + ext_line + padding + "║" + Colors.RESET)
                
                vm_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.BLUE}📧{Colors.RESET} Voicemail {Colors.YELLOW}(ext {dest_id}){Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', vm_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + vm_line + padding + "║" + Colors.RESET)
        
        elif dest_type == 'ext-local':
            # Handle voicemail, announcements, etc.
            if 'vmu' in dest_id:
                ext_num = dest_id.replace('vmu', '')
                ext = self._find_extension(ext_num)
                if ext:
                    vm_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}📧{Colors.RESET} Extension {Colors.BOLD}{ext_num}{Colors.RESET}: {Colors.WHITE}{ext.get('name', 'Unknown')}{Colors.RESET} {Colors.YELLOW}Voicemail (vmu{ext_num}){Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', vm_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + vm_line + padding + "║" + Colors.RESET)
                else:
                    vm_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}📧{Colors.RESET} Extension {Colors.BOLD}{ext_num}{Colors.RESET}: {Colors.YELLOW}Voicemail (vmu{ext_num}){Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', vm_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + vm_line + padding + "║" + Colors.RESET)
            elif 'vmb' in dest_id:
                ext_num = dest_id.replace('vmb', '')
                ext = self._find_extension(ext_num)
                if ext:
                    vm_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}📧{Colors.RESET} Extension {Colors.BOLD}{ext_num}{Colors.RESET}: {Colors.WHITE}{ext.get('name', 'Unknown')}{Colors.RESET} {Colors.YELLOW}Voicemail (vmb{ext_num}){Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', vm_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + vm_line + padding + "║" + Colors.RESET)
                else:
                    vm_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}📧{Colors.RESET} Extension {Colors.BOLD}{ext_num}{Colors.RESET}: {Colors.YELLOW}Voicemail (vmb{ext_num}){Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', vm_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + vm_line + padding + "║" + Colors.RESET)
            else:
                ext = self._find_extension(dest_id)
                if ext:
                    ext_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.GREEN}📱{Colors.RESET} Extension {Colors.BOLD}{dest_id}{Colors.RESET}: {Colors.WHITE}{ext.get('name', 'Unknown')}{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ext_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + ext_line + padding + "║" + Colors.RESET)
                else:
                    ext_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.GREEN}📱{Colors.RESET} Extension {Colors.BOLD}{dest_id}{Colors.RESET} "
                    visible_text = re.sub(r'\x1b\[[0-9;]*m', '', ext_line)
                    padding = " " * max(0, 68 - len(visible_text))
                    print(Colors.CYAN + "║" + ext_line + padding + "║" + Colors.RESET)
        
        elif dest_type == 'app-blackhole':
            hangup_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.RED}🔚{Colors.RESET} {Colors.WHITE}Hangup{Colors.RESET} "
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', hangup_line)
            padding = " " * max(0, 68 - len(visible_text))
            print(Colors.CYAN + "║" + hangup_line + padding + "║" + Colors.RESET)
        
        elif dest_type == 'app-announcement':
            announce_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}📢{Colors.RESET} Announcement: {Colors.YELLOW}{dest_id}{Colors.RESET} "
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', announce_line)
            padding = " " * max(0, 68 - len(visible_text))
            print(Colors.CYAN + "║" + announce_line + padding + "║" + Colors.RESET)
        
        elif dest_type == 'app-setcid':
            setcid = self._find_setcid(dest_id)
            if setcid:
                desc = setcid.get('description', f'Set Caller ID {dest_id}')
                cid_name = setcid.get('cid_name', 'Unknown')
                cid_num = setcid.get('cid_num', 'Unknown')
                next_dest = setcid.get('dest', '')
                
                print(f"{prefix}{connector} 🆔 Set Caller ID: {desc}")
                
                # Describe what the transformation will do
                transformation = self._describe_callerid_transformation(cid_name, cid_num)
                print(f"{child_prefix}├─ 🔄 {transformation}")
                
                # Show the raw templates for technical reference
                if cid_name and cid_name != 'Unknown':
                    print(f"{child_prefix}├─ � Name Template: {cid_name}")
                if cid_num and cid_num != 'Unknown':
                    print(f"{child_prefix}├─ 📞 Number Template: {cid_num}")
                
                if next_dest:
                    print(f"{child_prefix}│")
                    print(f"{child_prefix}└─ ➡️  Next Destination:")
                    self._render_destination_tree(next_dest, child_prefix + "   ", True, visited.copy(), depth + 1)
                else:
                    print(f"{child_prefix}└─ 🔚 No next destination configured")
            else:
                print(f"{prefix}{connector} 🆔 Set Caller ID: {dest_id} (details not found)")
        
        elif dest_type == 'ext-miscdests':
            misc = self._find_misc_destination(dest_id)
            if misc:
                desc = misc.get('description', f'Misc Destination {dest_id}')
                final_dest = misc.get('dest', 'Unknown')
                misc_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}🎯{Colors.RESET} {Colors.WHITE}{desc}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', misc_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + misc_line + padding + "║" + Colors.RESET)
                
                final_line = f" {child_prefix}{Colors.CYAN}└─{Colors.RESET} {Colors.GREEN}☎️{Colors.RESET}  Final Destination: {Colors.YELLOW}{final_dest}{Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', final_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + final_line + padding + "║" + Colors.RESET)
            else:
                misc_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.BLUE}🎯{Colors.RESET} Misc Destination: {Colors.YELLOW}{dest_id}{Colors.RESET} {Colors.RED}(details not found){Colors.RESET} "
                visible_text = re.sub(r'\x1b\[[0-9;]*m', '', misc_line)
                padding = " " * max(0, 68 - len(visible_text))
                print(Colors.CYAN + "║" + misc_line + padding + "║" + Colors.RESET)
        
        else:
            # Generic destination
            display = self._resolve_destination_display(destination)
            generic_line = f" {prefix}{Colors.CYAN}{connector}{Colors.RESET} {Colors.YELLOW}🎯{Colors.RESET} {Colors.WHITE}{display[:50]}{Colors.RESET} "
            visible_text = re.sub(r'\x1b\[[0-9;]*m', '', generic_line)
            padding = " " * max(0, 68 - len(visible_text))
            print(Colors.CYAN + "║" + generic_line + padding + "║" + Colors.RESET)
        
        visited.remove(destination)
    
    def _resolve_destination_display(self, destination):
        """Resolve destination to display format with names."""
        if not destination:
            return "❓ Unknown"
            
        if ',' in destination:
            parts = destination.split(',')
            dest_type = parts[0]
            dest_id = parts[1] if len(parts) > 1 else 'Unknown'
            
            if dest_type == 'ext-local':
                # Handle voicemail (vmuXXX) vs direct extension
                if dest_id.startswith('vmu'):
                    ext_num = dest_id[3:]  # Remove 'vmu' prefix
                    ext = self._find_extension(ext_num)
                    if ext:
                        return f"📧 Extension {ext_num}: {ext.get('name', f'Extension {ext_num}')} (vmb{ext_num})"
                    return f"📧 Extension {ext_num}: Voicemail (vmb{ext_num})"
                elif dest_id.startswith('vmb'):
                    # Handle vmb623 format
                    ext_num = dest_id[3:]  # Remove 'vmb' prefix  
                    ext = self._find_extension(ext_num)
                    if ext:
                        return f"📧 Extension {ext_num}: {ext.get('name', f'Extension {ext_num}')} (vmb{ext_num})"
                    return f"📧 Extension {ext_num}: Voicemail (vmb{ext_num})"
                else:
                    ext = self._find_extension(dest_id)
                    if ext:
                        return f"📞 Extension {dest_id}: {ext.get('name', f'Extension {dest_id}')}"
                    return f"📞 Extension {dest_id}"
                    
            elif dest_type == 'timeconditions':
                tc = self._find_time_condition(dest_id)
                if tc:
                    return f"⏰ {tc.get('name', f'Time Condition {dest_id}')}"
                return f"⏰ Time Condition {dest_id}"
                
            elif dest_type == 'ext-group':
                rg = self._find_ring_group(dest_id)
                if rg:
                    return f"🔔 {rg.get('description', f'Ring Group {dest_id}')}"
                return f"🔔 Ring Group {dest_id}"
                
            elif dest_type == 'ivr':
                ivr = self._find_ivr_menu(dest_id)
                if ivr:
                    return f"🎵 {ivr.get('name', f'IVR {dest_id}')}"
                return f"🎵 IVR {dest_id}"
                
            elif dest_type == 'from-did-direct':
                # Handle direct extension routing
                ext = self._find_extension(dest_id)
                if ext:
                    return f"📞 Extension {dest_id}: {ext.get('name', f'Extension {dest_id}')}"
                return f"📞 Extension {dest_id}"
                
            else:
                return f"❓ {dest_type}: {dest_id}"
        else:
            return f"❓ {destination}"
    
    def _find_time_condition(self, tc_id):
        """Find time condition by ID."""
        for tc in self.data.get('time_conditions', []):
            if str(tc.get('id')) == str(tc_id):
                return tc
        return None
    
    def _get_time_condition_labels(self, tc):
        """Generate appropriate labels for time condition branches based on condition type"""
        if not tc:
            return "Condition True", "Condition False"
            
        name = tc.get('name', '').lower()
        mode = tc.get('mode', 'time-group')
        
        # Calendar-based conditions (holidays, special events)
        if mode == 'calendar-group':
            if 'holiday' in name:
                return "IS Holiday", "NOT Holiday"
            elif 'vacation' in name:
                return "IS Vacation", "NOT Vacation"
            elif 'closed' in name:
                return "IS Closed", "NOT Closed"
            elif 'special' in name or 'event' in name:
                return "IS Special Event", "NOT Special Event"
            else:
                return "Calendar Match", "Calendar No Match"
        
        # Time-group conditions (business hours, day/night)
        elif mode == 'time-group':
            if 'business' in name or 'office' in name:
                return "Business Hours", "After Hours"
            elif 'night' in name:
                return "Night Hours", "Day Hours"
            elif 'weekend' in name:
                return "Weekend", "Weekday"
            elif 'lunch' in name:
                return "Lunch Time", "Not Lunch"
            else:
                return "Time Match", "Time No Match"
        
        # Default for unknown modes
        else:
            return "Condition True", "Condition False"
    
    def _find_ring_group(self, rg_id):
        """Find ring group by ID."""
        for rg in self.data.get('ring_groups', []):
            if str(rg.get('group_num')) == str(rg_id):
                return rg
        return None
    
    def _find_ivr_menu(self, ivr_id):
        """Find IVR menu by ID."""
        for ivr in self.data.get('ivr_menus', []):
            if str(ivr.get('id')) == str(ivr_id):
                return ivr
        return None
    
    def _find_ivr_options(self, ivr_id):
        """Find IVR options for menu ID."""
        options = []
        for opt in self.data.get('ivr_options', []):
            if str(opt.get('ivr_id')) == str(ivr_id):
                options.append(opt)
        return options
    
    def _find_extension(self, ext_id):
        """Find extension by ID."""
        for ext in self.data.get('extensions', []):
            if str(ext.get('extension')) == str(ext_id):
                return ext
        return None
    
    def _find_setcid(self, setcid_id):
        """Find Set Caller ID by ID."""
        for setcid in self.data.get('setcid', []):
            if str(setcid.get('id')) == str(setcid_id):
                return setcid
        return None
    
    def _find_misc_destination(self, misc_id):
        """Find Misc Destination by ID."""
        for misc in self.data.get('misc_destinations', []):
            if str(misc.get('id')) == str(misc_id):
                return misc
        return None
    
    def _describe_callerid_transformation(self, name_template, num_template):
        """Describe what the caller ID transformation will do"""
        if not name_template and not num_template:
            return "No caller ID modification"
            
        transformations = []
        
        if name_template and name_template != 'Unknown':
            if '${CALLERID(name)}' in name_template:
                prefix = name_template.replace('${CALLERID(name)}', '').strip()
                if prefix:
                    transformations.append(f"Prepend '{prefix}' to caller's name")
                else:
                    transformations.append("Pass through caller's name unchanged")
            else:
                transformations.append(f"Set name to '{name_template}'")
                
        if num_template and num_template != 'Unknown':
            if '${CALLERID(num)}' in num_template:
                prefix = num_template.replace('${CALLERID(num)}', '').strip()
                if prefix:
                    transformations.append(f"Prepend '{prefix}' to caller's number")
                else:
                    transformations.append("Pass through caller's number unchanged")
            else:
                transformations.append(f"Set number to '{num_template}'")
                
        if transformations:
            return "; ".join(transformations)
        else:
            return "No caller ID modification"

    def _resolve_callerid_template(self, template):
        """Resolve caller ID template variables to example values."""
        if not template or template == 'Unknown':
            return template
            
        # Common substitutions for demonstration
        resolved = template
        resolved = resolved.replace('${CALLERID(name)}', 'John Smith')
        resolved = resolved.replace('${CALLERID(num)}', '555-123-4567')
        resolved = resolved.replace('${FROM_DID}', 'DID Number')
        resolved = resolved.replace('${CHANNEL}', 'SIP/provider-001')
        
        # Handle simple patterns
        if resolved != template:
            return resolved
        else:
            return template
    
    def _collect_toggle_controls(self):
        """Collect call flow toggle control information - placeholder for future enhancement."""
        return []
    
    def _print_toggle_item(self, toggle):
        """Print a toggle control item sample - placeholder for future enhancement."""
        pass
    
    def _find_toggle_control(self, tc_name):
        """Find toggle control information for a time condition - placeholder for future enhancement."""
        return None

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="FreePBX Universal Version-Aware ASCII Call Flow Generator"
    )
    
    parser.add_argument("--socket", help="MySQL socket path")
    parser.add_argument("--db-user", default="root", help="MySQL user")
    parser.add_argument("--db-password", help="MySQL password")
    parser.add_argument("--print-data", action="store_true", help="Print collected data")
    parser.add_argument("--detailed", action="store_true", help="Show detailed output")
    parser.add_argument("--did", help="Generate ASCII call flow for specific DID")
    parser.add_argument("--generate-flow", action="store_true", help="Generate ASCII call flow diagrams")
    
    args = parser.parse_args()
    
    print("🚀 FreePBX UNIVERSAL Version-Aware Call Flow Generator")
    print("Supports FreePBX 2.8-16.x, Asterisk 1.8-18.x, All Database Versions")
    print("=" * 80)
    
    # Initialize collector
    collector = FreePBXUniversalCollector(
        socket=args.socket,
        user=args.db_user,
        password=args.db_password
    )
    
    # Run complete analysis
    collector.analyze_system()
    
    # Handle arguments
    if args.print_data:
        print("\n" + "="*80)
        print("📋 COMPREHENSIVE DATA SUMMARY")
        print("="*80)
        for component, data in collector.data.items():
            count = len(data) if data else 0
            component_name = component.replace('_', ' ').title()
            print(f"{component_name}: {count} items")
            
    if args.did:
        collector.generate_ascii_callflow(did=args.did)
        
    if args.generate_flow:
        collector.generate_ascii_callflow()
        
    # Show usage examples if no specific action requested
    if not any([args.print_data, args.did, args.generate_flow]):
        print("🔄 Next: Use this data to generate intelligent ASCII call flow diagrams.")
        print("\n💡 USAGE EXAMPLES:")
        print("  # Print summary of collected data:")
        print("  python freepbx_version_aware_ascii_callflow.py --print-data")
        print()
        print("  # Print detailed data:")
        print("  python freepbx_version_aware_ascii_callflow.py --print-data --detailed")
        print()
        print("  # Generate ASCII flow for specific DID:")
        print("  python freepbx_version_aware_ascii_callflow.py --did 5176790109")
        print()
        print("  # Generate ASCII flows for all DIDs:")
        print("  python freepbx_version_aware_ascii_callflow.py --generate-flow")
        
    print(f"\n✅ Universal FreePBX analysis complete!")
    print(f"📊 Schema adapted for FreePBX {collector.freepbx_version or 'Unknown'}")
    print(f"🔧 {len(collector.schema_map)} components successfully mapped")

if __name__ == "__main__":
    main()