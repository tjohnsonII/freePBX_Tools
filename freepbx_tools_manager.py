#!/usr/bin/env python3
"""
freePBX Version Manager - Interactive deployment and uninstall tool
"""

import sys
import os
import subprocess
import getpass
import tempfile

# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("")  # This enables ANSI escape sequences in Windows console

class Colors:
    """ANSI color codes"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_banner():
    """Display banner"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}")
    print(" ╔═══════════════════════════════════════════════════════════════════╗")
    print(" ║                                                                   ║")
    print(" ║   █▀▀ █▀█ █▀▀ █▀▀ █▀█ █▄▄ ▀▄▀   █░█ █▀▀ █▀█ █▀ █ █▀█ █▄░█       ║")
    print(" ║   █▀░ █▀▄ ██▄ ██▄ █▀▀ █▄█ █░█   ▀▄▀ ██▄ █▀▄ ▄█ █ █▄█ █░▀█       ║")
    print(" ║                                                                   ║")
    print(" ║                       M A N A G E R                               ║")
    print(" ║                                                                   ║")
    print(" ╚═══════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")

def print_menu():
    """Display main menu"""
    print(f"\n{Colors.YELLOW}{Colors.BOLD}📋 Main Menu:{Colors.RESET}")
    print(f"  {Colors.CYAN}1){Colors.RESET} Deploy tools to server(s)")
    print(f"  {Colors.CYAN}2){Colors.RESET} Uninstall tools from server(s)")
    print(f"  {Colors.CYAN}3){Colors.RESET} 🔄 Uninstall + Install (clean deployment)")
    print(f"  {Colors.CYAN}4){Colors.RESET} Test dashboard on test server (69.39.69.102)")
    print(f"  {Colors.CYAN}5){Colors.RESET} View deployment status")
    print(f"  {Colors.CYAN}6){Colors.RESET} Exit")
    print()

def get_credentials():
    """Prompt for SSH credentials"""
    print(f"\n{Colors.YELLOW}{Colors.BOLD}🔑 SSH Credentials:{Colors.RESET}")
    
    username = input("SSH Username [123net]: ").strip() or "123net"
    password = getpass.getpass("SSH Password: ")
    
    # Ask if root password is different
    root_same = input("\nIs root password the same as SSH password? (yes/no) [yes]: ").strip().lower()
    
    if root_same in ['no', 'n']:
        root_password = getpass.getpass("Root Password: ")
    else:
        root_password = password
        print("  → Using SSH password for root")
    
    return username, password, root_password

def create_temp_config(username, password, root_password):
    """Create temporary config file with credentials"""
    config_content = f"""# Temporary credentials for deployment
FREEPBX_USER = "{username}"
FREEPBX_PASSWORD = "***REMOVED***"
FREEPBX_ROOT_PASSWORD = "***REMOVED***"
"""
    
    # Write to config.py
    with open("config.py", "w") as f:
        f.write(config_content)

def get_servers():
    """Prompt user for server list"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}🖥️  Server Selection:{Colors.RESET}")
    print(f"  {Colors.CYAN}1){Colors.RESET} Single server (enter IP)")
    print(f"  {Colors.CYAN}2){Colors.RESET} Multiple servers (comma-separated IPs)")
    print(f"  {Colors.CYAN}3){Colors.RESET} Use ProductionServers.txt (all 386 servers)")
    print(f"  {Colors.CYAN}4){Colors.RESET} Use custom file")
    
    choice = input("\nChoose option (1-4): ").strip()
    
    if choice == "1":
        server = input("Enter server IP: ").strip()
        return server
    elif choice == "2":
        servers = input("Enter comma-separated IPs: ").strip()
        return servers
    elif choice == "3":
        if os.path.exists("ProductionServers.txt"):
            confirm = input(f"⚠️  Deploy to ALL 386 production servers? (yes/no): ").strip().lower()
            if confirm == "yes":
                return "ProductionServers.txt"
            else:
                print("❌ Cancelled")
                return None
        else:
            print("❌ ProductionServers.txt not found")
            return None
    elif choice == "4":
        filename = input("Enter filename: ").strip()
        if os.path.exists(filename):
            return filename
        else:
            print(f"❌ File not found: {filename}")
            return None
    else:
        print("❌ Invalid choice")
        return None

def deploy_tools():
    """Deploy tools to servers"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  🚀 Deploy freePBX Tools")
    print(f"{'='*70}{Colors.RESET}")
    
    servers = get_servers()
    if not servers:
        return
    
    # Get credentials
    username, password, root_password = get_credentials()
    
    # Create temporary config
    create_temp_config(username, password, root_password)
    
    # Confirm deployment
    print(f"\n{Colors.YELLOW}📦 Ready to deploy to:{Colors.RESET} {Colors.CYAN}{servers}{Colors.RESET}")
    print(f"   {Colors.YELLOW}Username:{Colors.RESET} {Colors.CYAN}{username}{Colors.RESET}")
    confirm = input(f"{Colors.YELLOW}Continue with deployment? (yes/no):{Colors.RESET} ").strip().lower()
    
    if confirm != "yes":
        print(f"{Colors.RED}❌ Cancelled{Colors.RESET}")
        return
    
    # Run deployment
    print(f"\n{Colors.GREEN}{Colors.BOLD}🔄 Starting deployment...{Colors.RESET}\n")
    cmd = ["python", "deploy_freepbx_tools.py", "--servers", servers]
    subprocess.run(cmd)

