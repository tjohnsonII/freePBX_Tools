#!/usr/bin/env python3
"""
FreePBX Network Diagnostics Tool
Comprehensive network analysis and packet capture utilities
Integrates: sngrep, tcpdump, ping, traceroute, arp, routing, interfaces, DNS, netstat
"""

import subprocess
import sys
import os
import time
import argparse
import re
from datetime import datetime
import json

class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


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


class NetworkDiagnostics:
    def __init__(self, interface=None):
        self.interface = interface or self._get_primary_interface()
        self.output_dir = "/home/123net/network_diagnostics"
        self.ensure_output_dir()
        
    def ensure_output_dir(self):
        """Create output directory if it doesn't exist"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except:
            self.output_dir = "/tmp/network_diagnostics"
            os.makedirs(self.output_dir, exist_ok=True)
    
    def _get_primary_interface(self):
        """Detect the primary network interface"""
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                # Extract interface from: default via 192.168.1.1 dev eth0
                match = re.search(r'dev\s+(\S+)', result.stdout)
                if match:
                    return match.group(1)
        except:
            pass
        return "eth0"  # fallback
    
    def run_command(self, cmd, timeout=30, stream_output=True):
        """Run a command and optionally stream output in real-time"""
        print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔧 EXECUTING COMMAND{' ' * 56}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.WHITE} {' '.join(cmd):<75}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        try:
            if stream_output:
                # Stream output in real-time
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                output_lines = []
                stdout = process.stdout
                if stdout is not None:
                    for line in stdout:
                        print(f"{Colors.GREEN}│{Colors.RESET} {line}", end='')
                        output_lines.append(line)
                
                process.wait(timeout=timeout)
                return process.returncode, ''.join(output_lines), ''
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                return result.returncode, result.stdout, result.stderr
                
        except subprocess.TimeoutExpired:
            print(f"{Colors.RED}⏱️  Command timed out after {timeout}s{Colors.RESET}")
            return -1, '', 'Timeout'
        except Exception as e:
            print(f"{Colors.RED}❌ Error: {str(e)}{Colors.RESET}")
            return -1, '', str(e)
    
    def check_tool_available(self, tool_name):
        """Check if a tool is available on the system"""
        try:
            result = subprocess.run(
                ["which", tool_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def show_interface_info(self):
        """Show comprehensive interface information"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🌐 NETWORK INTERFACE INFORMATION{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        # Try ip addr first (modern)
        if self.check_tool_available("ip"):
            print(f"{Colors.GREEN}📡 Using 'ip addr' command:{Colors.RESET}\n")
            self.run_command(["ip", "addr", "show"])
            
            print(f"\n{Colors.GREEN}🔗 Link status:{Colors.RESET}\n")
            self.run_command(["ip", "link", "show"])
        
        # Fallback to ifconfig (legacy)
        elif self.check_tool_available("ifconfig"):
            print(f"{Colors.YELLOW}📡 Using 'ifconfig' command (legacy):{Colors.RESET}\n")
            self.run_command(["ifconfig", "-a"])
        
        else:
            print(f"{Colors.RED}❌ No interface tools available (ip/ifconfig){Colors.RESET}")
    
    def show_routing_info(self):
        """Show routing table information"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🗺️  ROUTING TABLE INFORMATION{' ' * 47}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        # Try ip route first (modern)
        if self.check_tool_available("ip"):
            print(f"{Colors.GREEN}📍 IPv4 Routes:{Colors.RESET}\n")
            self.run_command(["ip", "route", "show"])
            
            print(f"\n{Colors.GREEN}📍 IPv6 Routes:{Colors.RESET}\n")
            self.run_command(["ip", "-6", "route", "show"])
        
        # Fallback to route (legacy)
        elif self.check_tool_available("route"):
            print(f"{Colors.YELLOW}📍 Using 'route' command (legacy):{Colors.RESET}\n")
            self.run_command(["route", "-n"])
        
        else:
            print(f"{Colors.RED}❌ No routing tools available (ip/route){Colors.RESET}")
    
    def show_arp_table(self):
        """Show ARP table"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔗 ARP TABLE (Address Resolution Protocol){' ' * 34}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if self.check_tool_available("arp"):
            self.run_command(["arp", "-an"])
        elif self.check_tool_available("ip"):
            self.run_command(["ip", "neigh", "show"])
        else:
            print(f"{Colors.RED}❌ No ARP tools available{Colors.RESET}")
    
    def show_netstat_info(self):
        """Show network statistics and connections"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📊 NETWORK STATISTICS & CONNECTIONS{' ' * 40}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if self.check_tool_available("netstat"):
            print(f"{Colors.GREEN}🔌 Active connections:{Colors.RESET}\n")
            self.run_command(["netstat", "-tulpn"])
            
            print(f"\n{Colors.GREEN}📈 Interface statistics:{Colors.RESET}\n")
            self.run_command(["netstat", "-i"])
        
        elif self.check_tool_available("ss"):
            print(f"{Colors.GREEN}🔌 Active connections (using ss):{Colors.RESET}\n")
            self.run_command(["ss", "-tulpn"])
        
        else:
            print(f"{Colors.RED}❌ No netstat/ss tools available{Colors.RESET}")
    
    def run_ping_test(self, host, count=5):
        """Run ping test to a host"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🏓 PING TEST TO {host:<58}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if self.check_tool_available("ping"):
            self.run_command(["ping", "-c", str(count), host])
        else:
            print(f"{Colors.RED}❌ ping not available{Colors.RESET}")
    
    def run_traceroute(self, host):
        """Run traceroute to a host"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🗺️  TRACEROUTE TO {host:<55}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if self.check_tool_available("traceroute"):
            self.run_command(["traceroute", "-n", host], timeout=60)
        elif self.check_tool_available("tracepath"):
            print(f"{Colors.YELLOW}Using tracepath (traceroute not available){Colors.RESET}\n")
            self.run_command(["tracepath", host], timeout=60)
        else:
            print(f"{Colors.RED}❌ No traceroute tools available{Colors.RESET}")
    
    def run_dns_lookup(self, domain):
        """Run DNS lookup"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔍 DNS LOOKUP FOR {domain:<54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if self.check_tool_available("dig"):
            print(f"{Colors.GREEN}📋 Using dig (detailed):{Colors.RESET}\n")
            self.run_command(["dig", domain])
            
            print(f"\n{Colors.GREEN}📋 Short answer:{Colors.RESET}\n")
            self.run_command(["dig", "+short", domain])
        
        elif self.check_tool_available("nslookup"):
            print(f"{Colors.YELLOW}📋 Using nslookup:{Colors.RESET}\n")
            self.run_command(["nslookup", domain])
        
        elif self.check_tool_available("host"):
            print(f"{Colors.YELLOW}📋 Using host:{Colors.RESET}\n")
            self.run_command(["host", domain])
        
        else:
            print(f"{Colors.RED}❌ No DNS tools available (dig/nslookup/host){Colors.RESET}")
    
    def capture_with_tcpdump(self, duration=60, port=None, host=None, output_file=None):
        """Capture packets with tcpdump"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📦 TCPDUMP PACKET CAPTURE{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if not self.check_tool_available("tcpdump"):
            print(f"{Colors.RED}❌ tcpdump not available{Colors.RESET}")
            return
        
        # Build tcpdump command
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_file:
            output_file = f"{self.output_dir}/capture_{timestamp}.pcap"
        
        cmd = ["tcpdump", "-i", self.interface, "-w", output_file]
        
        # Add filters
        filter_parts = []
        if port:
            filter_parts.append(f"port {port}")
        if host:
            filter_parts.append(f"host {host}")
        
        if filter_parts:
            cmd.append(" and ".join(filter_parts))
        
        print(f"{Colors.GREEN}📡 Interface: {Colors.BOLD}{self.interface}{Colors.RESET}")
        print(f"{Colors.GREEN}💾 Output file: {Colors.BOLD}{output_file}{Colors.RESET}")
        print(f"{Colors.GREEN}⏱️  Duration: {Colors.BOLD}{duration}s{Colors.RESET}")
        if port:
            print(f"{Colors.GREEN}🔌 Port filter: {Colors.BOLD}{port}{Colors.RESET}")
        if host:
            print(f"{Colors.GREEN}🖥️  Host filter: {Colors.BOLD}{host}{Colors.RESET}")
        print()
        
        print(f"{Colors.YELLOW}⚠️  Press Ctrl+C to stop capture early{Colors.RESET}\n")
        
        try:
            self.run_command(cmd, timeout=duration, stream_output=True)
            print(f"\n{Colors.GREEN}✅ Capture complete: {output_file}{Colors.RESET}")
            
            # Show file info
            if os.path.exists(output_file):
                size = os.path.getsize(output_file)
                print(f"{Colors.CYAN}📊 File size: {size:,} bytes{Colors.RESET}")
        
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}⏹️  Capture stopped by user{Colors.RESET}")
    
    def launch_sngrep(self, filter_option=None):
        """Launch sngrep for SIP packet analysis"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 SNGREP - SIP PACKET ANALYZER{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if not self.check_tool_available("sngrep"):
            print(f"{Colors.RED}❌ sngrep not available{Colors.RESET}")
            print(f"{Colors.YELLOW}💡 Install with: yum install sngrep  (or)  apt install sngrep{Colors.RESET}")
            return
        
        cmd = ["sngrep"]
        
        if filter_option:
            cmd.extend(["-d", filter_option])
        
        print(f"{Colors.GREEN}🚀 Launching sngrep...{Colors.RESET}")
        print(f"{Colors.CYAN}📌 Interface: {self.interface}{Colors.RESET}")
        print(f"{Colors.YELLOW}💡 Press 'q' to quit sngrep{Colors.RESET}\n")
        
        try:
            # Launch sngrep interactively (don't capture output)
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}⏹️  sngrep closed{Colors.RESET}")
    
    def analyze_sip_traffic(self, duration=30):
        """Capture and analyze SIP traffic"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 SIP TRAFFIC ANALYSIS{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if not self.check_tool_available("tcpdump"):
            print(f"{Colors.RED}❌ tcpdump not available{Colors.RESET}")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{self.output_dir}/sip_capture_{timestamp}.pcap"
        
        print(f"{Colors.GREEN}📡 Capturing SIP traffic on port 5060...{Colors.RESET}")
        print(f"{Colors.GREEN}⏱️  Duration: {duration}s{Colors.RESET}\n")
        
        # Capture SIP traffic (port 5060)
        cmd = ["tcpdump", "-i", self.interface, "-s", "0", "-w", output_file, "port 5060"]
        
        try:
            self.run_command(cmd, timeout=duration, stream_output=False)
            
            if os.path.exists(output_file):
                print(f"\n{Colors.GREEN}✅ SIP capture complete: {output_file}{Colors.RESET}")
                
                # Analyze the capture
                print(f"\n{Colors.CYAN}📊 Analyzing SIP messages...{Colors.RESET}\n")
                analyze_cmd = ["tcpdump", "-r", output_file, "-n", "-A"]
                self.run_command(analyze_cmd, stream_output=True)
        
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}⏹️  Capture stopped by user{Colors.RESET}")
    
    def monitor_rtp_traffic(self, duration=30):
        """Monitor RTP (audio) traffic"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🎵 RTP TRAFFIC MONITOR{' ' * 54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if not self.check_tool_available("tcpdump"):
            print(f"{Colors.RED}❌ tcpdump not available{Colors.RESET}")
            return
        
        print(f"{Colors.GREEN}📡 Monitoring RTP traffic (ports 10000-20000)...{Colors.RESET}")
        print(f"{Colors.GREEN}⏱️  Duration: {duration}s{Colors.RESET}\n")
        
        # Monitor RTP port range
        cmd = ["tcpdump", "-i", self.interface, "-n", "udp", "portrange", "10000-20000"]
        
        try:
            self.run_command(cmd, timeout=duration, stream_output=True)
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}⏹️  Monitoring stopped by user{Colors.RESET}")
    
    def show_asterisk_sip_peers(self):
        """Show Asterisk SIP peers"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} ☎️  ASTERISK SIP PEERS{' ' * 54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if self.check_tool_available("asterisk"):
            self.run_command(["asterisk", "-rx", "sip show peers"])
            
            print(f"\n{Colors.GREEN}📊 SIP Registry:{Colors.RESET}\n")
            self.run_command(["asterisk", "-rx", "sip show registry"])
        else:
            print(f"{Colors.RED}❌ Asterisk CLI not available{Colors.RESET}")
    
    def show_asterisk_channels(self):
        """Show active Asterisk channels"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 ACTIVE ASTERISK CHANNELS{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        if self.check_tool_available("asterisk"):
            self.run_command(["asterisk", "-rx", "core show channels"])
            
            print(f"\n{Colors.GREEN}📊 Channel statistics:{Colors.RESET}\n")
            self.run_command(["asterisk", "-rx", "core show channels count"])
        else:
            print(f"{Colors.RED}❌ Asterisk CLI not available{Colors.RESET}")
    
    def run_comprehensive_diagnostic(self):
        """Run comprehensive network diagnostic"""
        print(f"\n{Colors.YELLOW}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.BOLD}{Colors.WHITE} 🔬 COMPREHENSIVE NETWORK DIAGNOSTIC{' ' * 40}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}╚{'═' * 78}╝{Colors.RESET}\n")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"{self.output_dir}/network_diagnostic_{timestamp}.txt"
        
        print(f"{Colors.CYAN}📝 Generating comprehensive report...{Colors.RESET}")
        print(f"{Colors.CYAN}💾 Output: {report_file}{Colors.RESET}\n")
        
        # Run all diagnostics
        self.show_interface_info()
        self.show_routing_info()
        self.show_arp_table()
        self.show_netstat_info()
        self.run_ping_test("8.8.8.8", count=3)
        self.run_dns_lookup("google.com")
        
        # Asterisk-specific
        self.show_asterisk_sip_peers()
        self.show_asterisk_channels()
        
        print(f"\n{Colors.GREEN}✅ Comprehensive diagnostic complete!{Colors.RESET}")


