# MySQL Database Access for FreePBX Tools

## Overview
**The FreePBX/Asterisk MySQL database is the single source of truth for all system configuration.** Every component—DIDs, extensions, ring groups, IVRs, time conditions, trunks—lives in the `asterisk` database. Reliable, consistent database access is the foundation of all FreePBX diagnostic tools.

## Critical Discovery: The Simple Approach Works Best

### The Problem We Solved
Initial implementations used complex MySQL authentication with explicit socket paths and user parameters:
```bash
mysql -BN --user root --socket /var/lib/mysql/mysql.sock asterisk -e "SELECT ..."
```

This approach failed because:
1. **Chicken-and-egg problem**: Need socket path to connect, need to connect to get socket path
2. **Over-engineering**: Root user already has socket authentication
3. **Fragile**: Different FreePBX versions have different socket locations
4. **Silent failures**: Complex commands fail without clear error messages

### The Solution: Match Manual Workflow
**When a human administrator accesses MySQL on FreePBX:**
```bash
[123net@pbx ~]$ su root
Password: 
[root@pbx 123net]# mysql
Welcome to the MariaDB monitor...
MariaDB [(none)]> USE asterisk;
MariaDB [asterisk]> SELECT COUNT(*) FROM timeconditions;
```

**Our scripts should do the exact same thing:**
```bash
mysql -NBe "SELECT COUNT(*) FROM timeconditions" asterisk
```

That's it. No socket parameters, no user flags, no complexity.

---

## The Working Pattern

### Basic Query (Python)
```python
import subprocess

def query_mysql(sql):
    """Execute SQL query against FreePBX asterisk database"""
    cmd = ["mysql", "-NBe", sql, "asterisk"]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=5
    )
    
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        # Log error for debugging
        print(f"MySQL Error: {result.stderr.strip()}")
        return None
```

### MySQL Flags Explained
- **`-N`**: Skip column names (no header row)
- **`-B`**: Batch mode (tab-separated output, no table formatting)
- **`-e`**: Execute the SQL statement and exit
- **`asterisk`**: Database name (always use this for FreePBX data)

### Example Queries

#### Count Time Conditions
```python
sql = "SELECT COUNT(*) FROM timeconditions"
cmd = ["mysql", "-NBe", sql, "asterisk"]
result = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)
count = int(result.stdout.strip())  # Returns: "3\n" → 3
```

#### Get Time Condition Details
```python
sql = "SELECT id, displayname, inuse_state FROM timeconditions ORDER BY displayname"
cmd = ["mysql", "-NBe", sql, "asterisk"]
result = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)

# Output format (tab-separated):
# 1	FNR	0
# 2	Midwest	0
# 3	ROI	1

for line in result.stdout.strip().split('\n'):
    tc_id, name, state = line.split('\t')
    # state: 0=auto, 1=forced ON, 2=forced OFF
```

#### Get Extension List
```python
sql = "SELECT extension, name FROM users ORDER BY CAST(extension AS UNSIGNED)"
cmd = ["mysql", "-NBe", sql, "asterisk"]
result = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)

for line in result.stdout.strip().split('\n'):
    ext, name = line.split('\t')
    print(f"Extension {ext}: {name}")
```

---

## Prerequisites

### 1. Root Access Required
**All scripts must run as root** because:
- MySQL socket authentication requires root privileges
- Asterisk CLI access requires root
- System service checks require root

**Implementation:**
```python
import os

def check_root():
    """Verify script is running as root"""
    try:
        if os.geteuid() != 0:
            print("⚠️  This tool requires root access to query the FreePBX database.")
            print("Please run: sudo freepbx-callflows")
            print("Or switch to root first: su root")
            sys.exit(1)
    except AttributeError:
        # Windows doesn't have geteuid, skip check
        pass
```

### 2. Workflow Pattern
**Standard user workflow:**
```bash
# Login as regular user (123net)
ssh 123net@pbx-server.example.com

# Switch to root
su root

# Now run FreePBX tools
freepbx-callflows
```

