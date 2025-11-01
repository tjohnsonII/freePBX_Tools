#!/usr/bin/env python3
"""
FreePBX Tools Deployment Script
Deploys tools to multiple FreePBX servers via SSH
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
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """Print a formatted header"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.RESET}")

def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}[OK] {text}{Colors.RESET}")

def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}[ERROR] {text}{Colors.RESET}")

def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}[WARNING] {text}{Colors.RESET}")

def print_info(text):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.RESET}")

def read_server_list(filename):
    """Read server IPs from file"""
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
    """Get list of files to deploy"""
    files_to_deploy = []
    
    # Make source directory absolute
    source_dir = os.path.abspath(LOCAL_SOURCE_DIR)
    
    if not os.path.exists(source_dir):
        print_error(f"Source directory not found: {source_dir}")
        return []
    
    # Get all files in the source directory
    for root, dirs, files in os.walk(source_dir):
        # Skip __pycache__ and .git directories
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', '.vscode']]
        
        for file in files:
            if file.endswith(('.py', '.sh', '.json', '.txt', '.md')):
                local_path = os.path.join(root, file)
                # Create relative path for remote - use forward slashes for Unix
                rel_path = os.path.relpath(local_path, source_dir).replace('\\', '/')
                files_to_deploy.append((local_path, rel_path))
    
    return files_to_deploy

def deploy_to_server(server_ip, username, password, files, dry_run=False):
    """Deploy files to a single server"""
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
        
        # Execute commands using sudo with root password
        install_commands = f"""
cd {temp_dir}
echo '{ROOT_PASSWORD}' | su -c 'bash bootstrap.sh' root
echo '{ROOT_PASSWORD}' | su -c './install.sh' root
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
        
        if exit_code == 0:
            print_success(f"[{server_ip}] Installation completed successfully")
            result['success'] = True
        else:
            print_warning(f"[{server_ip}] Installation completed with exit code {exit_code}")
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
    """Deploy to multiple servers in parallel"""
    print_header(f"Deploying to {len(servers)} servers")
    print(f"Files to deploy: {len(files)}")
    print(f"Max parallel workers: {max_workers}")
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
    """Print deployment summary"""
    print_header("Deployment Summary")
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"\nTotal servers: {len(results)}")
    print_success(f"Successful: {len(successful)}")
    if failed:
        print_error(f"Failed: {len(failed)}")
    
    if successful:
        print(f"\n{Colors.GREEN}✅ Successful Deployments:{Colors.RESET}")
        for r in successful:
            print(f"  • {r['server']}: {r['message']} ({r['files_deployed']} files)")
    
    if failed:
        print(f"\n{Colors.RED}❌ Failed Deployments:{Colors.RESET}")
        for r in failed:
            print(f"  • {r['server']}: {r['message']}")

def main():
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
