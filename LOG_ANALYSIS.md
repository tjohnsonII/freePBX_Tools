# FreePBX/Asterisk Log Analysis Guide

## Overview
While the MySQL database tells us **what is configured**, the log files tell us **what actually happened**. Logs are critical for diagnosing runtime issues, call failures, performance problems, and security threats.

## Critical Log Files

### Primary Logs

#### 1. `/var/log/asterisk/full`
**Purpose:** Complete Asterisk event log with all verbosity levels  
**Size:** Can grow to gigabytes (often 500MB - 5GB)  
**Rotation:** Daily or by size (logrotate)  
**Critical for:** Call flow debugging, dial plan execution, error tracking

**Format:**
```
[2025-11-06 14:23:45] VERBOSE[12345] pbx.c: Executing [s@from-internal:1] Set("PJSIP/7140-00000001", "CALLERID(number)=7140")
[2025-11-06 14:23:45] WARNING[12345] chan_pjsip.c: Request 'PJSIP/7141' has no extension
[2025-11-06 14:23:46] ERROR[12345] res_pjsip_session.c: Failed to create outgoing session to endpoint '7141'
```

**Log Levels:**
- `VERBOSE` - Normal operation (most common)
- `NOTICE` - Significant events (calls, hangups)
- `WARNING` - Potential issues (retries, deprecated features)
- `ERROR` - Failures (failed calls, config errors)
- `CRITICAL` - System failures (rarely seen)

---

#### 2. `/var/log/asterisk/messages`
**Purpose:** Summarized messages without verbose call details  
**Size:** Smaller than full log (50-500MB typical)  
**Rotation:** Daily  
**Critical for:** High-level overview, service status, reload events

**What to look for:**
- Asterisk start/stop/reload events
- Module load failures
- Database connection issues
- Trunk registration failures

---

#### 3. `/var/log/asterisk/queue_log`
**Purpose:** Call queue performance metrics  
**Size:** Moderate (10-200MB)  
**Format:** Pipe-delimited CSV  
**Critical for:** Queue performance analysis, agent metrics, abandoned calls

**Format:**
```
1699286234|1699286234.123|8000|NONE|ENTERQUEUE||7145|1
1699286240|1699286234.123|8000|7140|CONNECT|6|1699286234.124|3
1699286265|1699286234.123|8000|7140|COMPLETECALLER|6|25|1
```

**Fields:** `timestamp|unique_id|queue|agent|event|data1|data2|data3`

**Key Events:**
- `ENTERQUEUE` - Caller enters queue
- `CONNECT` - Agent answers
- `ABANDON` - Caller hangs up while waiting
- `COMPLETECALLER` - Caller hangs up after connection
- `COMPLETEAGENT` - Agent hangs up
- `EXITWITHTIMEOUT` - Queue timeout reached

---

#### 4. `/var/log/asterisk/cdr-csv/Master.csv`
**Purpose:** Call Detail Records (CDR) - billing and call history  
**Size:** Can be very large (1GB+)  
**Rotation:** Often disabled (just keeps growing)  
**Critical for:** Call volume analysis, cost tracking, historical trends

**Format (CSV):**
```
"accountcode","src","dst","dcontext","clid","channel","dstchannel","lastapp","lastdata","start","answer","end","duration","billsec","disposition","amaflags","uniqueid"
"","7140","18005551234","from-internal","7140","PJSIP/7140-00000001","PJSIP/trunk-00000002","Dial","PJSIP/trunk/18005551234","2025-11-06 14:23:45","2025-11-06 14:23:48","2025-11-06 14:25:12","87","84","ANSWERED","3","1699286625.123"
```

**Key Fields:**
- `src` - Calling party (extension or external number)
- `dst` - Destination dialed
- `duration` - Total call duration (seconds)
- `billsec` - Billable duration (after answer, seconds)
- `disposition` - Call outcome: `ANSWERED`, `NO ANSWER`, `BUSY`, `FAILED`

---

#### 5. `/var/log/httpd/error_log` (or `/var/log/apache2/error_log`)
**Purpose:** FreePBX web interface errors  
**Size:** Moderate (10-100MB)  
**Critical for:** GUI issues, PHP errors, permission problems

**What to look for:**
- PHP fatal errors
- Database connection failures
- Permission denied errors
- Module load failures

---

#### 6. `/var/log/fail2ban.log`
**Purpose:** Security - blocked IPs, attack attempts  
**Size:** Small to moderate (5-50MB)  
**Critical for:** Security monitoring, SIP scanner detection

**What to look for:**
- Ban/unban events
- Repeated authentication failures
- Attack patterns

**Example:**
```
2025-11-06 14:30:12 fail2ban.actions [12345]: NOTICE [asterisk] Ban 192.168.1.100
2025-11-06 14:30:15 fail2ban.filter  [12345]: INFO [asterisk] Found 192.168.1.100 - 2025-11-06 14:30:15
```