### 3. No Additional Configuration Needed
- No MySQL password files
- No socket detection logic
- No connection string parsing
- Root's socket authentication "just works"

---

## Key Database Tables

### Core Configuration Tables
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `timeconditions` | Time-based routing | `id`, `displayname`, `inuse_state` |
| `users` | Extensions/users | `extension`, `name`, `outboundcid` |
| `incoming` | Inbound routes (DIDs) | `cidnum` (DID), `description`, `destination` |
| `ringgroups` | Ring groups | `grpnum`, `description`, `grplist` |
| `queues` | Call queues | `id`, `descr`, `member` |
| `ivr_details` | IVR menus | `id`, `name`, `timeout` |
| `ivr_entries` | IVR options | `ivr_id`, `selection`, `dest` |
| `trunks` | Outbound trunks | `trunkid`, `name`, `channelid` |
| `outbound_routes` | Outbound routing | `route_id`, `name`, `seq` |

### State Codes Reference

#### Time Condition `inuse_state`
- `0` = Auto (following schedule)
- `1` = Forced ON (override to "true" state)
- `2` = Forced OFF (override to "false" state)

#### Destination Format
Destinations follow pattern: `<type>,<id>,<action>`
- `ext-group,1,` = Ring group 1
- `ivr-1,s,1` = IVR menu 1
- `ext-queues,1,` = Queue 1
- `ext-local,7140,1` = Extension 7140
- `app-blackhole,hangup,1` = Hangup/terminate

---

## Error Handling Best Practices

### 1. Always Check Return Code
```python
result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=5)

if result.returncode != 0:
    error_msg = result.stderr.strip()
    print(f"MySQL query failed: {error_msg}")
    return None  # or default value
```

### 2. Handle Empty Results
```python
if not result.stdout.strip():
    # No rows returned - this is valid for empty tables
    return []
```

### 3. Catch Exceptions
```python
try:
    result = subprocess.run(cmd, ..., timeout=5)
except subprocess.TimeoutExpired:
    print("MySQL query timed out (>5s)")
    return None
except Exception as e:
    print(f"Unexpected error: {str(e)}")
    return None
```

### 4. Validate Data Types
```python
# When expecting numeric data
try:
    count = int(result.stdout.strip())
except ValueError:
    print(f"Expected number, got: {result.stdout}")
    count = 0
```

---

## Common Pitfalls to Avoid

### ❌ Don't: Overcomplicate Authentication
```python
# WRONG - unnecessary complexity
cmd = ["mysql", "-BN", "--user", "root", "--socket", sock, 
       "--password", pwd, "asterisk", "-e", sql]
```

### ✅ Do: Keep It Simple
```python
# RIGHT - matches manual workflow
cmd = ["mysql", "-NBe", sql, "asterisk"]
```

### ❌ Don't: Detect Socket Path Dynamically
```python
# WRONG - causes chicken-and-egg problem
def detect_socket():
    result = subprocess.run(["mysql", "-NBe", "SHOW VARIABLES LIKE 'socket'"])
    # This fails if you can't connect without knowing the socket!
```

### ✅ Do: Trust Root Authentication
```python
# RIGHT - root user has socket auth by default
# No socket detection needed
```

### ❌ Don't: Parse MySQL Output Manually
```python
# WRONG - fragile parsing
output = result.stdout
lines = output.split('\n')
header = lines[0]  # Assumes header exists
data = lines[1:]   # Breaks if -N flag used
```

### ✅ Do: Use -N Flag and Split on Tabs
```python
# RIGHT - clean, predictable format
for line in result.stdout.strip().split('\n'):
    fields = line.split('\t')  # Tab-separated values
```

---

## Testing Database Access