def uninstall_tools():
    """Uninstall tools from servers"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  🗑️  Uninstall freePBX Tools")
    print(f"{'='*70}{Colors.RESET}")
    
    print(f"\n{Colors.RED}{Colors.BOLD}⚠️  WARNING:{Colors.RESET} This will remove:")
    print(f"  {Colors.YELLOW}•{Colors.RESET} /usr/local/123net/freepbx-tools/")
    print(f"  {Colors.YELLOW}•{Colors.RESET} /home/123net/freepbx-tools/")
    print(f"  {Colors.YELLOW}•{Colors.RESET} /home/123net/callflows/")
    print(f"  {Colors.YELLOW}•{Colors.RESET} All symlinks from /usr/local/bin/")
    print()
    
    servers = get_servers()
    if not servers:
        return
    
    # Get credentials
    username, password, root_password = get_credentials()
    
    # Create temporary config
    create_temp_config(username, password, root_password)
    
    # Double confirm uninstall
    print(f"\n{Colors.RED}{Colors.BOLD}🗑️  Ready to UNINSTALL from:{Colors.RESET} {Colors.CYAN}{servers}{Colors.RESET}")
    print(f"   {Colors.YELLOW}Username:{Colors.RESET} {Colors.CYAN}{username}{Colors.RESET}")
    confirm1 = input(f"{Colors.RED}Are you sure? (yes/no):{Colors.RESET} ").strip().lower()
    
    if confirm1 != "yes":
        print(f"{Colors.RED}❌ Cancelled{Colors.RESET}")
        return
    
    confirm2 = input(f"{Colors.RED}{Colors.BOLD}Type 'UNINSTALL' to confirm:{Colors.RESET} ").strip()
    
    if confirm2 != "UNINSTALL":
        print(f"{Colors.RED}❌ Cancelled{Colors.RESET}")
        return
    
    # Run uninstall
    print(f"\n{Colors.YELLOW}{Colors.BOLD}🔄 Starting uninstall...{Colors.RESET}\n")
    cmd = ["python", "deploy_uninstall_tools.py", "--servers", servers]
    subprocess.run(cmd)

def clean_deploy():
    """Uninstall then install - clean deployment"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  🔄 Clean Deployment (Uninstall + Install)")
    print(f"{'='*70}{Colors.RESET}")
    
    print(f"\n{Colors.YELLOW}This will:{Colors.RESET}")
    print("  1. Uninstall existing tools from selected servers")
    print("  2. Deploy fresh installation")
    print("  3. Preserve callflows directory and data")
    print()
    
    # Get target servers
    print(f"\n{Colors.YELLOW}{Colors.BOLD}Select target:{Colors.RESET}")
    print(f"  {Colors.CYAN}1.{Colors.RESET} Single server (IP address)")
    print(f"  {Colors.CYAN}2.{Colors.RESET} Multiple servers (from file)")
    print(f"  {Colors.CYAN}3.{Colors.RESET} Test server (69.39.69.102)")
    print(f"  {Colors.CYAN}4.{Colors.RESET} Production servers (ProductionServers.txt)")
    
    target = input(f"\n{Colors.YELLOW}Choice (1-4):{Colors.RESET} ").strip()
    
    servers = None
    if target == "1":
        servers = input(f"\n{Colors.YELLOW}Enter server IP:{Colors.RESET} ").strip()
    elif target == "2":
        file_path = input(f"\n{Colors.YELLOW}Enter file path:{Colors.RESET} ").strip()
        servers = file_path
    elif target == "3":
        servers = "69.39.69.102"
    elif target == "4":
        servers = "ProductionServers.txt"
    else:
        print(f"{Colors.RED}❌ Invalid choice{Colors.RESET}")
        return
    
    # Confirm
    print(f"\n{Colors.RED}{Colors.BOLD}⚠️  Warning:{Colors.RESET} This will uninstall and reinstall tools on:")
    print(f"  {Colors.CYAN}{servers}{Colors.RESET}")
    confirm = input(f"\n{Colors.YELLOW}Proceed? (yes/no):{Colors.RESET} ").strip().lower()
    
    if confirm != "yes":
        print(f"{Colors.RED}❌ Cancelled{Colors.RESET}")
        return
    
    # Get credentials
    username, password, root_password = get_credentials()
    
    # Create temporary config
    create_temp_config(username, password, root_password)
    
    # Step 1: Uninstall
    print(f"\n{Colors.CYAN}{Colors.BOLD}Step 1/2: Uninstalling...{Colors.RESET}")
    print("="*70)
    cmd = ["python", "deploy_uninstall_tools.py", "--servers", servers]
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print(f"\n{Colors.RED}❌ Uninstall failed. Aborting deployment.{Colors.RESET}")
        return
    
    print(f"\n{Colors.GREEN}✅ Uninstall complete{Colors.RESET}")
    
    # Step 2: Install
    print(f"\n{Colors.CYAN}{Colors.BOLD}Step 2/2: Installing...{Colors.RESET}")
    print("="*70)
    cmd = ["python", "deploy_freepbx_tools.py", "--servers", servers]
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Clean deployment completed successfully!{Colors.RESET}")
    else:
        print(f"\n{Colors.RED}❌ Installation failed.{Colors.RESET}")

