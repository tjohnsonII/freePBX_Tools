#!/usr/bin/env python3
"""
FreePBX Network Diagnostics Tool
-------------------------------
Comprehensive network analysis and packet capture utilities
Integrates: sngrep, tcpdump, ping, traceroute, arp, routing, interfaces, DNS, netstat

VARIABLE MAP (Key Script Variables)
-----------------------------------
Colors         : ANSI color codes for CLI output
TeeOutput      : Class for writing to terminal and file
args           : Parsed command-line arguments
output_file    : Path to output report file
interface      : Network interface to analyze
diagnostics    : Dictionary of diagnostic results
capture_file   : Path to packet capture file

Key Function Arguments:
-----------------------
filename       : Path to file to read or write
interface      : Network interface name
args           : Parsed command-line arguments

See function docstrings for additional details on arguments and return values.

    FUNCTION MAP (Major Functions)
    -----------------------------
    parse_args                : Parse command-line arguments
    run_command               : Run a shell command and capture output
    run_ping                  : Run ping diagnostic
    run_traceroute            : Run traceroute diagnostic
    run_arp                   : Run ARP table diagnostic
    run_ifconfig              : Get network interface configuration
    run_netstat               : Get network socket statistics
    run_dns_lookup            : Perform DNS lookup
    run_tcpdump               : Run tcpdump packet capture
    run_sngrep                : Run sngrep for SIP analysis
    print_summary             : Print summary of diagnostics to terminal
    write_report              : Write diagnostics report to file
    main                      : CLI entry point, parses args and runs diagnostics
"""