### Quick Verification Script
```python
#!/usr/bin/env python3
"""Test MySQL connectivity for FreePBX tools"""

import subprocess
import sys

def test_mysql():
    """Verify we can query the asterisk database"""
    tests = [
        ("Time Conditions", "SELECT COUNT(*) FROM timeconditions"),
        ("Extensions", "SELECT COUNT(*) FROM users"),
        ("Inbound Routes", "SELECT COUNT(*) FROM incoming"),
        ("Ring Groups", "SELECT COUNT(*) FROM ringgroups"),
        ("Queues", "SELECT COUNT(*) FROM queues"),
    ]
    
    print("Testing MySQL Database Access...")
    print("-" * 50)
    
    for name, sql in tests:
        cmd = ["mysql", "-NBe", sql, "asterisk"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True, timeout=5)
        
        if result.returncode == 0:
            count = result.stdout.strip()
            print(f"✓ {name:20} {count:>5} records")
        else:
            print(f"✗ {name:20} FAILED: {result.stderr.strip()}")
            return False
    
    print("-" * 50)
    print("✓ All database tests passed!")
    return True

if __name__ == "__main__":
    if not test_mysql():
        sys.exit(1)
```

**Run test:**
```bash
su root
python3 test_mysql.py
```

---

## Performance Considerations

### Query Timeouts
Always set reasonable timeouts (5 seconds is usually sufficient):
```python
result = subprocess.run(cmd, ..., timeout=5)
```

### Batch Queries
For multiple related queries, consider:
1. **JOIN instead of multiple queries** when possible
2. **Temporary tables** for complex analysis
3. **Single query with multiple counts** using UNION

### Example: Combined Count Query
```python
sql = """
SELECT 'timeconditions' as table_name, COUNT(*) as count FROM timeconditions
UNION ALL
SELECT 'users', COUNT(*) FROM users
UNION ALL
SELECT 'incoming', COUNT(*) FROM incoming
"""
cmd = ["mysql", "-NBe", sql, "asterisk"]
# Returns all counts in one query
```

---

## Security Notes

1. **Root requirement is intentional** - FreePBX administration requires elevated privileges
2. **No password storage** - uses socket authentication only
3. **SQL injection protection** - always validate/sanitize user input if building dynamic queries
4. **Audit logging** - MySQL logs all queries in `/var/log/mysql/` or `/var/lib/mysql/<host>.log`

---

## Troubleshooting

### Problem: "Access denied for user"
**Cause:** Not running as root
**Solution:** Run `su root` before executing scripts

### Problem: "Can't connect to local MySQL server"
**Cause:** MySQL/MariaDB service not running
**Solution:** 
```bash
systemctl status mariadb
systemctl start mariadb
```

### Problem: "Unknown database 'asterisk'"
**Cause:** Not a FreePBX system, or database not initialized
**Solution:** Verify FreePBX installation

### Problem: "Table doesn't exist"
**Cause:** FreePBX version differences or missing module
**Solution:** Check table existence first:
```python
sql = "SHOW TABLES LIKE 'timeconditions'"
result = subprocess.run(["mysql", "-NBe", sql, "asterisk"], ...)
if not result.stdout.strip():
    print("Time Conditions module not installed")
```

---

## Best Practices Summary

1. ✅ **Run as root** - check with `os.geteuid()`
2. ✅ **Simple commands** - `mysql -NBe "SQL" asterisk`
3. ✅ **Always timeout** - prevent hung scripts
4. ✅ **Check return codes** - detect failures
5. ✅ **Handle empty results** - valid state
6. ✅ **Tab-separated parsing** - use `-N` and `split('\t')`
7. ✅ **Validate data types** - expect integers, strings, nulls
8. ✅ **Log errors** - for debugging and auditing

---

## Next Steps: Log Analysis

The database provides **configuration state**. For **runtime behavior and issues**, we need to analyze logs:

### Key Log Locations (see LOG_ANALYSIS.md)
- `/var/log/asterisk/full` - Full Asterisk event log
- `/var/log/asterisk/messages` - Summary messages
- `/var/log/asterisk/queue_log` - Queue performance data
- `/var/log/asterisk/cdr-csv/Master.csv` - Call detail records
- `/var/log/httpd/error_log` - FreePBX web interface errors
- `/var/log/fail2ban.log` - Security/intrusion attempts

**Database = What is configured**  
**Logs = What actually happened**

Both are essential for complete system diagnostics.
