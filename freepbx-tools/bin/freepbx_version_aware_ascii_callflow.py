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
        
        # Collect toggle controls - placeholder for future enhancement
        try:
            self.data['toggle_controls'] = []
            count = 0
            total_items += count
            
            status = "○"
            print(f"   {status} Toggle Controls: {count} items")
                    
        except Exception as e:
            print(f"   ❌ Toggle Controls: Collection error - {e}")
                
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
        """Render a complete ASCII call flow tree."""
        print(f"\n📞 CALL FLOW: {did}")
        print("=" * 50)
        
        destination = route.get('destination', '')
        description = route.get('description', 'Unknown Route')
        
        print(f"📱 Incoming Call: {did} ({description})")
        print("│")
        
        if destination:
            self._render_destination_tree(destination, "", True)
        else:
            print("└─ ❓ No destination configured")
        
        print()

    def _render_destination_tree(self, destination, prefix="", is_last=True, visited=None, depth=0):
        """Recursively render the complete call tree for a destination."""
        if visited is None:
            visited = set()
        
        # Prevent infinite loops
        if destination in visited or depth > 10:
            connector = "└─" if is_last else "├─"
            print(f"{prefix}{connector} 🔄 Loop detected or max depth reached: {destination}")
            return
        
        visited.add(destination)
        
        # Parse destination
        if ',' in destination:
            dest_parts = destination.split(',')
            dest_type = dest_parts[0]
            dest_id = dest_parts[1] if len(dest_parts) > 1 else 'Unknown'
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
                    print(f"{prefix}{connector} ⏰ Time Condition: {tc_name} (Toggle Control)")
                    print(f"{child_prefix}├─ 🎛️  Toggle: Use feature codes to override")
                    print(f"{child_prefix}│")
                else:
                    print(f"{prefix}{connector} ⏰ Time Condition: {tc_name}")
                    print(f"{child_prefix}│")
                
                # Get appropriate labels for this time condition
                true_label, false_label = self._get_time_condition_labels(tc)
                
                true_dest = tc.get('true_dest', '')
                false_dest = tc.get('false_dest', '')
                
                # Render true branch
                print(f"{child_prefix}├─ {true_label}")
                if true_dest:
                    self._render_destination_tree(true_dest, child_prefix + "│  ", False, visited.copy(), depth + 1)
                else:
                    print(f"{child_prefix}│  └─ ❓ No true destination")
                
                print(f"{child_prefix}│")
                
                # Render false branch
                print(f"{child_prefix}└─ {false_label}")
                if false_dest:
                    self._render_destination_tree(false_dest, child_prefix + "   ", True, visited.copy(), depth + 1)
                else:
                    print(f"{child_prefix}   └─ ❓ No false destination")
            else:
                print(f"{prefix}{connector} ⏰ Time Condition: {dest_id} (details not found)")
        
        elif dest_type == 'ext-group':
            rg = self._find_ring_group(dest_id)
            if rg:
                print(f"{prefix}{connector} 🔔 Ring Group: {rg.get('description', dest_id)}")
                
                # Show ring group members
                if rg.get('member_list'):
                    members = [m for m in rg['member_list'].split('-') if m]
                    print(f"{child_prefix}├─ 👥 Members:")
                    for i, member in enumerate(members):  # Show ALL members
                        mem_connector = "├─" if i < len(members) - 1 else "└─"
                        ext = self._find_extension(member)
                        ext_name = ext.get('name', 'Unknown') if ext else 'Unknown'
                        print(f"{child_prefix}│  {mem_connector} 📞 {member} ({ext_name})")
                
                # Show failover destination if exists - use correct field mapping
                failover_dest = rg.get('failover_dest', '') or rg.get('postdest', '') or rg.get('dest', '')
                if failover_dest and failover_dest != 'app-blackhole,hangup,1':
                    print(f"{child_prefix}│")
                    print(f"{child_prefix}└─ 🔀 No Answer Failover:")
                    self._render_destination_tree(failover_dest, child_prefix + "   ", True, visited.copy(), depth + 1)
                else:
                    print(f"{child_prefix}└─ 🔚 No failover (call ends)")
            else:
                print(f"{prefix}{connector} 🔔 Ring Group: {dest_id} (details not found)")
        
        elif dest_type.startswith('ivr'):
            ivr = self._find_ivr_menu(dest_id)
            if ivr:
                print(f"{prefix}{connector} 🎵 IVR Menu: {ivr.get('name', dest_id)}")
                
                # Show IVR options
                options = self._find_ivr_options(dest_id)
                if options:
                    print(f"{child_prefix}├─ 🔢 Options:")
                    for i, opt in enumerate(options[:5]):  # Show up to 5 options
                        opt_connector = "├─" if i < min(len(options), 5) - 1 else "└─"
                        selection = opt.get('selection', '?')
                        opt_dest = opt.get('dest', 'Unknown')
                        print(f"{child_prefix}│  {opt_connector} [{selection}] →")
                        if opt_dest and opt_dest != 'Unknown':
                            self._render_destination_tree(opt_dest, child_prefix + "│  " + ("   " if i == min(len(options), 5) - 1 else "│  "), True, visited.copy(), depth + 1)
                    if len(options) > 5:
                        print(f"{child_prefix}│  └─ ... and {len(options) - 5} more options")
                
                print(f"{child_prefix}└─ 🔚 (IVR timeout/invalid handling)")
            else:
                print(f"{prefix}{connector} 🎵 IVR Menu: {dest_id} (details not found)")
        
        elif dest_type == 'from-did-direct':
            ext = self._find_extension(dest_id)
            if ext:
                print(f"{prefix}{connector} 📞 Direct Extension: {dest_id} ({ext.get('name', 'Unknown')})")
                print(f"{child_prefix}└─ 📧 Voicemail: {ext.get('name', 'Unknown')} (if no answer)")
            else:
                print(f"{prefix}{connector} 📞 Direct Extension: {dest_id}")
                print(f"{child_prefix}└─ 📧 Voicemail (if no answer)")
        
        elif dest_type == 'ext-local':
            # Handle voicemail, announcements, etc.
            if 'vmu' in dest_id:
                ext_num = dest_id.replace('vmu', '')
                ext = self._find_extension(ext_num)
                if ext:
                    print(f"{prefix}{connector} 📧 Voicemail: {ext.get('name', 'Unknown')} ({ext_num})")
                else:
                    print(f"{prefix}{connector} 📧 Voicemail: Extension {ext_num}")
            else:
                print(f"{prefix}{connector} 📱 Local Extension: {dest_id}")
                # Could chain to voicemail on no answer
        
        elif dest_type == 'app-blackhole':
            print(f"{prefix}{connector} 🔚 Hangup")
        
        elif dest_type == 'app-announcement':
            print(f"{prefix}{connector} 📢 Announcement: {dest_id}")
        
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
                print(f"{prefix}{connector} 🎯 {desc}")
                print(f"{child_prefix}└─ ☎️  Final Destination: {final_dest}")
            else:
                print(f"{prefix}{connector} 🎯 Misc Destination: {dest_id} (details not found)")
        
        else:
            # Generic destination
            display = self._resolve_destination_display(destination)
            print(f"{prefix}{connector} 🎯 {display}")
        
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