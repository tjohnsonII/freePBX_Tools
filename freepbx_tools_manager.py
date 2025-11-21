#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
print_banner():
    Print the main banner for the tool.
print_menu():
    Print the interactive menu for user selection.
get_credentials():
    Prompt for and return user credentials.
create_temp_config(username, password, root_password):
    Create a temporary config file with credentials.
get_servers():
    Retrieve the list of servers to manage.
deploy_tools():
    Deploy FreePBX tools to selected servers.
uninstall_tools():
    Uninstall FreePBX tools from selected servers.
clean_deploy():
    Clean up deployment artifacts and temp files.
test_dashboard():
    Run dashboard integration tests.
view_status():
    View deployment or server status.
ssh_to_server():
    Open an SSH session to a selected server.
phone_config_analyzer():
    Launch the phone configuration analyzer tool.
main():
    Orchestrate the interactive menu and user actions.
"""
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
    print(f"  {Colors.CYAN}6){Colors.RESET} 🔌 SSH into a server")
    print(f"  {Colors.CYAN}7){Colors.RESET} 📱 Phone Config Analyzer")
    print(f"  {Colors.CYAN}8){Colors.RESET} Exit")
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

def ssh_to_server():
    """SSH into a server with password authentication"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  🔌 SSH Connection")
    print(f"{'='*70}{Colors.RESET}")
    
    # Get server IP
    print(f"\n{Colors.YELLOW}Enter target server:{Colors.RESET}")
    server_ip = input("Server IP: ").strip()
    
    if not server_ip:
        print(f"{Colors.RED}❌ Server IP required{Colors.RESET}")
        return
    
    # Get credentials
    print(f"\n{Colors.YELLOW}{Colors.BOLD}🔑 SSH Credentials:{Colors.RESET}")
    username = input("Username [123net]: ").strip() or "123net"
    password = getpass.getpass("Password: ")
    
    if not password:
        print(f"{Colors.RED}❌ Password required{Colors.RESET}")
        return
    
    print(f"\n{Colors.GREEN}🔌 Connecting to {Colors.MAGENTA}{username}@{server_ip}{Colors.RESET}...")
    print(f"{Colors.YELLOW}💡 Tip: Type 'exit' to disconnect{Colors.RESET}\n")
    
    # Use sshpass if available, otherwise provide instructions
    try:
        # Check if sshpass is available (works on Linux/WSL)
        which_result = subprocess.run(["which", "sshpass"], 
                                     capture_output=True, 
                                     text=True,
                                     shell=False)
        
        if which_result.returncode == 0:
            # sshpass is available - use it
            cmd = [
                "sshpass", "-p", password,
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                f"{username}@{server_ip}"
            ]
            subprocess.run(cmd)
        else:
            raise FileNotFoundError("sshpass not found")
            
    except (FileNotFoundError, subprocess.SubprocessError):
        # sshpass not available - try different approach
        print(f"{Colors.YELLOW}⚠️  sshpass not available, trying alternative method...{Colors.RESET}\n")
        
        # On Windows, try using PowerShell with plink (PuTTY)
        if sys.platform == "win32":
            try:
                # Try plink (PuTTY command-line)
                cmd = [
                    "plink",
                    "-ssh",
                    "-pw", password,
                    f"{username}@{server_ip}"
                ]
                subprocess.run(cmd)
            except FileNotFoundError:
                # No plink either - provide manual instructions
                print(f"{Colors.RED}❌ Neither sshpass nor plink found{Colors.RESET}")
                print(f"\n{Colors.YELLOW}{Colors.BOLD}📋 Manual Connection Instructions:{Colors.RESET}")
                print(f"\n{Colors.CYAN}Option 1 - Use PuTTY:{Colors.RESET}")
                print(f"  1. Open PuTTY")
                print(f"  2. Enter: {Colors.MAGENTA}{server_ip}{Colors.RESET}")
                print(f"  3. Username: {Colors.MAGENTA}{username}{Colors.RESET}")
                print(f"  4. Password: {Colors.MAGENTA}<provided>{Colors.RESET}")
                
                print(f"\n{Colors.CYAN}Option 2 - Use native SSH:{Colors.RESET}")
                print(f"  {Colors.MAGENTA}ssh {username}@{server_ip}{Colors.RESET}")
                print(f"  (Enter password when prompted)")
                
                print(f"\n{Colors.CYAN}Option 3 - Install sshpass (recommended):{Colors.RESET}")
                print(f"  On WSL/Linux: {Colors.MAGENTA}sudo apt-get install sshpass{Colors.RESET}")
                print(f"  On Windows: {Colors.MAGENTA}choco install putty{Colors.RESET}")
        else:
            # On Linux/Mac without sshpass - use regular ssh
            print(f"{Colors.YELLOW}💡 Falling back to interactive SSH...{Colors.RESET}")
            print(f"{Colors.YELLOW}Password: {password}{Colors.RESET}\n")
            cmd = ["ssh", f"{username}@{server_ip}"]
            subprocess.run(cmd)