import subprocess
import sys
import os
import time
import threading
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
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=5
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
                # Stream output in real-time. A background reader thread drains
                # stdout as it arrives; the main thread enforces `timeout` itself
                # (long-running captures like tcpdump never exit on their own) and
                # shows a countdown while nothing is coming through.
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )

                output_lines = []
                got_output = threading.Event()

                def _reader():
                    stdout = process.stdout
                    if stdout is not None:
                        for line in stdout:
                            got_output.set()
                            print(f"{Colors.GREEN}│{Colors.RESET} {line}", end='')
                            output_lines.append(line)

                reader_thread = threading.Thread(target=_reader, daemon=True)
                reader_thread.start()

                start = time.time()
                last_tick = -1
                while process.poll() is None and (time.time() - start) < timeout:
                    elapsed = time.time() - start
                    if int(elapsed) != last_tick and not got_output.is_set():
                        remaining = max(0, int(timeout - elapsed))
                        print(f"\r{Colors.CYAN}  ⏳ {remaining}s remaining...{Colors.RESET}   ", end='', flush=True)
                        last_tick = int(elapsed)
                    got_output.clear()
                    time.sleep(0.2)

                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

                reader_thread.join(timeout=5)
                print()
                return (process.returncode or 0), ''.join(output_lines), ''
            else:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    universal_newlines=True,
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
            # Try which command first
            result = subprocess.run(
                ["which", tool_name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=5
            )
            if result.returncode == 0:
                return True
        except:
            pass
        
        # Try command -v as fallback
        try:
            result = subprocess.run(
                ["bash", "-c", f"command -v {tool_name}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=5
            )
            if result.returncode == 0:
                return True
        except:
            pass
        
        # Try direct execution as last resort
        try:
            result = subprocess.run(
                [tool_name, "--help"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=2
            )
            return True
        except:
            pass
        
        return False
    
    def show_interface_info(self):
        """Show comprehensive interface information"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🌐 NETWORK INTERFACE INFORMATION{' ' * 44}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Try multiple commands in order of preference - check if binary exists
        commands_to_try = [
            (["/sbin/ip", "addr", "show"], "Using 'ip addr' command:", Colors.GREEN),
            (["/usr/sbin/ip", "addr", "show"], "Using 'ip addr' command:", Colors.GREEN),
            (["ip", "addr", "show"], "Using 'ip addr' command:", Colors.GREEN),
            (["/sbin/ifconfig", "-a"], "Using 'ifconfig' command (legacy):", Colors.YELLOW),
            (["/usr/sbin/ifconfig", "-a"], "Using 'ifconfig' command (legacy):", Colors.YELLOW),
            (["ifconfig", "-a"], "Using 'ifconfig' command (legacy):", Colors.YELLOW),
        ]
        
        success = False
        for cmd, label, color in commands_to_try:
            # Check if the binary exists
            binary = cmd[0]
            if os.path.exists(binary) or '/' not in binary:  # If no path, might be in PATH
                try:
                    print(f"{color}📡 {label}{Colors.RESET}\n")
                    self.run_command(cmd)
                    
                    # If using ip, also show link status
                    if "ip" in cmd[0]:
                        print(f"\n{color}🔗 Link status:{Colors.RESET}\n")
                        link_cmd = cmd[0:1] + ["link", "show"]
                        self.run_command(link_cmd)
                    
                    success = True
                    break
                except Exception as e:
                    # Binary exists but failed, try next
                    continue
        
        if not success:
            print(f"{Colors.RED}❌ No interface tools available (ip/ifconfig){Colors.RESET}")
    
    def show_routing_info(self):
        """Show routing table information"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🗺️  ROUTING TABLE INFORMATION{' ' * 47}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Try multiple commands in order of preference - check if binary exists
        commands_to_try = [
            (["/sbin/ip", "route", "show"], "IPv4 Routes:", Colors.GREEN, True),
            (["/usr/sbin/ip", "route", "show"], "IPv4 Routes:", Colors.GREEN, True),
            (["ip", "route", "show"], "IPv4 Routes:", Colors.GREEN, True),
            (["/sbin/route", "-n"], "Using 'route' command (legacy):", Colors.YELLOW, False),
            (["/usr/sbin/route", "-n"], "Using 'route' command (legacy):", Colors.YELLOW, False),
            (["route", "-n"], "Using 'route' command (legacy):", Colors.YELLOW, False),
            (["/bin/netstat", "-rn"], "Using 'netstat -rn':", Colors.YELLOW, False),
            (["netstat", "-rn"], "Using 'netstat -rn':", Colors.YELLOW, False),
        ]
        
        success = False
        for cmd, label, color, is_ip in commands_to_try:
            # Check if the binary exists
            binary = cmd[0]
            if os.path.exists(binary) or '/' not in binary:  # If no path, might be in PATH
                try:
                    print(f"{color}📍 {label}{Colors.RESET}\n")
                    self.run_command(cmd)
                    
                    # If using ip, also show IPv6 routes
                    if is_ip:
                        print(f"\n{color}📍 IPv6 Routes:{Colors.RESET}\n")
                        ipv6_cmd = cmd[0:1] + ["-6", "route", "show"]
                        try:
                            self.run_command(ipv6_cmd)
                        except:
                            pass
                    
                    success = True
                    break
                except Exception as e:
                    # Binary exists but failed, try next
                    continue
        
        if not success:
            print(f"{Colors.RED}❌ No routing tools available (ip/route){Colors.RESET}")
    
    def show_arp_table(self):
        """Show ARP table"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔗 ARP TABLE (Address Resolution Protocol){' ' * 34}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Try arp first - check if binary exists
        arp_paths = ["/sbin/arp", "/usr/sbin/arp", "arp"]
        for path in arp_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    self.run_command([path, "-an"])
                    return
                except:
                    continue
        
        # Fallback to ip neigh
        ip_paths = ["/sbin/ip", "/usr/sbin/ip", "ip"]
        for path in ip_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    self.run_command([path, "neigh", "show"])
                    return
                except:
                    continue
        
        print(f"{Colors.RED}❌ No ARP tools available{Colors.RESET}")
    
    def show_netstat_info(self):
        """Show network statistics and connections"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📊 NETWORK STATISTICS & CONNECTIONS{' ' * 40}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Try netstat first - check if binary exists
        netstat_paths = ["/bin/netstat", "/usr/bin/netstat", "netstat"]
        for path in netstat_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    print(f"{Colors.GREEN}🔌 Active connections:{Colors.RESET}\n")
                    self.run_command([path, "-tulpn"])
                    
                    print(f"\n{Colors.GREEN}📈 Interface statistics:{Colors.RESET}\n")
                    self.run_command([path, "-i"])
                    return
                except:
                    continue
        
        # Fallback to ss
        ss_paths = ["/sbin/ss", "/usr/sbin/ss", "ss"]
        for path in ss_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    print(f"{Colors.GREEN}🔌 Active connections (using ss):{Colors.RESET}\n")
                    self.run_command([path, "-tulpn"])
                    return
                except:
                    continue
        
        print(f"{Colors.RED}❌ No netstat/ss tools available{Colors.RESET}")
    
    def run_ping(self, host, count=4):
        """Ping a host"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🏓 PING TEST TO {host:<57}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Try multiple paths for ping
        ping_paths = ["/bin/ping", "/usr/bin/ping", "ping"]
        for path in ping_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    self.run_command([path, "-c", str(count), host])
                    return
                except:
                    continue
        
        print(f"{Colors.RED}❌ ping not available{Colors.RESET}")
    
    def run_traceroute(self, host):
        """Run traceroute to a host"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🗺️  TRACEROUTE TO {host:<55}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Try multiple paths for traceroute
        traceroute_paths = [
            (["/bin/traceroute", "-n", host], "Using traceroute", Colors.GREEN),
            (["/usr/bin/traceroute", "-n", host], "Using traceroute", Colors.GREEN),
            (["traceroute", "-n", host], "Using traceroute", Colors.GREEN),
            (["/usr/sbin/traceroute", "-n", host], "Using traceroute", Colors.GREEN),
            (["/bin/tracepath", host], "Using tracepath (traceroute not available)", Colors.YELLOW),
            (["/usr/bin/tracepath", host], "Using tracepath (traceroute not available)", Colors.YELLOW),
            (["tracepath", host], "Using tracepath (traceroute not available)", Colors.YELLOW),
        ]
        
        for cmd, label, color in traceroute_paths:
            binary = cmd[0]
            if os.path.exists(binary) or '/' not in binary:
                try:
                    if "tracepath" in label:
                        print(f"{color}{label}{Colors.RESET}\n")
                    self.run_command(cmd, timeout=60)
                    return
                except:
                    continue
        
        print(f"{Colors.RED}❌ No traceroute tools available{Colors.RESET}")
    
    def run_dns_lookup(self, domain):
        """Run DNS lookup"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🔍 DNS LOOKUP FOR {domain:<54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Try dig first (most detailed)
        dig_paths = ["/usr/bin/dig", "/bin/dig", "dig"]
        for path in dig_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    print(f"{Colors.GREEN}📋 Using dig (detailed):{Colors.RESET}\n")
                    self.run_command([path, domain])
                    
                    print(f"\n{Colors.GREEN}📋 Short answer:{Colors.RESET}\n")
                    self.run_command([path, "+short", domain])
                    return
                except:
                    continue
        
        # Try nslookup
        nslookup_paths = ["/usr/bin/nslookup", "/bin/nslookup", "nslookup"]
        for path in nslookup_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    print(f"{Colors.YELLOW}📋 Using nslookup:{Colors.RESET}\n")
                    self.run_command([path, domain])
                    return
                except:
                    continue
        
        # Try host
        host_paths = ["/usr/bin/host", "/bin/host", "host"]
        for path in host_paths:
            if os.path.exists(path) or '/' not in path:
                try:
                    print(f"{Colors.YELLOW}📋 Using host:{Colors.RESET}\n")
                    self.run_command([path, domain])
                    return
                except:
                    continue
        
        print(f"{Colors.RED}❌ No DNS tools available (dig/nslookup/host){Colors.RESET}")
    
    def capture_with_tcpdump(self, duration=60, port=None, host=None, output_file=None):
        """Capture packets with tcpdump"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📦 TCPDUMP PACKET CAPTURE{' ' * 50}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Check for tcpdump
        tcpdump_paths = ["/usr/sbin/tcpdump", "/sbin/tcpdump", "/usr/bin/tcpdump", "tcpdump"]
        tcpdump_cmd = None
        for path in tcpdump_paths:
            if os.path.exists(path) or '/' not in path:
                tcpdump_cmd = path
                break
        
        if not tcpdump_cmd:
            print(f"{Colors.RED}❌ tcpdump not available{Colors.RESET}")
            return
        
        # Build tcpdump command
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_file:
            output_file = f"{self.output_dir}/capture_{timestamp}.pcap"
        
        cmd = [tcpdump_cmd, "-i", self.interface, "-w", output_file]
        
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
        
        import os
        
        # Check for sngrep
        sngrep_paths = ["/usr/bin/sngrep", "/usr/local/bin/sngrep", "sngrep"]
        sngrep_cmd = None
        for path in sngrep_paths:
            if os.path.exists(path) or '/' not in path:
                sngrep_cmd = path
                break
        
        if not sngrep_cmd:
            print(f"{Colors.RED}❌ sngrep not available{Colors.RESET}")
            print(f"{Colors.YELLOW}💡 Install with: yum install sngrep  (or)  apt install sngrep{Colors.RESET}")
            return
        
        cmd = [sngrep_cmd]
        
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
        """Analyze SIP traffic on port 5060"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 SIP TRAFFIC ANALYSIS{' ' * 53}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Check for tcpdump
        tcpdump_paths = ["/usr/sbin/tcpdump", "/sbin/tcpdump", "/usr/bin/tcpdump", "tcpdump"]
        tcpdump_cmd = None
        for path in tcpdump_paths:
            if os.path.exists(path) or '/' not in path:
                tcpdump_cmd = path
                break
        
        if not tcpdump_cmd:
            print(f"{Colors.RED}❌ tcpdump not available{Colors.RESET}")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{self.output_dir}/sip_capture_{timestamp}.pcap"
        
        print(f"{Colors.GREEN}📡 Capturing SIP traffic on port 5060...{Colors.RESET}")
        print(f"{Colors.GREEN}⏱️  Duration: {duration}s{Colors.RESET}\n")
        
        # Capture SIP traffic (port 5060)
        cmd = [tcpdump_cmd, "-i", self.interface, "-s", "0", "-w", output_file, "port 5060"]
        
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
        """Monitor RTP traffic (audio streams)"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 🎵 RTP TRAFFIC MONITOR{' ' * 54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Check for tcpdump
        tcpdump_paths = ["/usr/sbin/tcpdump", "/sbin/tcpdump", "/usr/bin/tcpdump", "tcpdump"]
        tcpdump_cmd = None
        for path in tcpdump_paths:
            if os.path.exists(path) or '/' not in path:
                tcpdump_cmd = path
                break
        
        if not tcpdump_cmd:
            print(f"{Colors.RED}❌ tcpdump not available{Colors.RESET}")
            return
        
        print(f"{Colors.GREEN}📡 Monitoring RTP traffic (ports 10000-20000)...{Colors.RESET}")
        print(f"{Colors.GREEN}⏱️  Duration: {duration}s{Colors.RESET}\n")
        
        # Monitor RTP port range
        cmd = [tcpdump_cmd, "-i", self.interface, "-n", "udp", "portrange", "10000-20000"]
        
        try:
            self.run_command(cmd, timeout=duration, stream_output=True)
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}⏹️  Monitoring stopped by user{Colors.RESET}")
    
    def show_asterisk_sip_peers(self):
        """Show Asterisk SIP peers"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} ☎️  ASTERISK SIP PEERS{' ' * 54}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Check for asterisk CLI
        asterisk_paths = ["/usr/sbin/asterisk", "/usr/bin/asterisk", "asterisk"]
        asterisk_cmd = None
        for path in asterisk_paths:
            if os.path.exists(path) or '/' not in path:
                asterisk_cmd = path
                break
        
        if asterisk_cmd:
            try:
                self.run_command([asterisk_cmd, "-rx", "pjsip show endpoints"])

                print(f"\n{Colors.GREEN}📊 SIP Registrations:{Colors.RESET}\n")
                self.run_command([asterisk_cmd, "-rx", "pjsip show registrations"])
                return
            except:
                pass
        
        print(f"{Colors.RED}❌ Asterisk CLI not available{Colors.RESET}")
    
    def show_asterisk_channels(self):
        """Show active Asterisk channels"""
        print(f"\n{Colors.CYAN}╔{'═' * 78}╗{Colors.RESET}")
        print(f"{Colors.CYAN}║{Colors.YELLOW}{Colors.BOLD} 📞 ACTIVE ASTERISK CHANNELS{' ' * 48}{Colors.RESET}{Colors.CYAN} ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
        
        import os
        
        # Check for asterisk CLI
        asterisk_paths = ["/usr/sbin/asterisk", "/usr/bin/asterisk", "asterisk"]
        asterisk_cmd = None
        for path in asterisk_paths:
            if os.path.exists(path) or '/' not in path:
                asterisk_cmd = path
                break
        
        if asterisk_cmd:
            try:
                self.run_command([asterisk_cmd, "-rx", "core show channels"])
                
                print(f"\n{Colors.GREEN}📊 Channel statistics:{Colors.RESET}\n")
                self.run_command([asterisk_cmd, "-rx", "core show channels count"])
                return
            except:
                pass
        
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
        self.run_ping("8.8.8.8", count=3)
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
        diag.run_ping(args.ping)
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