---

## Log Analysis Strategies

### 1. Real-Time Monitoring

#### Watch Active Calls
```bash
tail -f /var/log/asterisk/full | grep --color -E 'Executing|NOTICE|WARNING|ERROR'
```

#### Monitor Specific Extension
```bash
tail -f /var/log/asterisk/full | grep 'PJSIP/7140'
```

#### Watch Queue Activity
```bash
tail -f /var/log/asterisk/queue_log
```

#### Monitor Trunk Status
```bash
tail -f /var/log/asterisk/full | grep -E 'trunk|Registration|qualify'
```

---

### 2. Error Detection

#### Find All Errors in Last Hour
```bash
awk -v cutoff="$(date -d '1 hour ago' '+%Y-%m-%d %H:%M:%S')" \
  '$0 > "["cutoff {print}' /var/log/asterisk/full | grep ERROR
```

#### Most Common Error Messages
```bash
grep ERROR /var/log/asterisk/full | \
  sed 's/\[.*\]//' | \
  sort | uniq -c | sort -rn | head -20
```

#### Failed Call Attempts
```bash
grep "Failed to create outgoing session" /var/log/asterisk/full | tail -50
```

#### Database Connection Issues
```bash
grep -E "database|mysql|connection.*fail" /var/log/asterisk/full -i | tail -50
```

---

### 3. Call Flow Analysis

#### Trace Specific Call by Unique ID
```bash
# Get unique ID from CDR or active calls
CALL_ID="1699286625.123"
grep "$CALL_ID" /var/log/asterisk/full
```

#### Find Calls to Specific DID
```bash
grep "Set.*DID.*8005551234" /var/log/asterisk/full | tail -20
```

#### Track Call Through Time Condition
```bash
grep "timeconditions" /var/log/asterisk/full | tail -50
```

#### See IVR Navigation
```bash
grep -E "IVR|DTMF|Playback.*ivr" /var/log/asterisk/full | tail -100
```

---

### 4. Performance Analysis

#### Queue Wait Times (from queue_log)
```bash
# Average wait time before answer
awk -F'|' '$5=="CONNECT" {sum+=$6; count++} END {print "Avg wait:", sum/count, "seconds"}' \
  /var/log/asterisk/queue_log
```

#### Abandoned Call Rate
```bash
# Percentage of abandoned calls
awk -F'|' '$5=="ENTERQUEUE" {enter++} $5=="ABANDON" {abandon++} \
  END {print "Abandon rate:", (abandon/enter)*100 "%"}' \
  /var/log/asterisk/queue_log
```

#### Call Volume by Hour (from CDR)
```bash
awk -F',' '{print $10}' /var/log/asterisk/cdr-csv/Master.csv | \
  cut -d' ' -f2 | cut -d: -f1 | sort | uniq -c
```

#### Average Call Duration
```bash
awk -F',' '$14 > 0 {sum+=$14; count++} END {print "Avg duration:", sum/count, "seconds"}' \
  /var/log/asterisk/cdr-csv/Master.csv
```

---

### 5. Trunk Analysis

#### Trunk Registration Status
```bash
grep -E "Registration|qualify.*trunk" /var/log/asterisk/full | tail -50
```

#### Trunk Failures
```bash
grep -E "trunk.*CHANUNAVAIL|trunk.*CONGESTION" /var/log/asterisk/full | tail -50
```

#### Outbound Call Failures by Trunk
```bash
grep "Dial.*trunk" /var/log/asterisk/full | grep -E "CHANUNAVAIL|CONGESTION" | \
  sed 's/.*trunk-/trunk-/' | cut -d' ' -f1 | sort | uniq -c | sort -rn
```

---

## Key Indicators of Problems

### 🔴 Critical Issues

#### 1. Database Connection Failures
**Pattern:** `Failed to connect to database` or `MySQL server has gone away`  
**Impact:** FreePBX cannot read configuration, calls may fail  
**Log location:** `/var/log/asterisk/full`, `/var/log/httpd/error_log`  
**Query:**
```bash
grep -i "database.*fail\|mysql.*error" /var/log/asterisk/full | tail -20
```

---

#### 2. Trunk Down / No Registration
**Pattern:** `Registration.*failed` or `qualify: Endpoint.*is now Unreachable`  
**Impact:** Cannot make/receive calls via trunk  
**Log location:** `/var/log/asterisk/full`  
**Query:**
```bash
grep -E "Registration.*failed|qualify.*Unreachable|trunk.*unavailable" \
  /var/log/asterisk/full | tail -50
```

---

#### 3. High Abandoned Call Rate
**Pattern:** Many `ABANDON` events in queue_log  
**Impact:** Customers hanging up before reaching agent  
**Log location:** `/var/log/asterisk/queue_log`  
**Query:**
```bash
# Last 100 queue events - count abandons
tail -100 /var/log/asterisk/queue_log | grep -c ABANDON
```

