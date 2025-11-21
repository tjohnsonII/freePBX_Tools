#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
print_header(text):
    Print a formatted section header.
print_success(text):
    Print a success message.
print_error(text):
    Print an error message.
print_warning(text):
    Print a warning message.
print_info(text):
    Print an informational message.
read_server_list(filename):
    Read a list of server IPs/hostnames from a file.
get_local_files():
    Get the list of local files to deploy.
deploy_to_server(server_ip, username, password, files, dry_run=False):
    Deploy files to a single server via SSH/SCP.
deploy_parallel(servers, username, password, files, max_workers=5, dry_run=False):
    Deploy to multiple servers in parallel using threads.
print_summary(results):
    Print a summary of deployment results.
main():
    Orchestrate the deployment process from CLI arguments.
"""
"""
deploy_freepbx_tools.py

Purpose:
    Deploys the FreePBX Tools suite to multiple FreePBX servers via SSH, automating file transfer, installation, and setup across a fleet. Supports parallel deployment, dry-run mode, and flexible credential sourcing.

Technical Overview:
    1. Loads server list from file or CLI args (CSV/TSV/IPs).
    2. Gathers all relevant files from LOCAL_SOURCE_DIR for deployment.
    3. Uses paramiko to SSH/SFTP into each server, uploading files to a temp directory.
    4. Runs bootstrap.sh and install.sh as root to complete installation.
    5. Supports parallel execution with ThreadPoolExecutor and dry-run mode for testing.

Variable Legend:
    REMOTE_INSTALL_DIR: Target directory on remote servers for installation.
    LOCAL_SOURCE_DIR: Local directory containing files to deploy.
    DEFAULT_USER, DEFAULT_PASSWORD, ROOT_PASSWORD: SSH credentials (from config.py or env).
    servers: List of server IPs/hostnames to deploy to.
    files: List of (local_path, rel_path) tuples for files to deploy.
    max_workers: Number of parallel deployment threads.
    dry_run: If True, only simulates deployment.
    result: Dict summarizing deployment outcome for a server.
    Colors: Class for ANSI color codes for terminal output.
    args: Parsed command-line arguments.

Script Flow:
    - Parse credentials from config.py or environment.
    - Parse server list from file or CLI args.
    - get_local_files(): Recursively collects all files to deploy, skipping test/docs.
    - deploy_to_server(): Handles SSH/SFTP, file upload, and install for one server.
    - deploy_parallel(): Runs deploy_to_server() in parallel for all servers.
    - print_summary(): Prints deployment results and summary.
    - main(): Orchestrates argument parsing, file gathering, deployment, and summary.

