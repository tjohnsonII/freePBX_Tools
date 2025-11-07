#!/usr/bin/env python3
"""
FreePBX Tools Manager - Interactive deployment and uninstall tool
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
    print("    ______              ____  ______  __  __")
    print("   / ____/_______  ____/ __ \\/ __ ) \\/ / / /")
    print("  / /_  / ___/ _ \\/ __  / / / / __  |\\  /_/ / ")
    print(" / __/ / /  /  __/ /_/ / /_/ / /_/ / / /__/ /  ")
    print("/_/   /_/   \\___/\\____/_____/_____/ /_/   /_/   ")
    print(f"{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"              🛠️  FreePBX Tools Manager  🛠️")
    print(f"{'='*70}{Colors.RESET}")

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
    print("\n" + "="*70)
    print("  🚀 Deploy FreePBX Tools")
    print("="*70)
    
    servers = get_servers()
    if not servers:
        return
    
    # Get credentials
    username, password, root_password = get_credentials()
    
    # Create temporary config
    create_temp_config(username, password, root_password)
    
    # Confirm deployment
    print(f"\n📦 Ready to deploy to: {servers}")
    print(f"   Username: {username}")
    confirm = input("Continue with deployment? (yes/no): ").strip().lower()
    
    if confirm != "yes":
        print("❌ Cancelled")
        return
    
    # Run deployment
    print("\n🔄 Starting deployment...\n")
    cmd = ["python", "deploy_freepbx_tools.py", "--servers", servers]
    subprocess.run(cmd)

def uninstall_tools():
    """Uninstall tools from servers"""
    print("\n" + "="*70)
    print("  🗑️  Uninstall FreePBX Tools")
    print("="*70)
    
    print("\n⚠️  WARNING: This will remove:")
    print("  • /usr/local/123net/freepbx-tools/")
    print("  • /home/123net/freepbx-tools/")
    print("  • /home/123net/callflows/")
    print("  • All symlinks from /usr/local/bin/")
    print()
    
    servers = get_servers()
    if not servers:
        return
    
    # Get credentials
    username, password, root_password = get_credentials()
    
    # Create temporary config
    create_temp_config(username, password, root_password)
    
    # Double confirm uninstall
    print(f"\n🗑️  Ready to UNINSTALL from: {servers}")
    print(f"   Username: {username}")
    confirm1 = input("Are you sure? (yes/no): ").strip().lower()
    
    if confirm1 != "yes":
        print("❌ Cancelled")
        return
    
    confirm2 = input("Type 'UNINSTALL' to confirm: ").strip()
    
    if confirm2 != "UNINSTALL":
        print("❌ Cancelled")
        return
    
    # Run uninstall
    print("\n🔄 Starting uninstall...\n")
    cmd = ["python", "deploy_uninstall_tools.py", "--servers", servers]
    subprocess.run(cmd)

def clean_deploy():
    """Uninstall then install - clean deployment"""
    print("\n" + "="*70)
    print("  🔄 Clean Deployment (Uninstall + Install)")
    print("="*70)
    
    print(f"\n{Colors.YELLOW}This will:{Colors.RESET}")
    print("  1. Uninstall existing tools from selected servers")
    print("  2. Deploy fresh installation")
    print("  3. Preserve callflows directory and data")
    print()
    
    # Get target servers
    print(f"\n{Colors.YELLOW}Select target:{Colors.RESET}")
    print("  1. Single server (IP address)")
    print("  2. Multiple servers (from file)")
    print("  3. Test server (69.39.69.102)")
    print("  4. Production servers (ProductionServers.txt)")
    
    target = input("\nChoice (1-4): ").strip()
    
    servers = None
    if target == "1":
        servers = input("\nEnter server IP: ").strip()
    elif target == "2":
        file_path = input("\nEnter file path: ").strip()
        servers = file_path
    elif target == "3":
        servers = "69.39.69.102"
    elif target == "4":
        servers = "ProductionServers.txt"
    else:
        print("❌ Invalid choice")
        return
    
    # Confirm
    print(f"\n{Colors.RED}{Colors.BOLD}⚠️  Warning:{Colors.RESET} This will uninstall and reinstall tools on:")
    print(f"  {servers}")
    confirm = input("\nProceed? (yes/no): ").strip().lower()
    
    if confirm != "yes":
        print("❌ Cancelled")
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
    print("\n" + "="*70)
    print("  🧪 Test Dashboard")
    print("="*70)
    
    print("\n📊 Testing dashboard on test server (69.39.69.102)...")
    print("\n💡 To view dashboard manually:")
    print("  1. SSH: ssh 123net@69.39.69.102")
    print("  2. Run: freepbx-callflows")
    print()
    
    confirm = input("Run test deployment? (yes/no): ").strip().lower()
    
    if confirm != "yes":
        print("❌ Cancelled")
        return
    
    # Get credentials
    username, password, root_password = get_credentials()
    
    # Create temporary config
    create_temp_config(username, password, root_password)
    
    print("\n🔄 Deploying to test server...\n")
    cmd = ["python", "deploy_freepbx_tools.py", "--servers", "69.39.69.102"]
    subprocess.run(cmd)

def view_status():
    """View deployment status"""
    print("\n" + "="*70)
    print("  📈 Deployment Status")
    print("="*70)
    
    print("\n📋 Available Commands:")
    print("  • Deploy:    python deploy_freepbx_tools.py --servers <IP or file>")
    print("  • Uninstall: python deploy_uninstall_tools.py --servers <IP or file>")
    print("  • Test:      python test_dashboard.py")
    print()
    
    print("📂 Files:")
    files = [
        "deploy_freepbx_tools.py",
        "deploy_uninstall_tools.py", 
        "ProductionServers.txt",
        "freepbx-tools/bin/freepbx_callflow_menu.py"
    ]
    
    for f in files:
        exists = "✅" if os.path.exists(f) else "❌"
        print(f"  {exists} {f}")
    
    print()
    
    # Check credentials
    if os.path.exists("config.py"):
        print("🔑 Credentials: ✅ config.py exists")
    else:
        print("🔑 Credentials: ❌ config.py missing")
    
    print()

def main():
    """Main interactive loop"""
    while True:
        print_banner()
        print_menu()
        
        choice = input("Choose option (1-6): ").strip()
        
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
            print("\n👋 Goodbye!\n")
            sys.exit(0)
        else:
            print("\n❌ Invalid choice. Please enter 1-6.\n")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!\n")
        sys.exit(0)