---

#### 4. Repeated Authentication Failures
**Pattern:** `NOTICE.*failed to authenticate` or `SECURITY.*failed authentication`  
**Impact:** Possible brute force attack, or misconfigured device  
**Log location:** `/var/log/asterisk/full`, `/var/log/fail2ban.log`  
**Query:**
```bash
grep -i "failed.*auth\|SECURITY" /var/log/asterisk/full | tail -50
```

---

### 🟡 Warning Signs

#### 1. High Channel Usage
**Pattern:** Many active channels near system limit  
**Impact:** New calls may be rejected  
**Query via Asterisk CLI:**
```bash
asterisk -rx "core show channels count"
```

---

#### 2. Codec Negotiation Failures
**Pattern:** `Unable to negotiate codec` or `no compatible formats`  
**Impact:** Calls fail with "fast busy" or immediate hangup  
**Log location:** `/var/log/asterisk/full`  
**Query:**
```bash
grep -i "codec.*negotiat\|no compatible format" /var/log/asterisk/full | tail -20
```

---

#### 3. Long Queue Wait Times
**Pattern:** `CONNECT` events with high wait time field  
**Impact:** Poor customer experience  
**Query:**
```bash
# Show connections with >60 second wait
awk -F'|' '$5=="CONNECT" && $6>60 {print $1, $3, $6}' \
  /var/log/asterisk/queue_log | tail -20
```

---

#### 4. Voicemail Storage Issues
**Pattern:** `Failed to create voicemail` or `disk full`  
**Impact:** Voicemail may not save  
**Query:**
```bash
grep -i "voicemail.*fail\|disk.*full\|no space left" /var/log/asterisk/full | tail -20
```

---

## Automated Log Parser Script

### Python Implementation

