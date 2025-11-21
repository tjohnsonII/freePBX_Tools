#!/usr/bin/env python3
"""
FreePBX Call Flow Validation Tool
---------------------------------
Compare our tool's output with direct database queries and GUI behavior

VARIABLE MAP (Key Script Variables)
-----------------------------------
CallFlowValidator : Main class for call flow validation
host           : Database host
user           : Database username
password       : Database password
args           : Parsed command-line arguments (if any)
sql            : SQL query string
did            : DID number to validate
db_result      : Result from direct DB query
tool_result    : Result from call flow tool

Key Function Arguments:
-----------------------
sql            : SQL query string
did            : DID number to validate
args           : Parsed command-line arguments

See function docstrings for additional details on arguments and return values.

    FUNCTION MAP (Major Functions)
    -----------------------------
    CallFlowValidator.__init__    : Initialize validator with DB params
    CallFlowValidator.query_db     : Execute direct MySQL query
    CallFlowValidator.run_callflow_tool: Run call flow tool and parse output
    CallFlowValidator.compare_results  : Compare DB and tool results
    main                             : CLI entry point, parses args and runs validation
"""

import subprocess
import json
import sys
import re
from typing import Dict, List, Tuple

class CallFlowValidator:
    def __init__(self, host="localhost", user="root", password=None):
        self.host = host
        self.user = user
        self.password = password
        
    def query_db(self, sql):
        """Execute direct MySQL query"""
        cmd = ["mysql", "-h", self.host, "-u", self.user, "-NBe", sql, "asterisk"]
        if self.password:
            cmd.insert(-2, f"-p{self.password}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Database query failed: {e}")
            return ""
    
    def run_callflow_tool(self, did):
        """Run our call flow tool and parse output"""
        cmd = ["python3", "/usr/local/123net/freepbx-tools/bin/freepbx_version_aware_ascii_callflow.py", "--did", str(did)]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Call flow tool failed: {e}")
            return ""
    
    def validate_inbound_route(self, did):
        """Validate inbound route matches database"""
        print(f"\n🔍 VALIDATING DID: {did}")
        print("=" * 50)
        
        # Get data from our tool
        tool_output = self.run_callflow_tool(did)
        
        # Get data directly from database
        db_query = f"""
        SELECT extension, description, destination 
        FROM incoming 
        WHERE extension = '{did}'
        """
        db_result = self.query_db(db_query)
        
        if not db_result:
            print(f"❌ DID {did} not found in database")
            return False
            
        db_parts = db_result.split('\t')
        db_extension = db_parts[0] if len(db_parts) > 0 else ""
        db_description = db_parts[1] if len(db_parts) > 1 else ""
        db_destination = db_parts[2] if len(db_parts) > 2 else ""
        
        print(f"📊 DATABASE:")
        print(f"   Extension: {db_extension}")
        print(f"   Description: {db_description}")
        print(f"   Destination: {db_destination}")
        
        # Parse tool output
        tool_destination = ""
        tool_description = ""
        
        for line in tool_output.split('\n'):
            if "✓ Found route:" in line:
                tool_description = line.split("✓ Found route: ")[1].strip()
            elif "✓ Destination:" in line:
                tool_destination = line.split("✓ Destination: ")[1].strip()
        
        print(f"🔧 TOOL OUTPUT:")
        print(f"   Description: {tool_description}")
        print(f"   Destination: {tool_destination}")
        
        # Validate
        desc_match = db_description == tool_description
        dest_contains_raw = db_destination in tool_output
        
        print(f"\n✅ VALIDATION:")
        print(f"   Description Match: {'✓' if desc_match else '❌'}")
        print(f"   Raw Destination Found: {'✓' if dest_contains_raw else '❌'}")
        
        if not desc_match:
            print(f"   ⚠️  Description mismatch: DB='{db_description}' vs Tool='{tool_description}'")
        
        return desc_match and dest_contains_raw
    
    def validate_extension_resolution(self, ext_id):
        """Validate extension name resolution"""
        print(f"\n🔍 VALIDATING EXTENSION: {ext_id}")
        print("=" * 50)
        
        # Direct database query for extension
        db_query = f"""
        SELECT extension, name 
        FROM users 
        WHERE extension = '{ext_id}'
        """
        db_result = self.query_db(db_query)
        
        if db_result:
            db_parts = db_result.split('\t')
            db_ext = db_parts[0] if len(db_parts) > 0 else ""
            db_name = db_parts[1] if len(db_parts) > 1 else ""
            
            print(f"📊 DATABASE: Extension {db_ext} = '{db_name}'")
            return db_ext, db_name
        else:
            print(f"❌ Extension {ext_id} not found in database")
            return None, None
    
    def validate_time_condition(self, tc_id):
        """Validate time condition resolution"""
        print(f"\n🔍 VALIDATING TIME CONDITION: {tc_id}")
        print("=" * 50)
        
        # Direct database query
        db_query = f"""
        SELECT timeconditions_id, displayname, truegoto, falsegoto 
        FROM timeconditions 
        WHERE timeconditions_id = '{tc_id}'
        """
        db_result = self.query_db(db_query)
        
        if db_result:
            db_parts = db_result.split('\t')
            tc_id_db = db_parts[0] if len(db_parts) > 0 else ""
            tc_name = db_parts[1] if len(db_parts) > 1 else ""
            tc_true = db_parts[2] if len(db_parts) > 2 else ""
            tc_false = db_parts[3] if len(db_parts) > 3 else ""
            
            print(f"📊 DATABASE:")
            print(f"   ID: {tc_id_db}")
            print(f"   Name: '{tc_name}'")
            print(f"   True Goto: {tc_true}")
            print(f"   False Goto: {tc_false}")
            
            return tc_name, tc_true, tc_false
        else:
            print(f"❌ Time Condition {tc_id} not found")
            return None, None, None
    
    def run_comprehensive_test(self, test_dids):
        """Run comprehensive validation on multiple DIDs"""
        print("🚀 FreePBX Call Flow Accuracy Validation")
        print("=" * 70)
        
        passed = 0
        failed = 0
        
        for did in test_dids:
            try:
                if self.validate_inbound_route(did):
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ Error validating {did}: {e}")
                failed += 1
        
        print(f"\n📊 VALIDATION SUMMARY:")
        print(f"   Passed: {passed}")
        print(f"   Failed: {failed}")
        print(f"   Accuracy: {(passed/(passed+failed)*100):.1f}%" if (passed+failed) > 0 else "N/A")
        
        return passed, failed

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_callflows.py <DID1> [DID2] [DID3] ...")
        sys.exit(1)
    
    test_dids = sys.argv[1:]
    
    validator = CallFlowValidator()
    validator.run_comprehensive_test(test_dids)

if __name__ == "__main__":
    main()