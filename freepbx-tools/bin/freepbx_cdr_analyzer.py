#!/usr/bin/env python3
"""
FreePBX CDR/CEL Call Log Analyzer
Comprehensive analysis of Call Detail Records and Channel Event Logs
Provides call statistics, quality metrics, and billing data
"""

import os
import sys
import subprocess
import re
from datetime import datetime, timedelta
from collections import defaultdict
import json

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    BLUE = '\033[94m'


class TeeOutput:
    """Write to both terminal and file simultaneously"""
    def __init__(self, file_handle):
        self.terminal = sys.stdout
        self.file = file_handle
        
    def write(self, message):
        self.terminal.write(message)
        self.file.write(message)
        
    def flush(self):
        self.terminal.flush()
        self.file.flush()


class CDRAnalyzer:
    def __init__(self, db_user="root", db_socket="/var/lib/mysql/mysql.sock"):
        self.db_user = db_user
        self.db_socket = db_socket
        self.db_name = "asteriskcdrdb"
        
    def query_db(self, sql):
        """Execute SQL query against CDR database"""
        try:
            cmd = [
                "mysql",
                "-u", self.db_user,
                "-S", self.db_socket,
                "-NBe", sql,
                self.db_name
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                universal_newlines=True,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"{Colors.RED}❌ Database query failed: {result.stderr}{Colors.RESET}")
                return []
            
            if not result.stdout.strip():
                return []
            
            return result.stdout.strip().split('\n')
            
        except Exception as e:
            print(f"{Colors.RED}❌ Query error: {str(e)}{Colors.RESET}")
            return []
    
    def get_call_statistics(self, hours=24):
        """Get comprehensive call statistics"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}") 
        print(f"  📊 CALL STATISTICS (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Total calls
        sql = f"""
        SELECT 
            COUNT(*) as total_calls,
            SUM(CASE WHEN disposition = 'ANSWERED' THEN 1 ELSE 0 END) as answered,
            SUM(CASE WHEN disposition = 'NO ANSWER' THEN 1 ELSE 0 END) as no_answer,
            SUM(CASE WHEN disposition = 'BUSY' THEN 1 ELSE 0 END) as busy,
            SUM(CASE WHEN disposition = 'FAILED' THEN 1 ELSE 0 END) as failed,
            SUM(duration) as total_duration,
            SUM(billsec) as total_billsec,
            AVG(duration) as avg_duration,
            AVG(billsec) as avg_billsec
        FROM cdr
        WHERE calldate >= '{cutoff}'
        """
        
        result = self.query_db(sql)
        if result:
            data = result[0].split('\t')
            total = int(data[0]) if data[0] and data[0] != 'NULL' else 0
            answered = int(data[1]) if data[1] and data[1] != 'NULL' else 0
            no_answer = int(data[2]) if data[2] and data[2] != 'NULL' else 0
            busy = int(data[3]) if data[3] and data[3] != 'NULL' else 0
            failed = int(data[4]) if data[4] and data[4] != 'NULL' else 0
            total_duration = int(float(data[5])) if data[5] and data[5] != 'NULL' else 0
            total_billsec = int(float(data[6])) if data[6] and data[6] != 'NULL' else 0
            avg_duration = float(data[7]) if data[7] and data[7] != 'NULL' else 0
            avg_billsec = float(data[8]) if data[8] and data[8] != 'NULL' else 0
            
            answer_rate = (answered / total * 100) if total > 0 else 0
            
            print(f"{Colors.WHITE}Total Calls:{Colors.RESET}      {Colors.BOLD}{Colors.CYAN}{total:,}{Colors.RESET}")
            print(f"{Colors.WHITE}Answered:{Colors.RESET}         {Colors.GREEN}{answered:,}{Colors.RESET} ({answer_rate:.1f}%)")
            print(f"{Colors.WHITE}No Answer:{Colors.RESET}        {Colors.YELLOW}{no_answer:,}{Colors.RESET}")
            print(f"{Colors.WHITE}Busy:{Colors.RESET}             {Colors.YELLOW}{busy:,}{Colors.RESET}")
            print(f"{Colors.WHITE}Failed:{Colors.RESET}           {Colors.RED}{failed:,}{Colors.RESET}")
            print()
            print(f"{Colors.WHITE}Total Duration:{Colors.RESET}   {self.format_duration(total_duration)}")
            print(f"{Colors.WHITE}Billable Time:{Colors.RESET}    {self.format_duration(total_billsec)}")
            print(f"{Colors.WHITE}Avg Call Length:{Colors.RESET}  {self.format_duration(int(avg_billsec))}")
    
    def format_duration(self, seconds):
        """Format seconds into readable duration"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{Colors.BOLD}{hours}h {minutes}m {secs}s{Colors.RESET}"
        elif minutes > 0:
            return f"{Colors.BOLD}{minutes}m {secs}s{Colors.RESET}"
        else:
            return f"{Colors.BOLD}{secs}s{Colors.RESET}"
    
    def get_top_callers(self, hours=24, limit=10):
        """Get top callers by volume"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}")
        print(f"  📞 TOP {limit} CALLERS (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            src,
            COUNT(*) as call_count,
            SUM(duration) as total_duration,
            SUM(CASE WHEN disposition = 'ANSWERED' THEN 1 ELSE 0 END) as answered
        FROM cdr
        WHERE calldate >= '{cutoff}' AND src != ''
        GROUP BY src
        ORDER BY call_count DESC
        LIMIT {limit}
        """
        
        results = self.query_db(sql)
        if results:
            print(f"{Colors.WHITE}{'Caller':<15} {'Calls':<8} {'Answered':<10} {'Duration':<12}{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*50}{Colors.RESET}")
            
            for row in results:
                data = row.split('\t')
                caller = data[0]
                calls = int(data[1])
                duration = int(float(data[2]))
                answered = int(data[3])
                answer_rate = (answered / calls * 100) if calls > 0 else 0
                
                print(f"{Colors.GREEN}{caller:<15}{Colors.RESET} {calls:<8} {answered:<4} ({answer_rate:>4.0f}%)  {self.format_duration(duration)}")
    
    def get_top_destinations(self, hours=24, limit=10):
        """Get top called destinations"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}")
        print(f"  🎯 TOP {limit} DESTINATIONS (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            dst,
            COUNT(*) as call_count,
            SUM(duration) as total_duration,
            SUM(CASE WHEN disposition = 'ANSWERED' THEN 1 ELSE 0 END) as answered
        FROM cdr
        WHERE calldate >= '{cutoff}' AND dst != ''
        GROUP BY dst
        ORDER BY call_count DESC
        LIMIT {limit}
        """
        
        results = self.query_db(sql)
        if results:
            print(f"{Colors.WHITE}{'Destination':<15} {'Calls':<8} {'Answered':<10} {'Duration':<12}{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*50}{Colors.RESET}")
            
            for row in results:
                data = row.split('\t')
                dst = data[0]
                calls = int(data[1])
                duration = int(float(data[2]))
                answered = int(data[3])
                answer_rate = (answered / calls * 100) if calls > 0 else 0
                
                print(f"{Colors.MAGENTA}{dst:<15}{Colors.RESET} {calls:<8} {answered:<4} ({answer_rate:>4.0f}%)  {self.format_duration(duration)}")
    
    def get_call_by_hour(self, hours=24):
        """Get call distribution by hour of day"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}")
        print(f"  ⏰ CALL DISTRIBUTION BY HOUR (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            HOUR(calldate) as hour,
            COUNT(*) as call_count,
            SUM(CASE WHEN disposition = 'ANSWERED' THEN 1 ELSE 0 END) as answered
        FROM cdr
        WHERE calldate >= '{cutoff}'
        GROUP BY hour
        ORDER BY hour
        """
        
        results = self.query_db(sql)
        if results:
            max_calls = 0
            hour_data = {}
            
            for row in results:
                data = row.split('\t')
                hour = int(data[0])
                calls = int(data[1])
                answered = int(data[2])
                hour_data[hour] = (calls, answered)
                if calls > max_calls:
                    max_calls = calls
            
            # Create bar chart
            for hour in sorted(hour_data.keys()):
                calls, answered = hour_data[hour]
                bar_width = int((calls / max_calls) * 40) if max_calls > 0 else 0
                bar = '█' * bar_width
                answer_rate = (answered / calls * 100) if calls > 0 else 0
                
                print(f"{Colors.WHITE}{hour:02d}:00{Colors.RESET} │{Colors.GREEN}{bar:<40}{Colors.RESET}│ {Colors.CYAN}{calls:>4}{Colors.RESET} calls ({answer_rate:.0f}% answered)")
    
    def get_disposition_breakdown(self, hours=24):
        """Get detailed breakdown of call dispositions"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}")
        print(f"  📋 CALL DISPOSITION BREAKDOWN (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            disposition,
            COUNT(*) as count,
            AVG(duration) as avg_duration,
            AVG(billsec) as avg_billsec
        FROM cdr
        WHERE calldate >= '{cutoff}'
        GROUP BY disposition
        ORDER BY count DESC
        """
        
        results = self.query_db(sql)
        if results:
            total = sum(int(row.split('\t')[1]) for row in results)
            
            print(f"{Colors.WHITE}{'Disposition':<20} {'Count':<10} {'%':<8} {'Avg Duration':<15}{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}")
            
            for row in results:
                data = row.split('\t')
                disposition = data[0]
                count = int(data[1])
                avg_dur = int(float(data[2])) if data[2] and data[2] != 'NULL' else 0
                avg_bill = int(float(data[3])) if data[3] and data[3] != 'NULL' else 0
                percentage = (count / total * 100) if total > 0 else 0
                
                color = Colors.GREEN if disposition == 'ANSWERED' else Colors.YELLOW if disposition == 'NO ANSWER' else Colors.RED
                
                print(f"{color}{disposition:<20}{Colors.RESET} {count:<10} {percentage:>6.1f}%  {self.format_duration(avg_bill)}")
    
    def get_failed_calls(self, hours=24, limit=20):
        """Get recent failed calls with details"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}")
        print(f"  ❌ FAILED CALLS (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            calldate,
            src,
            dst,
            disposition,
            lastapp,
            lastdata
        FROM cdr
        WHERE calldate >= '{cutoff}' 
        AND disposition IN ('FAILED', 'BUSY', 'CONGESTION')
        ORDER BY calldate DESC
        LIMIT {limit}
        """
        
        results = self.query_db(sql)
        if results:
            print(f"{Colors.YELLOW}Found {len(results)} failed calls:{Colors.RESET}\n")
            
            for row in results:
                data = row.split('\t')
                calldate = data[0]
                src = data[1] if len(data) > 1 else 'N/A'
                dst = data[2] if len(data) > 2 else 'N/A'
                disposition = data[3] if len(data) > 3 else 'N/A'
                lastapp = data[4] if len(data) > 4 else 'N/A'
                lastdata = data[5] if len(data) > 5 else 'N/A'
                
                print(f"{Colors.WHITE}{calldate}{Colors.RESET}")
                print(f"  From: {Colors.GREEN}{src}{Colors.RESET} → To: {Colors.MAGENTA}{dst}{Colors.RESET}")
                print(f"  Status: {Colors.RED}{disposition}{Colors.RESET}")
                print(f"  Last App: {Colors.CYAN}{lastapp}{Colors.RESET}({lastdata})")
                print()
        else:
            print(f"{Colors.GREEN}✅ No failed calls found{Colors.RESET}")
    
    def get_trunk_usage(self, hours=24):
        """Analyze trunk usage patterns"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}")
        print(f"  📡 TRUNK USAGE ANALYSIS (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            channel,
            COUNT(*) as call_count,
            SUM(CASE WHEN disposition = 'ANSWERED' THEN 1 ELSE 0 END) as answered,
            SUM(duration) as total_duration
        FROM cdr
        WHERE calldate >= '{cutoff}' 
        AND channel LIKE '%SIP/%'
        GROUP BY SUBSTRING_INDEX(channel, '-', 1)
        ORDER BY call_count DESC
        LIMIT 15
        """
        
        results = self.query_db(sql)
        if results:
            print(f"{Colors.WHITE}{'Trunk/Channel':<30} {'Calls':<8} {'Success Rate':<15} {'Duration':<12}{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*70}{Colors.RESET}")
            
            for row in results:
                data = row.split('\t')
                channel = data[0]
                # Extract trunk name from channel
                trunk_match = re.search(r'SIP/([^-]+)', channel)
                trunk = trunk_match.group(1) if trunk_match else channel
                
                calls = int(data[1])
                answered = int(data[2])
                duration = int(float(data[3]))
                success_rate = (answered / calls * 100) if calls > 0 else 0
                
                color = Colors.GREEN if success_rate > 90 else Colors.YELLOW if success_rate > 70 else Colors.RED
                
                print(f"{Colors.CYAN}{trunk:<30}{Colors.RESET} {calls:<8} {color}{success_rate:>5.1f}%{Colors.RESET}           {self.format_duration(duration)}")
    
    def get_call_duration_distribution(self, hours=24):
        """Analyze call duration distribution"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*78}")
        print(f"  ⏱️  CALL DURATION DISTRIBUTION (Last {hours} hours)")
        print(f"{'='*78}{Colors.RESET}\n")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            CASE
                WHEN billsec = 0 THEN '0s (Unanswered)'
                WHEN billsec < 30 THEN '1-30s'
                WHEN billsec < 60 THEN '31-60s'
                WHEN billsec < 180 THEN '1-3 min'
                WHEN billsec < 300 THEN '3-5 min'
                WHEN billsec < 600 THEN '5-10 min'
                WHEN billsec < 1800 THEN '10-30 min'
                ELSE '30+ min'
            END as duration_range,
            COUNT(*) as count
        FROM cdr
        WHERE calldate >= '{cutoff}'
        GROUP BY duration_range
        ORDER BY 
            CASE duration_range
                WHEN '0s (Unanswered)' THEN 0
                WHEN '1-30s' THEN 1
                WHEN '31-60s' THEN 2
                WHEN '1-3 min' THEN 3
                WHEN '3-5 min' THEN 4
                WHEN '5-10 min' THEN 5
                WHEN '10-30 min' THEN 6
                ELSE 7
            END
        """
        
        results = self.query_db(sql)
        if results:
            total = sum(int(row.split('\t')[1]) for row in results)
            max_count = max(int(row.split('\t')[1]) for row in results)
            
            print(f"{Colors.WHITE}{'Duration Range':<20} {'Count':<10} {'%':<8} {'Graph':<30}{Colors.RESET}")
            print(f"{Colors.CYAN}{'─'*70}{Colors.RESET}")
            
            for row in results:
                data = row.split('\t')
                duration_range = data[0]
                count = int(data[1])
                percentage = (count / total * 100) if total > 0 else 0
                bar_width = int((count / max_count) * 20) if max_count > 0 else 0
                bar = '█' * bar_width
                
                print(f"{Colors.GREEN}{duration_range:<20}{Colors.RESET} {count:<10} {percentage:>6.1f}%  {Colors.CYAN}{bar}{Colors.RESET}")
    
    def export_to_json(self, hours=24, output_file=None):
        """Export call data to JSON format"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"/home/123net/cdr_export_{timestamp}.json"
        
        print(f"\n{Colors.CYAN}📤 Exporting call data to JSON...{Colors.RESET}")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        sql = f"""
        SELECT 
            calldate,
            clid,
            src,
            dst,
            dcontext,
            channel,
            dstchannel,
            lastapp,
            lastdata,
            duration,
            billsec,
            disposition,
            amaflags,
            accountcode,
            uniqueid,
            userfield
        FROM cdr
        WHERE calldate >= '{cutoff}'
        ORDER BY calldate DESC
        """
        
        results = self.query_db(sql)
        
        calls = []
        for row in results:
            data = row.split('\t')
            call = {
                'calldate': data[0] if len(data) > 0 else '',
                'clid': data[1] if len(data) > 1 else '',
                'src': data[2] if len(data) > 2 else '',
                'dst': data[3] if len(data) > 3 else '',
                'dcontext': data[4] if len(data) > 4 else '',
                'channel': data[5] if len(data) > 5 else '',
                'dstchannel': data[6] if len(data) > 6 else '',
                'lastapp': data[7] if len(data) > 7 else '',
                'lastdata': data[8] if len(data) > 8 else '',
                'duration': int(data[9]) if len(data) > 9 and data[9] else 0,
                'billsec': int(data[10]) if len(data) > 10 and data[10] else 0,
                'disposition': data[11] if len(data) > 11 else '',
                'amaflags': data[12] if len(data) > 12 else '',
                'accountcode': data[13] if len(data) > 13 else '',
                'uniqueid': data[14] if len(data) > 14 else '',
                'userfield': data[15] if len(data) > 15 else '',
            }
            calls.append(call)
        
        export_data = {
            'export_date': datetime.now().isoformat(),
            'hours': hours,
            'total_calls': len(calls),
            'calls': calls
        }
        
        try:
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            print(f"{Colors.GREEN}✅ Exported {len(calls)} calls to: {output_file}{Colors.RESET}")
            
            # Show file size
            size = os.path.getsize(output_file)
            print(f"{Colors.CYAN}   File size: {size:,} bytes{Colors.RESET}")
            
        except Exception as e:
            print(f"{Colors.RED}❌ Export failed: {str(e)}{Colors.RESET}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="FreePBX CDR/CEL Call Log Analyzer")
    parser.add_argument("--hours", type=int, default=24, help="Analyze calls from last N hours (default: 24)")
    parser.add_argument("--statistics", action="store_true", help="Show call statistics")
    parser.add_argument("--top-callers", action="store_true", help="Show top callers")
    parser.add_argument("--top-destinations", action="store_true", help="Show top destinations")
    parser.add_argument("--by-hour", action="store_true", help="Show call distribution by hour")
    parser.add_argument("--dispositions", action="store_true", help="Show disposition breakdown")
    parser.add_argument("--failed", action="store_true", help="Show failed calls")
    parser.add_argument("--trunk-usage", action="store_true", help="Show trunk usage")
    parser.add_argument("--duration-dist", action="store_true", help="Show duration distribution")
    parser.add_argument("--export-json", type=str, metavar="FILE", help="Export to JSON file")
    parser.add_argument("--comprehensive", action="store_true", help="Run all analyses")
    parser.add_argument("--db-user", default="root", help="MySQL username")
    parser.add_argument("--socket", default="/var/lib/mysql/mysql.sock", help="MySQL socket path")
    
    args = parser.parse_args()
    args = parser.parse_args()
    
    # Check root
    try:
        if os.geteuid() != 0:  # type: ignore
            print(f"{Colors.YELLOW}⚠️  This tool requires root access to query the database{Colors.RESET}")
            sys.exit(1)
    except AttributeError:
        pass  # Windows doesn't have geteuid
    
    analyzer = CDRAnalyzer(db_user=args.db_user, db_socket=args.socket)
    
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*78}")
    print(f"  📞 FREEPBX CDR/CEL CALL LOG ANALYZER")
    print(f"{'='*78}{Colors.RESET}")
    
    # Export mode
    if args.export_json:
        analyzer.export_to_json(hours=args.hours, output_file=args.export_json)
        sys.exit(0)
    
    # Comprehensive mode
    if args.comprehensive or not any([
        args.statistics, args.top_callers, args.top_destinations,
        args.by_hour, args.dispositions, args.failed, args.trunk_usage,
        args.duration_dist
    ]):
        analyzer.get_call_statistics(hours=args.hours)
        analyzer.get_disposition_breakdown(hours=args.hours)
        analyzer.get_call_by_hour(hours=args.hours)
        analyzer.get_top_callers(hours=args.hours, limit=10)
        analyzer.get_top_destinations(hours=args.hours, limit=10)
        analyzer.get_trunk_usage(hours=args.hours)
        analyzer.get_call_duration_distribution(hours=args.hours)
        analyzer.get_failed_calls(hours=args.hours, limit=10)
    else:
        # Individual analyses
        if args.statistics:
            analyzer.get_call_statistics(hours=args.hours)
        if args.top_callers:
            analyzer.get_top_callers(hours=args.hours)
        if args.top_destinations:
            analyzer.get_top_destinations(hours=args.hours)
        if args.by_hour:
            analyzer.get_call_by_hour(hours=args.hours)
        if args.dispositions:
            analyzer.get_disposition_breakdown(hours=args.hours)
        if args.failed:
            analyzer.get_failed_calls(hours=args.hours)
        if args.trunk_usage:
            analyzer.get_trunk_usage(hours=args.hours)
        if args.duration_dist:
            analyzer.get_call_duration_distribution(hours=args.hours)
    
    print(f"\n{Colors.GREEN}✅ Analysis complete{Colors.RESET}\n")


if __name__ == "__main__":
    main()