```python
#!/usr/bin/env python3
"""
FreePBX Log Analyzer - Automated issue detection
"""

import re
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict

class LogAnalyzer:
    def __init__(self):
        self.full_log = "/var/log/asterisk/full"
        self.queue_log = "/var/log/asterisk/queue_log"
        self.cdr_log = "/var/log/asterisk/cdr-csv/Master.csv"
        self.issues = []
        
    def analyze_last_n_hours(self, hours=1):
        """Analyze logs from last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"🔍 Analyzing logs since {cutoff_str}")
        print("=" * 60)
        
        self.check_errors(hours)
        self.check_trunk_status()
        self.check_queue_performance()
        self.check_security_events()
        self.check_database_issues()
        
        return self.issues
    
    def check_errors(self, hours):
        """Count errors and warnings"""
        cmd = f"grep -E 'ERROR|CRITICAL' {self.full_log} | tail -1000"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        errors = result.stdout.strip().split('\n') if result.stdout.strip() else []
        error_count = len([e for e in errors if e])
        
        if error_count > 10:
            self.issues.append({
                "severity": "HIGH",
                "category": "Errors",
                "message": f"Found {error_count} errors in last {hours}h",
                "details": errors[-10:]  # Last 10 errors
            })
        
        # Count by type
        error_types = defaultdict(int)
        for line in errors:
            if line:
                # Extract error message (simplified)
                match = re.search(r'(ERROR|CRITICAL).*?:\s*(.+?)$', line)
                if match:
                    error_msg = match.group(2)[:80]  # First 80 chars
                    error_types[error_msg] += 1
        
        if error_types:
            print("\n📊 Error Summary:")
            for msg, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {count:>4}x {msg}")
    
    def check_trunk_status(self):
        """Check trunk registration and failures"""
        cmd = f"grep -E 'trunk.*Unreachable|Registration.*failed' {self.full_log} | tail -20"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.stdout.strip():
            trunk_issues = result.stdout.strip().split('\n')
            self.issues.append({
                "severity": "CRITICAL",
                "category": "Trunk",
                "message": f"Trunk connectivity issues detected",
                "details": trunk_issues
            })
            print("\n🔴 TRUNK ISSUES DETECTED:")
            for issue in trunk_issues[-5:]:
                print(f"  {issue}")
    
    def check_queue_performance(self):
        """Analyze queue metrics"""
        if not os.path.exists(self.queue_log):
            return
        
        cmd = f"tail -500 {self.queue_log}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        enters = 0
        abandons = 0
        connects = 0
        wait_times = []
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|')
            if len(parts) < 6:
                continue
            
            event = parts[4]
            if event == "ENTERQUEUE":
                enters += 1
            elif event == "ABANDON":
                abandons += 1
            elif event == "CONNECT":
                connects += 1
                try:
                    wait_time = int(parts[5])
                    wait_times.append(wait_time)
                except (ValueError, IndexError):
                    pass
        
        if enters > 0:
            abandon_rate = (abandons / enters) * 100
            avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
            
            print(f"\n📞 Queue Performance (last 500 events):")
            print(f"  Calls entered: {enters}")
            print(f"  Answered:      {connects} ({(connects/enters)*100:.1f}%)")
            print(f"  Abandoned:     {abandons} ({abandon_rate:.1f}%)")
            print(f"  Avg wait time: {avg_wait:.1f}s")
            
            if abandon_rate > 20:
                self.issues.append({
                    "severity": "HIGH",
                    "category": "Queue",
                    "message": f"High abandon rate: {abandon_rate:.1f}%",
                    "details": [f"Abandons: {abandons}/{enters}"]
                })
            
            if avg_wait > 60:
                self.issues.append({
                    "severity": "MEDIUM",
                    "category": "Queue",
                    "message": f"Long average wait time: {avg_wait:.1f}s",
                    "details": [f"Average: {avg_wait:.1f}s, Max: {max(wait_times) if wait_times else 0}s"]
                })
    
    def check_security_events(self):
        """Check for authentication failures and attacks"""
        cmd = f"grep -i 'failed.*auth\\|SECURITY' {self.full_log} | tail -100"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.stdout.strip():
            security_events = result.stdout.strip().split('\n')
            
            # Extract IPs
            ips = defaultdict(int)
            for line in security_events:
                ip_match = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', line)
                if ip_match:
                    ips[ip_match.group(0)] += 1
            
            if len(security_events) > 20:
                self.issues.append({
                    "severity": "HIGH",
                    "category": "Security",
                    "message": f"Multiple authentication failures: {len(security_events)}",
                    "details": [f"{ip}: {count} attempts" for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:10]]
                })
                print("\n🔒 Security Events:")
                for ip, count in sorted(ips.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  {ip}: {count} failed attempts")
    
    def check_database_issues(self):
        """Check for database connection problems"""
        cmd = f"grep -i 'database.*fail\\|mysql.*error\\|mysql.*gone away' {self.full_log} | tail -20"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.stdout.strip():
            db_issues = result.stdout.strip().split('\n')
            self.issues.append({
                "severity": "CRITICAL",
                "category": "Database",
                "message": "Database connectivity issues",
                "details": db_issues
            })
            print("\n🔴 DATABASE ISSUES:")
            for issue in db_issues[-5:]:
                print(f"  {issue}")
    
    def print_summary(self):
        """Print issue summary"""
        if not self.issues:
            print("\n✅ No significant issues detected!")
            return
        
        print("\n" + "=" * 60)
        print("📋 ISSUES SUMMARY")
        print("=" * 60)
        
        critical = [i for i in self.issues if i["severity"] == "CRITICAL"]
        high = [i for i in self.issues if i["severity"] == "HIGH"]
        medium = [i for i in self.issues if i["severity"] == "MEDIUM"]
        
        if critical:
            print(f"\n🔴 CRITICAL ({len(critical)}):")
            for issue in critical:
                print(f"  • [{issue['category']}] {issue['message']}")
        
        if high:
            print(f"\n🟠 HIGH ({len(high)}):")
            for issue in high:
                print(f"  • [{issue['category']}] {issue['message']}")
        
        if medium:
            print(f"\n🟡 MEDIUM ({len(medium)}):")
            for issue in medium:
                print(f"  • [{issue['category']}] {issue['message']}")


if __name__ == "__main__":
    import os
    import sys
    
    # Check root
    if os.geteuid() != 0:
        print("⚠️  This tool requires root access")
        sys.exit(1)
    
    analyzer = LogAnalyzer()
    analyzer.analyze_last_n_hours(hours=1)
    analyzer.print_summary()
```

---

## Integration with Dashboard

### Add to freepbx_callflow_menu.py

```python
def run_log_analysis(hours=1):
    """Run automated log analysis"""
    analyzer_script = "/usr/local/123net/freepbx-tools/bin/freepbx_log_analyzer.py"
    
    if not os.path.isfile(analyzer_script):
        print("Log analyzer not found at", analyzer_script)
        return
    
    print(f"\n🔍 Running log analysis (last {hours} hour(s))...")
    print("=" * 60)
    
    cmd = ["python3", analyzer_script, str(hours)]
    rc, out, err = run(cmd)
    
    if rc == 0:
        print(out)
    else:
        print("Error running analysis:")
        print(err or out)
    
    print("\n" + Colors.YELLOW + "Press ENTER to continue..." + Colors.RESET)
    input()
```

---

## Next Steps

1. **Deploy log analyzer script** to production servers
2. **Add to menu** as option #14
3. **Schedule automated runs** via cron for daily summaries
4. **Set up alerting** for critical issues
5. **Build trend dashboard** showing issue history over time

**Database queries tell us configuration. Log analysis tells us reality.**
