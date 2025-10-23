#!/usr/bin/env python3
"""
FreePBX ASCII Call Flow Generator - Comprehensive Data Collector
Gathers ALL FreePBX call flow configuration data to create complete call flow maps.

Core Approach: Collect EVERYTHING first, then build intelligent call flow visualizations.

Author: FreePBX Tools Team
Purpose: Complete FreePBX system analysis for human-readable call flow diagrams
"""

import sys
import subprocess
import argparse
import json
import time
from collections import defaultdict

# Default MySQL socket path for FreePBX
DEFAULT_SOCK = "/var/lib/mysql/mysql.sock"

def run_mysql(query, socket=DEFAULT_SOCK, user="root", password=None):
    """Execute MySQL query and return results."""
    cmd = ["mysql", "-NBe", query, "asterisk", "-u", user]
    if socket:
        cmd.extend(["-S", socket])
    if password:
        cmd.extend([f"-p{password}"])
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                              universal_newlines=True, timeout=30)
        if result.returncode != 0:
            print(f"MySQL Error: {result.stderr}")
            return ""
        return result.stdout
    except Exception as e:
        print(f"Database connection error: {e}")
        return ""

def parse_mysql_result(result, columns):
    """Parse MySQL result into list of dictionaries."""
    if not result.strip():
        return []
    
    rows = []
    for line in result.strip().split('\n'):
        parts = line.split('\t')
        # Pad with empty strings if needed
        while len(parts) < len(columns):
            parts.append('')
        row = dict(zip(columns, parts))
        rows.append(row)
    return rows