"""

import sys
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

try:
    import paramiko  # type: ignore
except ImportError:
    print("❌ Error: paramiko library not installed")
    print("Please install it with: pip install paramiko")
    sys.exit(1)

# Try to import credentials from config.py, fall back to environment variables
try:
    from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD
    DEFAULT_USER = FREEPBX_USER
    DEFAULT_PASSWORD = FREEPBX_PASSWORD
    ROOT_PASSWORD = FREEPBX_ROOT_PASSWORD
except ImportError:
    # Fall back to environment variables
    DEFAULT_USER = os.getenv("FREEPBX_USER", "123net")
    DEFAULT_PASSWORD = os.getenv("FREEPBX_PASSWORD", "")
    ROOT_PASSWORD = os.getenv("FREEPBX_ROOT_PASSWORD", "")
    
    if not DEFAULT_PASSWORD or not ROOT_PASSWORD:
        print("❌ Error: Credentials not found!")
        print("Either:")
        print("  1. Create config.py from config.example.py, OR")
        print("  2. Set environment variables: FREEPBX_PASSWORD and FREEPBX_ROOT_PASSWORD")
        sys.exit(1)

# Configuration
# IMPORTANT: Store credentials in environment variables or a secure config file
# Never commit passwords to git!
REMOTE_INSTALL_DIR = "/usr/local/123net/freepbx-tools"
LOCAL_SOURCE_DIR = "freepbx-tools"

class Colors:
    """
    ANSI color codes for terminal output (for pretty printing status/info).
    """
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """
    Print a formatted section header in the terminal.
    """
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.RESET}")

def print_success(text):
    """
    Print a green success message.
    """
    print(f"{Colors.GREEN}[OK] {text}{Colors.RESET}")

def print_error(text):
    """
    Print a red error message.
    """
    print(f"{Colors.RED}[ERROR] {text}{Colors.RESET}")

def print_warning(text):
    """
    Print a yellow warning message.
    """
    print(f"{Colors.YELLOW}[WARNING] {text}{Colors.RESET}")

def print_info(text):
    """
    Print a cyan info message.
    """
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.RESET}")

def read_server_list(filename):
    """
    Read server IPs/hostnames from a file (CSV/TSV/one-per-line).
    Skips comments and blank lines. Returns list of IPs.
    """
    servers = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    # Handle CSV format - take first column
                    ip = line.split(',')[0].strip()
                    if ip:
                        servers.append(ip)
        return servers
    except FileNotFoundError:
        print_error(f"Server list file not found: {filename}")
        return []
    except Exception as e:
        print_error(f"Error reading server list: {e}")
        return []

def get_local_files():
    """
    Recursively collect all files to deploy from LOCAL_SOURCE_DIR.
    Skips __pycache__, .git, .vscode, docs, and test files.
    Returns: List of (local_path, rel_path) tuples.
    """
    files_to_deploy = []
    
    # Make source directory absolute
    source_dir = os.path.abspath(LOCAL_SOURCE_DIR)
    
    if not os.path.exists(source_dir):
        print_error(f"Source directory not found: {source_dir}")
        return []
    
    # Get all files in the source directory
    for root, dirs, files in os.walk(source_dir):
        # Skip __pycache__, .git, .vscode, and 123net_internal_docs directories
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', '.vscode', '123net_internal_docs']]
        
        for file in files:
            # Skip markdown files (documentation) and test files
            if file.startswith('test_') or file == 'version_outliers.csv':
                continue
            
            # Only include essential files
            if file.endswith(('.py', '.sh', '.json', '.txt')) and not file.endswith('.md'):
                local_path = os.path.join(root, file)
                # Create relative path for remote - use forward slashes for Unix
                rel_path = os.path.relpath(local_path, source_dir).replace('\\', '/')
                files_to_deploy.append((local_path, rel_path))
    
    return files_to_deploy

def deploy_to_server(server_ip, username, password, files, dry_run=False):
    """
    Deploy all files to a single server via SSH/SFTP.
    - Connects as username/password using paramiko
    - Uploads files to temp directory
    - Runs bootstrap.sh and install.sh as root
    - Returns result dict summarizing outcome
    """
    result = {
        'server': server_ip,
        'success': False,
        'message': '',
        'files_deployed': 0
    }
    
    print(f"\n{Colors.BOLD}[{server_ip}]{Colors.RESET} Starting deployment...")
    
    if dry_run:
        print_info(f"[{server_ip}] DRY RUN - Would deploy {len(files)} files")
        result['success'] = True
        result['message'] = 'Dry run completed'
        result['files_deployed'] = len(files)
        return result
    
    # Connect to server
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"[{server_ip}] Connecting...")
        ssh.connect(
            server_ip,
            username=username,
            password=password,
            timeout=15,
            banner_timeout=15
        )
        print_success(f"[{server_ip}] Connected")
        
        # Create temporary upload directory in user's home
        temp_dir = "/home/123net/freepbx-tools"
        print(f"[{server_ip}] Creating temporary directory: {temp_dir}")
        stdin, stdout, stderr = ssh.exec_command(f"rm -rf {temp_dir} && mkdir -p {temp_dir}/bin")
        stdout.channel.recv_exit_status()
        
        # Upload files to temp directory
        sftp = ssh.open_sftp()
        files_uploaded = 0
        
        print(f"[{server_ip}] Uploading {len(files)} files...")
        for local_path, rel_path in files:
            # Use forward slashes for Unix paths
            remote_path = f"{temp_dir}/{rel_path}"
            remote_dir = '/'.join(remote_path.split('/')[:-1])
            
            # Create remote directory if needed
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_dir}")
                stdout.channel.recv_exit_status()
            
            # Upload file
            try:
                with open(local_path, 'rb') as f:
                    sftp.putfo(f, remote_path)
                # Make shell scripts executable
                if local_path.endswith('.sh'):
                    sftp.chmod(remote_path, 0o755)
                files_uploaded += 1
            except Exception as e:
                print_warning(f"[{server_ip}] Failed to upload {rel_path}: {e}")
                continue
        
        sftp.close()
        print_success(f"[{server_ip}] Uploaded {files_uploaded} files")
        
        # Now run the installation sequence as root
        # 1. Switch to root
        # 2. cd freepbx-tools
        # 3. bash bootstrap.sh
        # 4. ./install.sh
        
        print(f"[{server_ip}] Running installation as root...")
        
        # Use su root to switch to root, then run commands in that session
        # This mimics the manual process: su root, enter password, run commands
        install_commands = f"""cd {temp_dir}