def test_dashboard():
    """Test dashboard on test server"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  🧪 Test Dashboard")
    print(f"{'='*70}{Colors.RESET}")
    
    print(f"\n{Colors.YELLOW}📊 Testing dashboard on test server (69.39.69.102)...{Colors.RESET}")
    print(f"\n{Colors.GREEN}💡 To view dashboard manually:{Colors.RESET}")
    print(f"  {Colors.CYAN}1.{Colors.RESET} SSH: {Colors.MAGENTA}ssh 123net@69.39.69.102{Colors.RESET}")
    print(f"  {Colors.CYAN}2.{Colors.RESET} Run: {Colors.MAGENTA}freepbx-callflows{Colors.RESET}")
    print()
    
    confirm = input(f"{Colors.YELLOW}Run test deployment? (yes/no):{Colors.RESET} ").strip().lower()
    
    if confirm != "yes":
        print(f"{Colors.RED}❌ Cancelled{Colors.RESET}")
        return
    
    # Get credentials
    username, password, root_password = get_credentials()
    
    # Create temporary config
    create_temp_config(username, password, root_password)
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}🔄 Deploying to test server...{Colors.RESET}\n")
    cmd = ["python", "deploy_freepbx_tools.py", "--servers", "69.39.69.102"]
    subprocess.run(cmd)

def view_status():
    """View deployment status"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  📈 Deployment Status")
    print(f"{'='*70}{Colors.RESET}")
    
    print(f"\n{Colors.YELLOW}{Colors.BOLD}📋 Available Commands:{Colors.RESET}")
    print(f"  {Colors.GREEN}•{Colors.RESET} Deploy:    {Colors.MAGENTA}python deploy_freepbx_tools.py --servers <IP or file>{Colors.RESET}")
    print(f"  {Colors.GREEN}•{Colors.RESET} Uninstall: {Colors.MAGENTA}python deploy_uninstall_tools.py --servers <IP or file>{Colors.RESET}")
    print(f"  {Colors.GREEN}•{Colors.RESET} Test:      {Colors.MAGENTA}python test_dashboard.py{Colors.RESET}")
    print()
    
    print(f"{Colors.YELLOW}{Colors.BOLD}📂 Files:{Colors.RESET}")
    files = [
        "deploy_freepbx_tools.py",
        "deploy_uninstall_tools.py", 
        "ProductionServers.txt",
        "freepbx-tools/bin/freepbx_callflow_menu.py"
    ]
    
    for f in files:
        if os.path.exists(f):
            print(f"  {Colors.GREEN}✅{Colors.RESET} {Colors.CYAN}{f}{Colors.RESET}")
        else:
            print(f"  {Colors.RED}❌{Colors.RESET} {Colors.CYAN}{f}{Colors.RESET}")
    
    print()
    
    # Check credentials
    if os.path.exists("config.py"):
        print(f"{Colors.GREEN}🔑 Credentials: ✅ config.py exists{Colors.RESET}")
    else:
        print(f"{Colors.RED}🔑 Credentials: ❌ config.py missing{Colors.RESET}")
    
def main():
    """Main interactive loop"""
    while True:
        print_banner()
        print_menu()
        
        choice = input(f"{Colors.YELLOW}Choose option (1-6):{Colors.RESET} ").strip()
        
        if choice == "1":
            deploy_tools()
        elif choice == "2":
            uninstall_tools()
        elif choice == "3":
            clean_deploy()
        elif choice == "4":
            test_dashboard()
        elif choice == "5":
            view_status()
        elif choice == "6":
            print(f"\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{Colors.RED}❌ Invalid choice. Please enter 1-6.{Colors.RESET}\n")
        
        input(f"\n{Colors.YELLOW}Press Enter to continue...{Colors.RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}\n")
        sys.exit(0)
        sys.exit(0)