class FreePBXDataCollector:
    """
    Comprehensive FreePBX data collector that gathers ALL call flow configuration.
    This forms the complete foundation for intelligent call flow analysis.
    """
    
    def __init__(self, socket=DEFAULT_SOCK, user="root", password=None):
        self.socket = socket
        self.user = user
        self.password = password
        
        # Complete FreePBX configuration data
        self.data = {
            # ENTRY POINTS
            'inbound_routes': [],      # DID numbers and caller ID routing
            'custom_contexts': [],     # Trunk-specific routing contexts
            
            # ROUTING LOGIC  
            'time_conditions': [],     # Business hours, holiday schedules
            'ivr_menus': [],          # Interactive voice response menus
            'ivr_options': [],        # IVR menu key press destinations
            'call_flow_toggles': [],  # Manual routing control switches
            
            # DESTINATIONS
            'extensions': [],         # User extensions and devices
            'queues': [],            # Call center queues
            'queue_members': [],     # Queue agent assignments
            'ring_groups': [],       # Hunt groups
            'voicemail_boxes': [],   # Voicemail configurations
            'conferences': [],       # Conference rooms
            
            # ANNOUNCEMENTS & MEDIA
            'announcements': [],     # Audio file playback
            'music_on_hold': [],     # Hold music classes
            'system_recordings': [], # Custom recordings
            
            # ADVANCED FEATURES
            'follow_me': [],         # Find me anywhere routing
            'paging_groups': [],     # Overhead paging
            'parking_lots': [],      # Call parking
            'misc_destinations': [], # Custom applications
            'disa': [],             # Direct inward system access
            
            # OUTBOUND ROUTING
            'outbound_routes': [],   # External call routing
            'trunks': [],           # Carrier connections
            
            # CALL FLOW RELATIONSHIPS
            'feature_codes': [],     # Star codes (*97, etc.)
            'speed_dials': [],       # Quick dial shortcuts
            'call_recording': [],    # Recording configurations
            
            # SYSTEM LEVEL
            'modules': [],           # Enabled/disabled modules
            'global_settings': [],   # System-wide settings
            'custom_extensions': [], # Hand-coded dialplan
        }
        
    def collect_all_data(self):
        """Collect ALL FreePBX call flow configuration data."""
        print("🔍 FreePBX Comprehensive Data Collection")
        print("=" * 60)
        print("Gathering ALL call flow configuration data...")
        print()
        
        # Entry Points
        self._collect_inbound_routes()
        self._collect_custom_contexts()
        
        # Routing Logic
        self._collect_time_conditions()
        self._collect_ivr_menus()
        self._collect_ivr_options()
        self._collect_call_flow_toggles()
        
        # Destinations
        self._collect_extensions()
        self._collect_queues()
        self._collect_queue_members()
        self._collect_ring_groups()
        self._collect_voicemail_boxes()
        self._collect_conferences()
        
        # Announcements & Media
        self._collect_announcements()
        self._collect_music_on_hold()
        self._collect_system_recordings()
        
        # Advanced Features
        self._collect_follow_me()
        self._collect_paging_groups()
        self._collect_parking_lots()
        self._collect_misc_destinations()
        self._collect_disa()
        
        # Outbound Routing
        self._collect_outbound_routes()
        self._collect_trunks()
        
        # Relationships
        self._collect_feature_codes()
        self._collect_speed_dials()
        self._collect_call_recording()
        
        # System Level
        self._collect_modules()
        self._collect_global_settings()
        self._collect_custom_extensions()
        
        # Show comprehensive summary
        self._show_collection_summary()
        
    def _collect_inbound_routes(self):
        """Collect inbound route configurations (DID routing)."""
        print("📞 Collecting Inbound Routes...")
        
        query = """
        SELECT extension, description, destination, cidnum, privacyman, 
               alertinfo, ringing, mohclass, delay_answer, pricid
        FROM incoming
        ORDER BY extension
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['inbound_routes'] = parse_mysql_result(result, [
            'extension', 'description', 'destination', 'cidnum', 'privacyman',
            'alertinfo', 'ringing', 'mohclass', 'delay_answer', 'pricid'
        ])
        
        print(f"   ✓ Found {len(self.data['inbound_routes'])} inbound routes")
        
    def _collect_custom_contexts(self):
        """Collect custom dialplan contexts."""
        print("🔧 Collecting Custom Contexts...")
        
        query = """
        SELECT context, exten, priority, app, appdata
        FROM extensions 
        WHERE context LIKE '%incoming%' OR context LIKE '%custom%'
        ORDER BY context, exten, priority
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['custom_contexts'] = parse_mysql_result(result, [
            'context', 'exten', 'priority', 'app', 'appdata'
        ])
        
        print(f"   ✓ Found {len(self.data['custom_contexts'])} custom context entries")
        
    def _collect_time_conditions(self):
        """Collect time condition configurations."""
        print("⏰ Collecting Time Conditions...")
        
        # Try multiple table structures
        queries = [
            """
            SELECT timeconditions_id, displayname, time, truegoto, falsegoto,
                   deptname, generate_hint, toggle_mode
            FROM timeconditions
            ORDER BY timeconditions_id
            """,
            """
            SELECT id as timeconditions_id, description as displayname, 
                   time_spec as time, true_dest as truegoto, false_dest as falsegoto,
                   '' as deptname, 0 as generate_hint, 0 as toggle_mode
            FROM time_conditions
            ORDER BY id
            """
        ]
        
        for query in queries:
            try:
                result = run_mysql(query, self.socket, self.user, self.password)
                if result.strip():
                    self.data['time_conditions'] = parse_mysql_result(result, [
                        'timeconditions_id', 'displayname', 'time', 'truegoto', 'falsegoto',
                        'deptname', 'generate_hint', 'toggle_mode'
                    ])
                    break
            except:
                continue
                
        print(f"   ✓ Found {len(self.data['time_conditions'])} time conditions")
        
    def _collect_ivr_menus(self):
        """Collect IVR menu configurations."""
        print("📋 Collecting IVR Menus...")
        
        query = """
        SELECT id, displayname, announcement, directdial, timeout, 
               invalid_loops, invalid_retry_recording, invalid_destination,
               timeout_time, timeout_recording, timeout_destination,
               retvm, retvm_dest
        FROM ivr
        ORDER BY id
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['ivr_menus'] = parse_mysql_result(result, [
            'id', 'displayname', 'announcement', 'directdial', 'timeout',
            'invalid_loops', 'invalid_retry_recording', 'invalid_destination',
            'timeout_time', 'timeout_recording', 'timeout_destination',
            'retvm', 'retvm_dest'
        ])
        
        print(f"   ✓ Found {len(self.data['ivr_menus'])} IVR menus")
        
    def _collect_ivr_options(self):
        """Collect IVR menu option mappings."""
        print("🔢 Collecting IVR Options...")
        
        query = """
        SELECT ivr_id, selection, dest, ivr_ret
        FROM ivr_details
        ORDER BY ivr_id, selection
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['ivr_options'] = parse_mysql_result(result, [
            'ivr_id', 'selection', 'dest', 'ivr_ret'
        ])
        
        print(f"   ✓ Found {len(self.data['ivr_options'])} IVR menu options")
        
    def _collect_call_flow_toggles(self):
        """Collect call flow control toggle states."""
        print("🎛️  Collecting Call Flow Toggles...")
        
        # This table may not exist in all FreePBX versions
        query = """
        SELECT id, description, state, on_dest, off_dest, password
        FROM callflow_toggle
        ORDER BY id
        """
        
        try:
            result = run_mysql(query, self.socket, self.user, self.password)
            self.data['call_flow_toggles'] = parse_mysql_result(result, [
                'id', 'description', 'state', 'on_dest', 'off_dest', 'password'
            ])
        except:
            self.data['call_flow_toggles'] = []
            
        print(f"   ✓ Found {len(self.data['call_flow_toggles'])} call flow toggles")
        
    def _collect_extensions(self):
        """Collect extension/user configurations."""
        print("📱 Collecting Extensions...")
        
        # Try multiple table structures for different FreePBX versions
        queries = [
            """
            SELECT extension, name, voicemail, ringtimer, noanswer, recordoutgoing, 
                   recordincoming, canrecord, outboundcid, sipname, noanswer_cid,
                   busy_cid, chanunavail_cid, noanswer_dest, busy_dest, chanunavail_dest
            FROM users
            WHERE extension IS NOT NULL AND extension != ''
            ORDER BY CAST(extension AS UNSIGNED)
            """,
            """
            SELECT extension, displayname as name, voicemail, ringtimer, '' as noanswer,
                   '' as recordoutgoing, '' as recordincoming, '' as canrecord,
                   '' as outboundcid, '' as sipname, '' as noanswer_cid,
                   '' as busy_cid, '' as chanunavail_cid, '' as noanswer_dest,
                   '' as busy_dest, '' as chanunavail_dest
            FROM extensions
            WHERE extension IS NOT NULL AND extension != ''
            ORDER BY CAST(extension AS UNSIGNED)
            """
        ]
        
        for query in queries:
            try:
                result = run_mysql(query, self.socket, self.user, self.password)
                if result.strip():
                    self.data['extensions'] = parse_mysql_result(result, [
                        'extension', 'name', 'voicemail', 'ringtimer', 'noanswer',
                        'recordoutgoing', 'recordincoming', 'canrecord', 'outboundcid',
                        'sipname', 'noanswer_cid', 'busy_cid', 'chanunavail_cid',
                        'noanswer_dest', 'busy_dest', 'chanunavail_dest'
                    ])
                    break
            except:
                continue
                
        print(f"   ✓ Found {len(self.data['extensions'])} extensions")
        
    def _collect_queues(self):
        """Collect queue configurations."""
        print("🎯 Collecting Queues...")
        
        # Queues use a key-value config system
        query = """
        SELECT extension, keyword, data
        FROM queues_config
        WHERE keyword IN ('description', 'strategy', 'timeout', 'retry', 'maxlen',
                         'joinempty', 'leavewhenempty', 'ringinuse', 'autofill',
                         'eventmemberstatus', 'eventwhencalled', 'reportholdtime',
                         'memberdelay', 'weight', 'timeoutrestart', 'timeoutpriority')
        ORDER BY extension, keyword
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        raw_queue_data = parse_mysql_result(result, ['extension', 'keyword', 'data'])
        
        # Convert key-value pairs to structured data
        queue_configs = defaultdict(dict)
        for row in raw_queue_data:
            queue_configs[row['extension']][row['keyword']] = row['data']
            
        # Convert to list format
        self.data['queues'] = []
        for extension, config in queue_configs.items():
            queue_info = {'extension': extension}
            queue_info.update(config)
            self.data['queues'].append(queue_info)
            
        print(f"   ✓ Found {len(self.data['queues'])} queues")
        
    def _collect_queue_members(self):
        """Collect queue member assignments."""
        print("👥 Collecting Queue Members...")
        
        query = """
        SELECT extension, interface, penalty, paused
        FROM queue_members
        ORDER BY extension, interface
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['queue_members'] = parse_mysql_result(result, [
            'extension', 'interface', 'penalty', 'paused'
        ])
        
        print(f"   ✓ Found {len(self.data['queue_members'])} queue member assignments")
        
    def _collect_ring_groups(self):
        """Collect ring group configurations."""
        print("🔔 Collecting Ring Groups...")
        
        query = """
        SELECT grpnum, description, strategy, grptime, grplist, 
               grppre, alertinfo, needsconf, remotealert_id,
               toolate_id, ringing, postdest, recording, mohclass
        FROM ringgroups
        ORDER BY grpnum
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['ring_groups'] = parse_mysql_result(result, [
            'grpnum', 'description', 'strategy', 'grptime', 'grplist',
            'grppre', 'alertinfo', 'needsconf', 'remotealert_id',
            'toolate_id', 'ringing', 'postdest', 'recording', 'mohclass'
        ])
        
        print(f"   ✓ Found {len(self.data['ring_groups'])} ring groups")
        
    def _collect_voicemail_boxes(self):
        """Collect voicemail box configurations."""
        print("📧 Collecting Voicemail Boxes...")
        
        query = """
        SELECT mailbox, context, fullname, email, pager, attach, 
               saycid, review, operator, envelope, sayduration,
               saydurationm, sendvoicemail, delete, nextaftercmd, forcename,
               forcegreetings, hidefromdir, passwordlocation, emailsubject,
               emailbody, emaildateformat, pagerfromstring, pagersubject, pagerbody
        FROM voicemail_users
        ORDER BY CAST(mailbox AS UNSIGNED)
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['voicemail_boxes'] = parse_mysql_result(result, [
            'mailbox', 'context', 'fullname', 'email', 'pager', 'attach',
            'saycid', 'review', 'operator', 'envelope', 'sayduration',
            'saydurationm', 'sendvoicemail', 'delete', 'nextaftercmd', 'forcename',
            'forcegreetings', 'hidefromdir', 'passwordlocation', 'emailsubject',
            'emailbody', 'emaildateformat', 'pagerfromstring', 'pagersubject', 'pagerbody'
        ])
        
        print(f"   ✓ Found {len(self.data['voicemail_boxes'])} voicemail boxes")
        
    def _collect_conferences(self):
        """Collect conference room configurations."""
        print("🎤 Collecting Conferences...")
        
        query = """
        SELECT exten, description, userpin, adminpin, options, users, 
               music, startmuted, opts, timeout
        FROM meetme
        ORDER BY exten
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['conferences'] = parse_mysql_result(result, [
            'exten', 'description', 'userpin', 'adminpin', 'options', 'users',
            'music', 'startmuted', 'opts', 'timeout'
        ])
        
        print(f"   ✓ Found {len(self.data['conferences'])} conference rooms")
        
    def _collect_announcements(self):
        """Collect announcement configurations."""
        print("📢 Collecting Announcements...")
        
        query = """
        SELECT announcement_id, description, filename, repeat_msg, allow_skip
        FROM announcement
        ORDER BY announcement_id
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['announcements'] = parse_mysql_result(result, [
            'announcement_id', 'description', 'filename', 'repeat_msg', 'allow_skip'
        ])
        
        print(f"   ✓ Found {len(self.data['announcements'])} announcements")
        
    def _collect_music_on_hold(self):
        """Collect music on hold class configurations."""
        print("🎵 Collecting Music on Hold...")
        
        query = """
        SELECT name, mode, directory, application, sort, format, random
        FROM musiconhold
        ORDER BY name
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['music_on_hold'] = parse_mysql_result(result, [
            'name', 'mode', 'directory', 'application', 'sort', 'format', 'random'
        ])
        
        print(f"   ✓ Found {len(self.data['music_on_hold'])} music on hold classes")
        
    def _collect_system_recordings(self):
        """Collect system recording configurations."""
        print("🎙️  Collecting System Recordings...")
        
        query = """
        SELECT id, displayname, filename, description
        FROM recordings
        ORDER BY displayname
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['system_recordings'] = parse_mysql_result(result, [
            'id', 'displayname', 'filename', 'description'
        ])
        
        print(f"   ✓ Found {len(self.data['system_recordings'])} system recordings")
        
    def _collect_follow_me(self):
        """Collect follow me configurations."""
        print("📱 Collecting Follow Me...")
        
        query = """
        SELECT grpnum, strategy, grptime, grplist, annmsg_id, postdest,
               dring, needsconf, remotealert_id, toolate_id, ringing,
               pre_ring, ddial, changecid, fixedcid, fcid_name_prefix,
               fcid_number_prefix, recording
        FROM followme
        ORDER BY grpnum
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['follow_me'] = parse_mysql_result(result, [
            'grpnum', 'strategy', 'grptime', 'grplist', 'annmsg_id', 'postdest',
            'dring', 'needsconf', 'remotealert_id', 'toolate_id', 'ringing',
            'pre_ring', 'ddial', 'changecid', 'fixedcid', 'fcid_name_prefix',
            'fcid_number_prefix', 'recording'
        ])
        
        print(f"   ✓ Found {len(self.data['follow_me'])} follow me configurations")
        
    def _collect_paging_groups(self):
        """Collect paging group configurations."""
        print("📯 Collecting Paging Groups...")
        
        query = """
        SELECT page_group, description, device_list, force_page, duplex, options
        FROM paging
        ORDER BY page_group
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['paging_groups'] = parse_mysql_result(result, [
            'page_group', 'description', 'device_list', 'force_page', 'duplex', 'options'
        ])
        
        print(f"   ✓ Found {len(self.data['paging_groups'])} paging groups")
        
    def _collect_parking_lots(self):
        """Collect parking lot configurations."""
        print("🅿️  Collecting Parking Lots...")
        
        query = """
        SELECT keyword, data
        FROM parkinglot
        WHERE keyword IN ('parkext', 'parkpos', 'context', 'parkingtime',
                         'courtesytone', 'parkedplay', 'comebacktoorigin',
                         'comebackdialtime', 'comebackcontext')
        ORDER BY keyword
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        raw_parking_data = parse_mysql_result(result, ['keyword', 'data'])
        
        # Convert key-value pairs to structured data
        parking_config = {}
        for row in raw_parking_data:
            parking_config[row['keyword']] = row['data']
            
        self.data['parking_lots'] = [parking_config] if parking_config else []
        
        print(f"   ✓ Found {len(self.data['parking_lots'])} parking lot configurations")
        
    def _collect_misc_destinations(self):
        """Collect miscellaneous application destinations."""
        print("🔗 Collecting Misc Destinations...")
        
        query = """
        SELECT id, description, dest
        FROM miscapps
        ORDER BY description
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['misc_destinations'] = parse_mysql_result(result, [
            'id', 'description', 'dest'
        ])
        
        print(f"   ✓ Found {len(self.data['misc_destinations'])} misc destinations")
        
    def _collect_disa(self):
        """Collect DISA (Direct Inward System Access) configurations."""
        print("☎️  Collecting DISA...")
        
        query = """
        SELECT disa_id, displayname, pin, cid, context, hangup, digittimeout
        FROM disa
        ORDER BY displayname
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['disa'] = parse_mysql_result(result, [
            'disa_id', 'displayname', 'pin', 'cid', 'context', 'hangup', 'digittimeout'
        ])
        
        print(f"   ✓ Found {len(self.data['disa'])} DISA configurations")
        
    def _collect_outbound_routes(self):
        """Collect outbound route configurations."""
        print("🛣️  Collecting Outbound Routes...")
        
        query = """
        SELECT route_id, name, outcid, outcid_mode, password, emergency_route,
               intracompany_route, mohclass, time_group_id, patterns, trunk_list
        FROM outbound_routes
        ORDER BY route_id
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['outbound_routes'] = parse_mysql_result(result, [
            'route_id', 'name', 'outcid', 'outcid_mode', 'password', 'emergency_route',
            'intracompany_route', 'mohclass', 'time_group_id', 'patterns', 'trunk_list'
        ])
        
        print(f"   ✓ Found {len(self.data['outbound_routes'])} outbound routes")
        
    def _collect_trunks(self):
        """Collect trunk configurations."""
        print("📡 Collecting Trunks...")
        
        query = """
        SELECT trunkid, name, tech, outcid, keepcid, maxchans, failscript,
               dialoutprefix, channelid, usercontext, provider, disabled
        FROM trunks
        ORDER BY name
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['trunks'] = parse_mysql_result(result, [
            'trunkid', 'name', 'tech', 'outcid', 'keepcid', 'maxchans', 'failscript',
            'dialoutprefix', 'channelid', 'usercontext', 'provider', 'disabled'
        ])
        
        print(f"   ✓ Found {len(self.data['trunks'])} trunks")
        
    def _collect_feature_codes(self):
        """Collect feature code configurations."""
        print("⭐ Collecting Feature Codes...")
        
        query = """
        SELECT modulename, featurename, description, defaultcode, enabled, customcode
        FROM featurecodes
        WHERE enabled = 1
        ORDER BY modulename, featurename
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['feature_codes'] = parse_mysql_result(result, [
            'modulename', 'featurename', 'description', 'defaultcode', 'enabled', 'customcode'
        ])
        
        print(f"   ✓ Found {len(self.data['feature_codes'])} enabled feature codes")
        
    def _collect_speed_dials(self):
        """Collect speed dial configurations."""
        print("🏃 Collecting Speed Dials...")
        
        query = """
        SELECT speeddial_id, description, speeddial
        FROM speeddials
        ORDER BY speeddial_id
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['speed_dials'] = parse_mysql_result(result, [
            'speeddial_id', 'description', 'speeddial'
        ])
        
        print(f"   ✓ Found {len(self.data['speed_dials'])} speed dials")
        
    def _collect_call_recording(self):
        """Collect call recording configurations."""
        print("🎬 Collecting Call Recording...")
        
        query = """
        SELECT displayname, callrecording_mode, dest
        FROM callrecording
        ORDER BY displayname
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['call_recording'] = parse_mysql_result(result, [
            'displayname', 'callrecording_mode', 'dest'
        ])
        
        print(f"   ✓ Found {len(self.data['call_recording'])} call recording configs")
        
    def _collect_modules(self):
        """Collect module status information."""
        print("🧩 Collecting Module Status...")
        
        query = """
        SELECT modulename, enabled, version, status
        FROM modules
        ORDER BY modulename
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['modules'] = parse_mysql_result(result, [
            'modulename', 'enabled', 'version', 'status'
        ])
        
        print(f"   ✓ Found {len(self.data['modules'])} module entries")
        
    def _collect_global_settings(self):
        """Collect global system settings."""
        print("🌐 Collecting Global Settings...")
        
        query = """
        SELECT keyword, data
        FROM globals
        WHERE keyword IN ('RINGTIMER', 'FOLLOWME_PREFIX', 'DIRECTORY_OPTS',
                         'AMPUSER', 'AMPMGRUSER', 'AMPMGRPASS', 'FOPPASSWORD',
                         'RECORD_IN', 'RECORD_OUT', 'MIXMON_POST', 'MIXMON_DIR')
        ORDER BY keyword
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['global_settings'] = parse_mysql_result(result, [
            'keyword', 'data'
        ])
        
        print(f"   ✓ Found {len(self.data['global_settings'])} global settings")
        
    def _collect_custom_extensions(self):
        """Collect custom dialplan extensions."""
        print("⚙️  Collecting Custom Extensions...")
        
        query = """
        SELECT context, exten, priority, app, appdata
        FROM extensions
        WHERE context IN ('from-internal-custom', 'macro-user-callerid-custom',
                         'app-blacklist-check-custom', 'ext-local-custom')
        ORDER BY context, exten, priority
        """
        
        result = run_mysql(query, self.socket, self.user, self.password)
        self.data['custom_extensions'] = parse_mysql_result(result, [
            'context', 'exten', 'priority', 'app', 'appdata'
        ])
        
        print(f"   ✓ Found {len(self.data['custom_extensions'])} custom extension entries")
        
    def _show_collection_summary(self):
        """Show comprehensive data collection summary."""
        print("\n" + "=" * 60)
        print("📊 COMPREHENSIVE DATA COLLECTION SUMMARY")
        print("=" * 60)
        
        categories = {
            "📞 ENTRY POINTS": [
                ('inbound_routes', 'Inbound Routes'),
                ('custom_contexts', 'Custom Contexts')
            ],
            "🎛️  ROUTING LOGIC": [
                ('time_conditions', 'Time Conditions'),
                ('ivr_menus', 'IVR Menus'),
                ('ivr_options', 'IVR Options'),
                ('call_flow_toggles', 'Call Flow Toggles')
            ],
            "🎯 DESTINATIONS": [
                ('extensions', 'Extensions'),
                ('queues', 'Queues'),
                ('queue_members', 'Queue Members'),
                ('ring_groups', 'Ring Groups'),
                ('voicemail_boxes', 'Voicemail Boxes'),
                ('conferences', 'Conferences')
            ],
            "🎵 ANNOUNCEMENTS & MEDIA": [
                ('announcements', 'Announcements'),
                ('music_on_hold', 'Music on Hold'),
                ('system_recordings', 'System Recordings')
            ],
            "🚀 ADVANCED FEATURES": [
                ('follow_me', 'Follow Me'),
                ('paging_groups', 'Paging Groups'),
                ('parking_lots', 'Parking Lots'),
                ('misc_destinations', 'Misc Destinations'),
                ('disa', 'DISA')
            ],
            "🛣️  OUTBOUND ROUTING": [
                ('outbound_routes', 'Outbound Routes'),
                ('trunks', 'Trunks')
            ],
            "🔗 RELATIONSHIPS": [
                ('feature_codes', 'Feature Codes'),
                ('speed_dials', 'Speed Dials'),
                ('call_recording', 'Call Recording')
            ],
            "⚙️  SYSTEM LEVEL": [
                ('modules', 'Modules'),
                ('global_settings', 'Global Settings'),
                ('custom_extensions', 'Custom Extensions')
            ]
        }
        
        total_items = 0
        for category, items in categories.items():
            print(f"\n{category}")
            for data_key, display_name in items:
                count = len(self.data[data_key])
                total_items += count
                status = "✓" if count > 0 else "○"
                print(f"  {status} {display_name}: {count}")
        
        print(f"\n🎯 TOTAL DATA COLLECTED: {total_items} configuration items")
        print("=" * 60)
        print("✅ Complete FreePBX call flow data collection finished!")
        print("📋 Ready for intelligent call flow analysis and ASCII diagram generation.")
        
    def print_collected_data(self, detailed=False):
        """Print collected data to console for testing and verification."""
        print("\n" + "=" * 80)
        print("📋 COLLECTED DATA DETAILED VIEW")
        print("=" * 80)
        
        categories = {
            "📞 ENTRY POINTS": [
                ('inbound_routes', 'Inbound Routes'),
                ('custom_contexts', 'Custom Contexts')
            ],
            "🎛️  ROUTING LOGIC": [
                ('time_conditions', 'Time Conditions'),
                ('ivr_menus', 'IVR Menus'),
                ('ivr_options', 'IVR Options'),
                ('call_flow_toggles', 'Call Flow Toggles')
            ],
            "🎯 DESTINATIONS": [
                ('extensions', 'Extensions'),
                ('queues', 'Queues'),
                ('queue_members', 'Queue Members'),
                ('ring_groups', 'Ring Groups'),
                ('voicemail_boxes', 'Voicemail Boxes'),
                ('conferences', 'Conferences')
            ],
            "🎵 ANNOUNCEMENTS & MEDIA": [
                ('announcements', 'Announcements'),
                ('music_on_hold', 'Music on Hold'),
                ('system_recordings', 'System Recordings')
            ],
            "🚀 ADVANCED FEATURES": [
                ('follow_me', 'Follow Me'),
                ('paging_groups', 'Paging Groups'),
                ('parking_lots', 'Parking Lots'),
                ('misc_destinations', 'Misc Destinations'),
                ('disa', 'DISA')
            ],
            "🛣️  OUTBOUND ROUTING": [
                ('outbound_routes', 'Outbound Routes'),
                ('trunks', 'Trunks')
            ],
            "🔗 RELATIONSHIPS": [
                ('feature_codes', 'Feature Codes'),
                ('speed_dials', 'Speed Dials'),
                ('call_recording', 'Call Recording')
            ],
            "⚙️  SYSTEM LEVEL": [
                ('modules', 'Modules'),
                ('global_settings', 'Global Settings'),
                ('custom_extensions', 'Custom Extensions')
            ]
        }
        
        for category, items in categories.items():
            print(f"\n{category}")
            print("-" * len(category))
            
            for data_key, display_name in items:
                data_list = self.data[data_key]
                count = len(data_list)
                
                if count == 0:
                    print(f"  ○ {display_name}: No data found")
                    continue
                    
                print(f"  ✓ {display_name}: {count} items")
                
                if detailed:
                    # Show detailed data for each item
                    for i, item in enumerate(data_list[:5]):  # Limit to first 5 items
                        print(f"    [{i+1}] {self._format_item_details(item, data_key)}")
                    
                    if count > 5:
                        print(f"    ... and {count - 5} more items")
                else:
                    # Show summary of first few items
                    for i, item in enumerate(data_list[:3]):  # Show first 3 items
                        summary = self._format_item_summary(item, data_key)
                        if summary:
                            print(f"    • {summary}")
                    
                    if count > 3:
                        print(f"    • ... and {count - 3} more")
                
                print()  # Add spacing between sections
        
        print("=" * 80)
        
    def _format_item_summary(self, item, data_type):
        """Format a single item for summary display."""
        try:
            if data_type == 'inbound_routes':
                return f"DID: {item.get('extension', 'N/A')} → {item.get('description', 'No description')} → {item.get('destination', 'No destination')}"
            
            elif data_type == 'time_conditions':
                return f"TC{item.get('timeconditions_id', 'N/A')}: {item.get('displayname', 'No name')} (True→{item.get('truegoto', 'N/A')}, False→{item.get('falsegoto', 'N/A')})"
            
            elif data_type == 'ivr_menus':
                return f"IVR{item.get('id', 'N/A')}: {item.get('displayname', 'No name')} (Announcement: {item.get('announcement', 'None')})"
            
            elif data_type == 'ivr_options':
                return f"IVR{item.get('ivr_id', 'N/A')} Key {item.get('selection', 'N/A')} → {item.get('dest', 'No destination')}"
            
            elif data_type == 'extensions':
                return f"Ext {item.get('extension', 'N/A')}: {item.get('name', 'No name')} (VM: {item.get('voicemail', 'No')})"
            
            elif data_type == 'queues':
                return f"Queue {item.get('extension', 'N/A')}: {item.get('description', 'No description')} (Strategy: {item.get('strategy', 'N/A')})"
            
            elif data_type == 'ring_groups':
                return f"RG {item.get('grpnum', 'N/A')}: {item.get('description', 'No description')} (Strategy: {item.get('strategy', 'N/A')})"
            
            elif data_type == 'announcements':
                return f"Ann {item.get('announcement_id', 'N/A')}: {item.get('description', 'No description')} (File: {item.get('filename', 'None')})"
            
            elif data_type == 'conferences':
                return f"Conf {item.get('exten', 'N/A')}: {item.get('description', 'No description')} (Max users: {item.get('users', 'Unlimited')})"
            
            elif data_type == 'voicemail_boxes':
                return f"VM {item.get('mailbox', 'N/A')}: {item.get('fullname', 'No name')} (Email: {item.get('email', 'None')})"
            
            elif data_type == 'outbound_routes':
                return f"Route: {item.get('name', 'No name')} (Emergency: {item.get('emergency_route', 'No')})"
            
            elif data_type == 'trunks':
                return f"Trunk: {item.get('name', 'No name')} ({item.get('tech', 'Unknown')} - {item.get('provider', 'No provider')})"
            
            elif data_type == 'feature_codes':
                code = item.get('customcode') or item.get('defaultcode', 'N/A')
                return f"{code}: {item.get('description', 'No description')} ({item.get('modulename', 'Unknown module')})"
            
            elif data_type == 'modules':
                status = "Enabled" if item.get('enabled') == '1' else "Disabled"
                return f"{item.get('modulename', 'Unknown')}: {status} (v{item.get('version', 'Unknown')})"
            
            elif data_type == 'global_settings':
                return f"{item.get('keyword', 'Unknown')}: {item.get('data', 'No value')}"
            
            else:
                # Generic formatting for other data types
                keys = list(item.keys())
                if len(keys) >= 2:
                    return f"{item.get(keys[0], 'N/A')}: {item.get(keys[1], 'No data')}"
                elif len(keys) >= 1:
                    return f"{item.get(keys[0], 'No data')}"
                else:
                    return "No data available"
                    
        except Exception as e:
            return f"Error formatting item: {e}"
    
    def _format_item_details(self, item, data_type):
        """Format a single item for detailed display."""
        try:
            details = []
            for key, value in item.items():
                if value and str(value).strip():  # Only show non-empty values
                    details.append(f"{key}={value}")
            
            return " | ".join(details[:5])  # Limit to first 5 fields to keep readable
            
        except Exception as e:
            return f"Error formatting details: {e}"

    def export_data(self, filename=None):
        """Export collected data to JSON file."""
        if not filename:
            timestamp = int(time.time())
            filename = f"freepbx_complete_data_{timestamp}.json"
            
        try:
            with open(filename, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
            print(f"\n💾 Data exported to: {filename}")
            return filename
        except Exception as e:
            print(f"\n❌ Export failed: {e}")
            return None

def main():
    """Main entry point for comprehensive FreePBX data collection."""
    parser = argparse.ArgumentParser(description="FreePBX Comprehensive Data Collector")
    parser.add_argument("--socket", default=DEFAULT_SOCK, help="MySQL socket path")
    parser.add_argument("--db-user", default="root", help="MySQL user")
    parser.add_argument("--db-password", help="MySQL password")
    parser.add_argument("--export", help="Export data to JSON file")
    parser.add_argument("--show-summary", action="store_true", help="Show detailed summary")
    
    args = parser.parse_args()
    
    print("🚀 FreePBX ASCII Call Flow Generator")
    print("Comprehensive Configuration Data Collector")
    print("=" * 60)
    
    # Initialize data collector
    collector = FreePBXDataCollector(
        socket=args.socket,
        user=args.db_user,
        password=args.db_password
    )
    
    # Collect all configuration data
    collector.collect_all_data()
    
    # Export data if requested
    if args.export:
        collector.export_data(args.export)
    
    print("\n✅ Comprehensive data collection complete!")
    print("🔄 Next: Use this data to generate intelligent ASCII call flow diagrams.")

if __name__ == "__main__":
    main()
