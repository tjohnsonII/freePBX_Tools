#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FreePBX Complete Version-Aware ASCII Call Flow Generator
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
        print("🔍 COMPREHENSIVE FREEPBX SYSTEM ANALYSIS")
        print("=" * 70)
        
        # Phase 1: Version Detection
        self._detect_asterisk_version()
        self._detect_freepbx_version()
        self._detect_database_version()
        self._discover_all_tables()
        
        print("=" * 70)
        print(f"📊 SYSTEM PROFILE:")
        print(f"   FreePBX: {self.freepbx_version or 'Unknown'} (Major: {self.freepbx_major or 'Unknown'})")
        print(f"   Asterisk: {self.asterisk_version or 'Unknown'} (Major: {self.asterisk_major or 'Unknown'})")
        print(f"   Database: {self.db_version or 'Unknown'}")
        print(f"   Tables Found: {len(self.all_tables)}")
        print("=" * 70)
        
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
        print("\n🗂️  ADAPTIVE SCHEMA MAPPING")
        print("=" * 70)
        
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
        ]
        
        successful_mappings = 0
        for component, mapper_func in mappings:
            try:
                mapping = mapper_func()
                if mapping:
                    self.schema_map[component] = mapping
                    successful_mappings += 1
                    print(f"   ✓ {component.replace('_', ' ').title()}: {mapping['table']} → {len(mapping['fields'])} fields")
                else:
                    print(f"   ❌ {component.replace('_', ' ').title()}: No compatible table found")
            except Exception as e:
                print(f"   ❌ {component.replace('_', ' ').title()}: Mapping error - {e}")
                
        print("=" * 70)
        print(f"📊 SCHEMA MAPPING: {successful_mappings}/{len(mappings)} components mapped")
        print("=" * 70)
        
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
                            fields['destination'] = field
                            break
                            
                    if 'ivr_id' in fields and 'selection' in fields:
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
        
    def _collect_all_data(self):
        """Collect data using discovered schema mappings."""
        print("\n📊 VERSION-AWARE DATA COLLECTION")
        print("=" * 70)
        
        total_items = 0
        for component, schema in self.schema_map.items():
            try:
                data = self._collect_component_data(component, schema)
                self.data[component] = data
                count = len(data) if data else 0
                total_items += count
                
                status = "✓" if count > 0 else "○"
                print(f"   {status} {component.replace('_', ' ').title()}: {count} items")
                
                # Show sample data
                if count > 0 and count <= 3:
                    for item in data:
                        self._print_sample_item(component, item)
                elif count > 3:
                    for item in data[:2]:
                        self._print_sample_item(component, item)
                    print(f"      ... and {count - 2} more")
                    
            except Exception as e:
                print(f"   ❌ {component.replace('_', ' ').title()}: Collection error - {e}")
                
        print("=" * 70)
        print(f"🎯 TOTAL CONFIGURATION ITEMS: {total_items}")
        print("=" * 70)
        
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
        print("\n📞 ASCII CALL FLOW GENERATION")
        print("=" * 70)
        
        if not self.data.get('inbound_routes'):
            print("   ⚠ No inbound routes found - cannot generate call flows")
            return
        
        if did:
            self._generate_single_did_flow(did)
        else:
            self._generate_all_flows()
    
    def _generate_all_flows(self):
        """Generate ASCII call flows for all inbound routes."""
        print(f"\n🎯 GENERATING ASCII CALL FLOWS FOR ALL DIDS")
        print("=" * 60)
        
        inbound_routes = self.data.get('inbound_routes', [])
        if not inbound_routes:
            print("❌ No inbound routes found")
            return
        
        print(f"✓ Found {len(inbound_routes)} inbound routes")
        
        for route in inbound_routes:
            did = route.get('did') or 'Unknown'
            description = route.get('description') or f"Route for {did}"
            destination = route.get('destination') or 'Unknown'
            
            print(f"\n📞 DID: {did} - {description}")
            print("-" * 40)
            print(f"✓ Destination: {destination}")
            
            # Generate simple flow visualization
            self._render_simple_flow(did, route)
    
    def _generate_single_did_flow(self, did):
        """Generate ASCII flow for a specific DID."""
        print(f"\n🎯 GENERATING ASCII CALL FLOW FOR DID: {did}")
        print("=" * 60)
        
        # Find the DID in inbound routes
        route = None
        for r in self.data.get('inbound_routes', []):
            if r.get('did') == did:
                route = r
                break
        
        if not route:
            print(f"❌ No inbound route found for DID: {did}")
            return
            
        print(f"✓ Found route: {route.get('description', 'Unnamed Route')}")
        print(f"✓ Destination: {route.get('destination', 'Unknown')}")
        
        # Generate flow visualization
        self._render_simple_flow(did, route)
    
    def _render_simple_flow(self, did, route):
        """Render a simple ASCII call flow."""
        print(f"\n📞 CALL FLOW: {did}")
        print("=" * 50)
        
        destination = route.get('destination', '')
        description = route.get('description', 'Unknown Route')
        
        print(f"📱 Incoming Call: {did} ({description})")
        print("│")
        
        if destination:
            if ',' in destination:
                dest_parts = destination.split(',')
                dest_type = dest_parts[0]
                dest_id = dest_parts[1] if len(dest_parts) > 1 else 'Unknown'
                
                if dest_type == 'timeconditions':
                    tc = self._find_time_condition(dest_id)
                    if tc:
                        print(f"├─ ⏰ Time Condition: {tc.get('name', dest_id)}")
                        print("│  │")
                        
                        # Get appropriate labels for this time condition
                        true_label, false_label = self._get_time_condition_labels(tc)
                        
                        print(f"│  ├─ ✅ {true_label} → {self._resolve_destination_display(tc.get('true_dest', 'Unknown'))}")
                        print(f"│  └─ ❌ {false_label} → {self._resolve_destination_display(tc.get('false_dest', 'Unknown'))}")
                    else:
                        print(f"├─ ⏰ Time Condition: {dest_id} (details not found)")
                
                elif dest_type == 'ext-group':
                    rg = self._find_ring_group(dest_id)
                    if rg:
                        print(f"└─ 🔔 Ring Group: {rg.get('description', dest_id)}")
                        if rg.get('member_list'):
                            members = rg['member_list'].split('-')
                            for i, member in enumerate(members[:3]):
                                if member:
                                    connector = "├─" if i < len(members[:3]) - 1 else "└─"
                                    print(f"   {connector} 📞 Extension: {member}")
                            if len(members) > 3:
                                print(f"   └─ ... and {len(members) - 3} more extensions")
                    else:
                        print(f"└─ 🔔 Ring Group: {dest_id} (details not found)")
                
                elif dest_type.startswith('ivr'):
                    ivr = self._find_ivr_menu(dest_id)
                    if ivr:
                        print(f"└─ 🎵 IVR Menu: {ivr.get('name', dest_id)}")
                        options = self._find_ivr_options(dest_id)
                        for i, opt in enumerate(options[:5]):
                            selection = opt.get('selection', 'Unknown')
                            dest = opt.get('destination', 'Unknown')
                            connector = "├─" if i < len(options[:5]) - 1 else "└─"
                            print(f"   {connector} [{selection}] → {dest}")
                        if len(options) > 5:
                            print(f"   └─ ... and {len(options) - 5} more options")
                    else:
                        print(f"└─ 🎵 IVR Menu: {dest_id} (details not found)")
                
                elif dest_type == 'from-did-direct':
                    ext = self._find_extension(dest_id)
                    if ext:
                        print(f"└─ 📞 Direct Extension: {dest_id} ({ext.get('name', 'Unknown')})")
                    else:
                        print(f"└─ 📞 Direct Extension: {dest_id}")
                
                else:
                    print(f"└─ ❓ {dest_type}: {dest_id}")
            else:
                print(f"└─ ❓ Destination: {destination}")
        else:
            print("└─ ❓ No destination configured")
        
        print()
    
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
                        return f"📧 {ext.get('name', f'Extension {ext_num}')} Voicemail"
                    return f"📧 Extension {ext_num} Voicemail"
                else:
                    ext = self._find_extension(dest_id)
                    if ext:
                        return f"📞 {ext.get('name', f'Extension {dest_id}')}"
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
                
            elif dest_type.startswith('ivr'):
                ivr = self._find_ivr_menu(dest_id)
                if ivr:
                    return f"🎵 {ivr.get('name', f'IVR {dest_id}')}"
                return f"🎵 IVR {dest_id}"
                
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