su root << 'ROOTEOF'
{ROOT_PASSWORD}
bash bootstrap.sh
./install.sh
exit
ROOTEOF
"""
        
        stdin, stdout, stderr = ssh.exec_command(install_commands)
        exit_code = stdout.channel.recv_exit_status()
        
        install_output = stdout.read().decode()
        install_errors = stderr.read().decode()
        
        if install_output:
            print(f"[{server_ip}] Installation output:\n{install_output}")
        if install_errors:
            print(f"[{server_ip}] Installation errors:\n{install_errors}")

        
        if install_output:
            print(f"[{server_ip}] Installation output:\n{install_output}")
        if install_errors:
            print(f"[{server_ip}] Installation errors:\n{install_errors}")
        
        # Check for success indicators in output rather than relying on exit code
        # Exit code can be 1 due to password prompts but installation still succeeds
        if "Installed 123NET FreePBX Tools" in install_output or "symlinks created" in install_output.lower():
            print_success(f"[{server_ip}] Installation completed successfully")
            result['success'] = True
        elif exit_code == 0:
            print_success(f"[{server_ip}] Installation completed successfully")
            result['success'] = True
        else:
            print_warning(f"[{server_ip}] Installation may have issues (exit code {exit_code})")
            result['success'] = False
        
        result['files_deployed'] = files_uploaded
        result['message'] = f'Deployed {files_uploaded} files'
        
    except paramiko.AuthenticationException:
        result['message'] = 'Authentication failed'
        print_error(f"[{server_ip}] Authentication failed")
    except paramiko.SSHException as e:
        result['message'] = f'SSH error: {str(e)}'
        print_error(f"[{server_ip}] SSH error: {e}")
    except Exception as e:
        result['message'] = f'Error: {str(e)}'
        print_error(f"[{server_ip}] Deployment failed: {e}")
    finally:
        ssh.close()
    
    return result

def deploy_parallel(servers, username, password, files, max_workers=5, dry_run=False):
    """
    Deploy to multiple servers in parallel using ThreadPoolExecutor.
    Prints progress and collects results for summary.
    """
    print_header(f"Deploying to {len(servers)} servers")
    print(f"{Colors.CYAN}Files to deploy:{Colors.RESET} {Colors.BOLD}{len(files)}{Colors.RESET}")
    print(f"{Colors.CYAN}Max parallel workers:{Colors.RESET} {Colors.BOLD}{max_workers}{Colors.RESET}")
    if dry_run:
        print_warning("DRY RUN MODE - No actual changes will be made")
    print()
    
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all deployment tasks
        future_to_server = {
            executor.submit(deploy_to_server, server, username, password, files, dry_run): server
            for server in servers
        }
        
        # Process results as they complete
        for future in as_completed(future_to_server):
            server = future_to_server[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print_error(f"[{server}] Unexpected error: {e}")
                results.append({
                    'server': server,
                    'success': False,
                    'message': str(e),
                    'files_deployed': 0
                })
    
    return results

def print_summary(results):
    """
    Print deployment summary, showing successful and failed deployments.
    """
    print_header("Deployment Summary")
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"\n{Colors.BOLD}Total servers: {len(results)}{Colors.RESET}")
    if successful:
        print_success(f"Successful: {len(successful)}")
    if failed:
        print_error(f"Failed: {len(failed)}")
    
    if successful:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Successful Deployments:{Colors.RESET}")
        for r in successful:
            files_info = f"({r['files_deployed']} files)" if r['files_deployed'] > 0 else ""
            print(f"  {Colors.GREEN}•{Colors.RESET} {Colors.CYAN}{r['server']}:{Colors.RESET} {r['message']} {Colors.YELLOW}{files_info}{Colors.RESET}")
    
    if failed:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ Failed Deployments:{Colors.RESET}")
        for r in failed:
            print(f"  {Colors.RED}•{Colors.RESET} {Colors.CYAN}{r['server']}:{Colors.RESET} {Colors.RED}{r['message']}{Colors.RESET}")

def main():
    """
    Main entry point for the deployment script.
    - Parses CLI arguments for server list, credentials, and options
    - Gathers files to deploy
    - Runs deployment in parallel
    - Prints summary and exits with error code if any failures
    """
    parser = argparse.ArgumentParser(
        description='Deploy FreePBX Tools to multiple servers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy to servers in ProductionServers.txt
  python deploy_freepbx_tools.py ProductionServers.txt
  
  # Dry run to see what would be deployed
  python deploy_freepbx_tools.py ProductionServers.txt --dry-run
  
  # Deploy to specific servers
  python deploy_freepbx_tools.py --servers 69.39.69.102 10.0.0.5
  
  # Use custom credentials
  python deploy_freepbx_tools.py servers.txt --user admin --password secret
        """
    )
    parser.add_argument('server_file', nargs='?', help='File containing server IPs (one per line)')
    parser.add_argument('--servers', nargs='+', help='Specify server IPs directly')
    parser.add_argument('--user', default=DEFAULT_USER, help=f'SSH username (default: {DEFAULT_USER})')
    parser.add_argument('--password', default=DEFAULT_PASSWORD, help='SSH password')
    parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deployed without making changes')
    args = parser.parse_args()
    # Get list of servers
    servers = []
    if args.servers:
        servers = args.servers
    elif args.server_file:
        servers = read_server_list(args.server_file)
    else:
        parser.print_help()
        sys.exit(1)
    if not servers:
        print_error("No servers specified")
        sys.exit(1)
    # Get files to deploy
    files = get_local_files()
    if not files:
        print_error("No files found to deploy")
        sys.exit(1)
    print_header("FreePBX Tools Deployment")
    print(f"Source: {LOCAL_SOURCE_DIR}")
    print(f"Target: {REMOTE_INSTALL_DIR}")
    print(f"Servers: {len(servers)}")
    # Start deployment
    start_time = time.time()
    results = deploy_parallel(servers, args.user, args.password, files, args.workers, args.dry_run)
    elapsed = time.time() - start_time
    # Print summary
    print_summary(results)
    print(f"\nTotal time: {elapsed:.1f} seconds")
    # Exit with error code if any deployments failed
    failed_count = len([r for r in results if not r['success']])
    sys.exit(1 if failed_count > 0 else 0)

if __name__ == "__main__":
    main()