def main():
    parser = argparse.ArgumentParser(description="FreePBX Network Diagnostics Tool")
    parser.add_argument("-i", "--interface", help="Network interface to use")
    parser.add_argument("-o", "--output", help="Save output to file")
    parser.add_argument("--interfaces", action="store_true", help="Show interface information")
    parser.add_argument("--routing", action="store_true", help="Show routing table")
    parser.add_argument("--arp", action="store_true", help="Show ARP table")
    parser.add_argument("--netstat", action="store_true", help="Show network statistics")
    parser.add_argument("--ping", metavar="HOST", help="Ping a host")
    parser.add_argument("--traceroute", metavar="HOST", help="Traceroute to a host")
    parser.add_argument("--dns", metavar="DOMAIN", help="DNS lookup")
    parser.add_argument("--tcpdump", action="store_true", help="Capture packets with tcpdump")
    parser.add_argument("--duration", type=int, default=60, help="Capture duration (seconds)")
    parser.add_argument("--port", type=int, help="Filter by port")
    parser.add_argument("--host", help="Filter by host")
    parser.add_argument("--sngrep", action="store_true", help="Launch sngrep SIP analyzer")
    parser.add_argument("--sip-traffic", action="store_true", help="Analyze SIP traffic")
    parser.add_argument("--rtp-traffic", action="store_true", help="Monitor RTP traffic")
    parser.add_argument("--asterisk-peers", action="store_true", help="Show Asterisk SIP peers")
    parser.add_argument("--asterisk-channels", action="store_true", help="Show Asterisk channels")
    parser.add_argument("--comprehensive", action="store_true", help="Run comprehensive diagnostic")
    
    args = parser.parse_args()
    
    # Setup output redirection if requested
    output_file = None
    original_stdout = sys.stdout
    if args.output:
        try:
            output_file = open(args.output, 'w')
            sys.stdout = TeeOutput(output_file)
            print(f"{Colors.GREEN}📝 Logging output to: {args.output}{Colors.RESET}\n")
        except Exception as e:
            print(f"{Colors.RED}Error opening output file: {e}{Colors.RESET}")
            sys.exit(1)
    
    diag = NetworkDiagnostics(interface=args.interface)
    
    print(f"{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🌐 FREEPBX NETWORK DIAGNOSTICS{' ' * 46}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╠{'═' * 78}╣{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} Interface: {Colors.GREEN}{Colors.BOLD}{diag.interface:<64}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} Output Dir: {Colors.CYAN}{diag.output_dir:<63}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}")
    
    # Execute requested diagnostics
    if args.interfaces:
        diag.show_interface_info()
    elif args.routing:
        diag.show_routing_info()
    elif args.arp:
        diag.show_arp_table()
    elif args.netstat:
        diag.show_netstat_info()
    elif args.ping:
        diag.run_ping_test(args.ping)
    elif args.traceroute:
        diag.run_traceroute(args.traceroute)
    elif args.dns:
        diag.run_dns_lookup(args.dns)
    elif args.tcpdump:
        diag.capture_with_tcpdump(duration=args.duration, port=args.port, host=args.host)
    elif args.sngrep:
        diag.launch_sngrep()
    elif args.sip_traffic:
        diag.analyze_sip_traffic(duration=args.duration)
    elif args.rtp_traffic:
        diag.monitor_rtp_traffic(duration=args.duration)
    elif args.asterisk_peers:
        diag.show_asterisk_sip_peers()
    elif args.asterisk_channels:
        diag.show_asterisk_channels()
    elif args.comprehensive:
        diag.run_comprehensive_diagnostic()
    else:
        # Show usage
        print(f"\n{Colors.YELLOW}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.BOLD}{Colors.WHITE} 🎯 USAGE EXAMPLES{' ' * 59}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}╠{'═' * 78}╣{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Show all network interfaces:{' ' * 46}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 freepbx_network_diagnostics.py --interfaces{' ' * 22}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Show routing table:{' ' * 54}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 freepbx_network_diagnostics.py --routing{' ' * 25}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Ping test:{' ' * 63}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 freepbx_network_diagnostics.py --ping 8.8.8.8{' ' * 22}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Capture SIP traffic for 60 seconds:{' ' * 37}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 freepbx_network_diagnostics.py --sip-traffic --duration 60{' ' * 8}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Launch sngrep for SIP analysis:{' ' * 42}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 freepbx_network_diagnostics.py --sngrep{' ' * 26}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.RESET}{' ' * 78}{Colors.YELLOW}║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.CYAN} # Run comprehensive diagnostic:{' ' * 45}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}║{Colors.WHITE}   python3 freepbx_network_diagnostics.py --comprehensive{' ' * 19}{Colors.RESET}{Colors.YELLOW} ║{Colors.RESET}")
        print(f"{Colors.YELLOW}╚{'═' * 78}╝{Colors.RESET}")


if __name__ == "__main__":
    main()