def phone_config_analyzer():
    """Run Phone Configuration Analyzer"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  📱 Phone Configuration Analyzer")
    print(f"{'='*70}{Colors.RESET}")
    
    print(f"\n{Colors.YELLOW}{Colors.BOLD}What would you like to analyze?{Colors.RESET}")
    print(f"  {Colors.CYAN}1){Colors.RESET} Single config file")
    print(f"  {Colors.CYAN}2){Colors.RESET} Directory of config files")
    print(f"  {Colors.CYAN}3){Colors.RESET} Run interactive demo")
    print(f"  {Colors.CYAN}4){Colors.RESET} View documentation")
    print(f"  {Colors.CYAN}5){Colors.RESET} Back to main menu")
    print()
    
    choice = input(f"{Colors.YELLOW}Choose option (1-5):{Colors.RESET} ").strip()
    
    if choice == "1":
        # Single file analysis
        file_path = input(f"\n{Colors.YELLOW}Enter config file path:{Colors.RESET} ").strip()
        
        if not os.path.exists(file_path):
            print(f"{Colors.RED}❌ File not found: {file_path}{Colors.RESET}")
            return
        
        # Ask about export
        export_json = input(f"{Colors.YELLOW}Export to JSON? (yes/no) [no]:{Colors.RESET} ").strip().lower()
        export_csv = input(f"{Colors.YELLOW}Export to CSV? (yes/no) [no]:{Colors.RESET} ").strip().lower()
        
        # Build command
        cmd = ["python", "phone_config_analyzer.py", file_path]
        
        if export_json in ['yes', 'y']:
            json_file = input(f"{Colors.YELLOW}JSON filename [analysis.json]:{Colors.RESET} ").strip() or "analysis.json"
            cmd.extend(["--json", json_file])
        
        if export_csv in ['yes', 'y']:
            csv_file = input(f"{Colors.YELLOW}CSV filename [analysis.csv]:{Colors.RESET} ").strip() or "analysis.csv"
            cmd.extend(["--csv", csv_file])
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}🔍 Analyzing config file...{Colors.RESET}\n")
        subprocess.run(cmd)
        
    elif choice == "2":
        # Directory analysis
        dir_path = input(f"\n{Colors.YELLOW}Enter directory path:{Colors.RESET} ").strip()
        
        if not os.path.exists(dir_path):
            print(f"{Colors.RED}❌ Directory not found: {dir_path}{Colors.RESET}")
            return
        
        if not os.path.isdir(dir_path):
            print(f"{Colors.RED}❌ Not a directory: {dir_path}{Colors.RESET}")
            return
        
        # Build command
        cmd = ["python", "phone_config_analyzer.py", "--directory", dir_path]
        
        # Ask about batch export
        export = input(f"{Colors.YELLOW}Export each config to JSON? (yes/no) [no]:{Colors.RESET} ").strip().lower()
        if export in ['yes', 'y']:
            output_dir = input(f"{Colors.YELLOW}Output directory [reports]:{Colors.RESET} ").strip() or "reports"
            
            # Create output directory
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"{Colors.GREEN}✅ Created directory: {output_dir}{Colors.RESET}")
            
            # Note: We'll need to enhance the analyzer for batch JSON export
            # For now, just analyze the directory
            print(f"\n{Colors.YELLOW}💡 Note: Batch JSON export can be done with a shell script{Colors.RESET}")
            print(f"{Colors.CYAN}Example:{Colors.RESET}")
            print(f"  for f in {dir_path}/*.cfg; do")
            print(f"    python phone_config_analyzer.py \"$f\" --json {output_dir}/$(basename \"$f\" .cfg).json")
            print(f"  done")
            print()
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}🔍 Analyzing directory...{Colors.RESET}\n")
        subprocess.run(cmd)
        
    elif choice == "3":
        # Run demo
        demo_file = "phone_config_analyzer_demo.py"
        
        if not os.path.exists(demo_file):
            print(f"{Colors.RED}❌ Demo file not found: {demo_file}{Colors.RESET}")
            print(f"{Colors.YELLOW}💡 Make sure {demo_file} is in the current directory{Colors.RESET}")
            return
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎭 Running interactive demo...{Colors.RESET}\n")
        subprocess.run(["python", demo_file])
        
    elif choice == "4":
        # View documentation
        print(f"\n{Colors.CYAN}{Colors.BOLD}📚 Documentation Files:{Colors.RESET}\n")
        
        docs = [
            ("PHONE_CONFIG_ANALYZER_README.md", "Comprehensive documentation"),
            ("PHONE_CONFIG_ANALYZER_QUICKREF.md", "Quick reference guide"),
            ("PHONE_CONFIG_ANALYZER_SUMMARY.md", "Project overview")
        ]
        
        for doc_file, description in docs:
            if os.path.exists(doc_file):
                print(f"  {Colors.GREEN}✅{Colors.RESET} {Colors.CYAN}{doc_file}{Colors.RESET}")
                print(f"     {Colors.YELLOW}{description}{Colors.RESET}")
            else:
                print(f"  {Colors.RED}❌{Colors.RESET} {Colors.CYAN}{doc_file}{Colors.RESET}")
            print()
        
        view_doc = input(f"{Colors.YELLOW}Open a document? Enter filename or 'no':{Colors.RESET} ").strip()
        
        if view_doc and view_doc.lower() != 'no' and os.path.exists(view_doc):
            # Try to open with default viewer
            if sys.platform == "win32":
                os.startfile(view_doc)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", view_doc])
            else:  # Linux
                subprocess.run(["xdg-open", view_doc])
            
            print(f"{Colors.GREEN}✅ Opened {view_doc}{Colors.RESET}")
        
    elif choice == "5":
        return
    else:
        print(f"{Colors.RED}❌ Invalid choice{Colors.RESET}")
    
def main():
    """Main interactive loop"""
    while True:
        print_banner()
        print_menu()
        
        choice = input(f"{Colors.YELLOW}Choose option (1-8):{Colors.RESET} ").strip()
        
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
            ssh_to_server()
        elif choice == "7":
            phone_config_analyzer()
        elif choice == "8":
            print(f"\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{Colors.RED}❌ Invalid choice. Please enter 1-8.{Colors.RESET}\n")
        
        input(f"\n{Colors.YELLOW}Press Enter to continue...{Colors.RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}\n")
        sys.exit(0)
        sys.exit(0)
