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
import re

try:
    import paramiko  # type: ignore
except ImportError:
    print("❌ Error: paramiko library not installed")
    print("Please install it with: pip install paramiko")
    sys.exit(1)

def _is_placeholder_secret(value: str) -> bool:
    v = (value or "").strip()
    return v in {"***REMOVED***", "REDACTED", "<REDACTED>", ""}


def load_credentials():
    """Load credentials.

    Precedence:
      1) Environment variables (FREEPBX_*)
      2) config.py

    Note: If password is blank, SSH key/agent auth may still work.
    """
    env_user = os.getenv("FREEPBX_USER", "").strip()
    env_pass = os.getenv("FREEPBX_PASSWORD", "")
    env_root = os.getenv("FREEPBX_ROOT_PASSWORD", "")

    if env_user or env_pass or env_root:
        return {
            "user": env_user or "123net",
            "password": env_pass,
            "root_password": env_root,
            "source": "env",
        }

    try:
        from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD  # type: ignore
        return {
            "user": str(FREEPBX_USER),
            "password": str(FREEPBX_PASSWORD),
            "root_password": str(FREEPBX_ROOT_PASSWORD),
            "source": "config.py",
        }
    except Exception:
        return {
            "user": "123net",
            "password": "",
            "root_password": "",
            "source": "none",
        }


_creds = load_credentials()
DEFAULT_USER = _creds["user"]
DEFAULT_PASSWORD = _creds["password"]
ROOT_PASSWORD = _creds["root_password"]

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


def _run_shell_scripted(ssh, script_lines, timeout=300):
    """Run a small scripted interaction over an interactive shell.

    Returns: (exit_status, combined_output)
    """
    chan = ssh.invoke_shell()
    chan.settimeout(2.0)

    output_parts = []
    start = time.time()

    def _drain():
        buf = ""
        while chan.recv_ready():
            chunk = chan.recv(4096).decode("utf-8", errors="ignore")
            if not chunk:
                break
            buf += chunk
        if buf:
            output_parts.append(buf)
        return buf

    # Best effort: clear banner
    _drain()

    def _send(line: str) -> None:
        chan.send((line + "\n").encode("utf-8"))

    for line in script_lines:
        if time.time() - start > timeout:
            raise TimeoutError("Timed out running remote scripted shell")
        _send(line)
        time.sleep(0.2)
        _drain()

    # Wait for completion marker or shell close
    marker = "__FREEPBXTOOLS_DONE__"
    _send(f"echo {marker}; echo __FREEPBXTOOLS_RC__=$?")

    combined = ""
    while time.time() - start <= timeout:
        time.sleep(0.2)
        _drain()
        combined = "".join(output_parts)
        if marker in combined:
            break

    # Try to exit cleanly
    try:
        _send("exit")
    except Exception:
        pass

    return 0, "".join(output_parts)


def _run_as_root_via_su(ssh, root_password, workdir, commands, timeout=600, stream_output=False, stream_prefix=""):
    """Run commands as root using 'su' in an interactive PTY shell.

    This is more reliable than exec_command because 'su' reads the password from a TTY.
    """
    if not root_password:
        raise ValueError("Root password is required for su-based installation")

    chan = ssh.invoke_shell()
    chan.settimeout(2.0)
    start = time.time()
    out = []

    def _stream(buf: str) -> None:
        if not stream_output or not buf:
            return
        # Prefix each line to keep multi-host output readable.
        if stream_prefix:
            for chunk in buf.splitlines(True):
                sys.stdout.write(stream_prefix + chunk)
        else:
            sys.stdout.write(buf)
        sys.stdout.flush()

    def _drain():
        buf = ""
        while chan.recv_ready():
            chunk = chan.recv(4096).decode("utf-8", errors="ignore")
            if not chunk:
                break
            buf += chunk
        if buf:
            out.append(buf)
            _stream(buf)
        return buf

    def _wait_for(patterns, max_wait=30, heartbeat_label: str = ""):
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        buf = ""
        end = time.time() + max_wait
        last_heartbeat = 0.0
        while time.time() < end:
            time.sleep(0.2)
            buf += _drain()
            for c in compiled:
                if c.search(buf):
                    return True
            if time.time() - start > timeout:
                raise TimeoutError("Timed out waiting for remote prompt")

            # Periodic heartbeat so long-running installs don't look hung.
            if stream_output and heartbeat_label:
                now = time.time()
                if (now - last_heartbeat) > 20.0:
                    last_heartbeat = now
                    sys.stdout.write(f"{stream_prefix}... {heartbeat_label} ...\n")
                    sys.stdout.flush()
        return False

    # Clear banner
    _drain()

    def _send(line: str) -> None:
        chan.send((line + "\n").encode("utf-8"))

    _send(f"cd {workdir}")
    time.sleep(0.2)
    _drain()

    _send("su - root")
    if _wait_for([r"password:"], max_wait=25, heartbeat_label="waiting for root password prompt"):
        _send(root_password)

    # Give the shell a moment to switch contexts
    time.sleep(0.7)
    _drain()

    # Confirm we are root; if not, abort so we don't falsely report success.
    # Use a marker to avoid prompt/echo quirks.
    _send("printf '__FREEPBXTOOLS_IDU__%s__\\n' \"$(id -u)\"")
    if not _wait_for([r"__FREEPBXTOOLS_IDU__0__"], max_wait=12, heartbeat_label="verifying root"):
        raise RuntimeError("Failed to become root via su (id -u != 0)")

    # su - root typically resets to root's home; cd back into the working directory.
    _send(f"cd {workdir}")
    time.sleep(0.2)
    _drain()

    # Run requested commands and wait for an rc marker after each.
    # IMPORTANT: do not send `exit` until the command has completed; otherwise we
    # can kill long-running commands like install.sh and end up with missing symlinks.
    for i, cmd in enumerate(commands, start=1):
        marker = f"__FREEPBXTOOLS_CMD_DONE__{i}__"
        _send(cmd)
        _send(f"echo {marker}RC=$?")
        if not _wait_for([re.escape(marker) + r"RC=\\d+"], max_wait=max(30, timeout), heartbeat_label=f"running {cmd}"):
            raise TimeoutError(f"Timed out waiting for command completion marker: {cmd}")
        _drain()

    # Exit root shell
    _send("exit")
    time.sleep(0.2)
    _drain()

    return 0, "".join(out)


def _strip_internal_markers(text: str) -> str:
    if not text:
        return text
    # Remove our internal sentinel markers from displayed logs.
    return "\n".join(
        line for line in text.splitlines() if "__FREEPBXTOOLS_" not in line
    )

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

def deploy_to_server(
    server_ip,
    username,
    password,
    root_password,
    files,
    dry_run=False,
    connect_only=False,
    upload_only=False,
):
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
            password=(password if password else None),
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
            allow_agent=True,
            look_for_keys=True,
        )
        print_success(f"[{server_ip}] Connected")

        if connect_only:
            # Minimal remote command to verify exec works
            stdin, stdout, stderr = ssh.exec_command("echo CONNECT_OK && id && uname -a")
            stdout.channel.recv_exit_status()
            out = stdout.read().decode('utf-8', errors='ignore')
            err = stderr.read().decode('utf-8', errors='ignore')
            if out:
                print(f"[{server_ip}] Connect test output:\n{out}")
            if err:
                print(f"[{server_ip}] Connect test stderr:\n{err}")
            result['success'] = True
            result['message'] = 'Connect-only completed'
            return result
        
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

        if upload_only:
            result['success'] = True
            result['files_deployed'] = files_uploaded
            result['message'] = f'Upload-only completed ({files_uploaded} files)'
            return result
        
        # Now run the installation sequence as root
        # 1. Switch to root
        # 2. cd freepbx-tools
        # 3. bash bootstrap.sh
        # 4. ./install.sh
        
        print(f"[{server_ip}] Running installation as root...")
        exit_code = 0
        install_output = ""
        install_errors = ""
        try:
            _, install_output = _run_as_root_via_su(
                ssh,
                root_password=root_password,
                workdir=temp_dir,
                commands=["bash bootstrap.sh", "./install.sh"],
                timeout=1800,
                stream_output=True,
                stream_prefix=f"[{server_ip}] ",
            )
        except Exception as e:
            install_errors = str(e)
            exit_code = 1
        
        # Output is streamed live; keep a copy for banner/postcheck parsing.
        if install_errors:
            print(f"[{server_ip}] Installation errors:\n{install_errors}")
        
        # Only treat as success if install.sh printed its success banner,
        # AND postconditions exist (symlink + profile.d PATH helper).
        banner_ok = exit_code == 0 and "Installed 123NET FreePBX Tools to" in install_output

        postcheck_cmd = (
            # Verify key CLI links exist AND resolve to real targets
            "for n in freepbx-callflows freepbx-dump freepbx-tc-status; do "
            "  p=\"/usr/local/bin/$n\"; "
            "  if [ -L \"$p\" ] && [ -e \"$(readlink -f \"$p\" 2>/dev/null)\" ]; then "
            "    echo ${n}_OK; "
            "  else "
            "    echo ${n}_MISSING; "
            "  fi; "
            "done; "
            "test -f /etc/profile.d/123net-freepbx-tools.sh && echo PROFILE_OK || echo PROFILE_MISSING; "
            "bash -lc 'case \":$PATH:\" in *:/usr/local/bin:*) echo LOGINPATH_OK ;; *) echo LOGINPATH_MISSING ;; esac' 2>/dev/null || echo LOGINPATH_UNKNOWN"
        )
        stdin, stdout, stderr = ssh.exec_command(postcheck_cmd)
        stdout.channel.recv_exit_status()
        post_out = stdout.read().decode('utf-8', errors='ignore')
        post_err = stderr.read().decode('utf-8', errors='ignore')

        callflows_ok = "freepbx-callflows_OK" in post_out
        dump_ok = "freepbx-dump_OK" in post_out
        tc_ok = "freepbx-tc-status_OK" in post_out
        profile_ok = "PROFILE_OK" in post_out
        loginpath_ok = "LOGINPATH_OK" in post_out

        if banner_ok and callflows_ok and dump_ok and tc_ok and (profile_ok or loginpath_ok):
            print_success(f"[{server_ip}] Installation completed successfully")
            result['success'] = True
        else:
            print_warning(f"[{server_ip}] Installation did not meet post-install checks")
            result['success'] = False
            details = []
            if not banner_ok:
                details.append("missing installer success banner")
            if not callflows_ok:
                details.append("missing/broken /usr/local/bin/freepbx-callflows")
            if not dump_ok:
                details.append("missing/broken /usr/local/bin/freepbx-dump")
            if not tc_ok:
                details.append("missing/broken /usr/local/bin/freepbx-tc-status")
            if not (profile_ok or loginpath_ok):
                details.append("PATH not ensured (no /etc/profile.d helper and login PATH missing /usr/local/bin)")
            if post_err.strip():
                details.append("postcheck stderr present")
            result['message'] = "Install incomplete: " + ", ".join(details)
            if post_out.strip():
                print(f"[{server_ip}] Post-install check output:\n{post_out}")
            if post_err.strip():
                print(f"[{server_ip}] Post-install check stderr:\n{post_err}")

        # If we failed, print a cleaned summary of the captured session output for debugging.
        if not result['success'] and install_output:
            print(f"[{server_ip}] Installation output (captured, markers stripped):\n{_strip_internal_markers(install_output)}")
        
        result['files_deployed'] = files_uploaded
        result['message'] = f'Deployed {files_uploaded} files'
        
    except paramiko.AuthenticationException:
        result['message'] = 'Authentication failed'
        print_error(f"[{server_ip}] Authentication failed")
        print_info(f"[{server_ip}] Tip: if you normally SSH with keys, leave SSH Password blank so agent/key auth is used.")
    except paramiko.SSHException as e:
        result['message'] = f'SSH error: {str(e)}'
        print_error(f"[{server_ip}] SSH error: {e}")
    except Exception as e:
        result['message'] = f'Error: {str(e)}'
        print_error(f"[{server_ip}] Deployment failed: {e}")
    finally:
        ssh.close()
    
    return result
def deploy_parallel(
    servers,
    username,
    password,
    root_password,
    files,
    max_workers=5,
    dry_run=False,
    connect_only=False,
    upload_only=False,
):
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
            executor.submit(
                deploy_to_server,
                server,
                username,
                password,
                root_password,
                files,
                dry_run,
                connect_only,
                upload_only,
            ): server
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
    parser.add_argument('--root-password', default=ROOT_PASSWORD, help='Root password (for su root)')
    parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deployed without making changes')
    parser.add_argument('--connect-only', action='store_true', help='Only test SSH connect + remote exec (no upload/install)')
    parser.add_argument('--upload-only', action='store_true', help='Upload files but skip root install')
    args = parser.parse_args()

    if args.connect_only and args.upload_only:
        print_error("Choose only one: --connect-only or --upload-only")
        sys.exit(2)

    # If the config was redacted/placeholder, treat as blank.
    if _is_placeholder_secret(args.password):
        args.password = ""
    if _is_placeholder_secret(args.root_password):
        args.root_password = ""
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
    results = deploy_parallel(
        servers,
        args.user,
        args.password,
        args.root_password,
        files,
        args.workers,
        args.dry_run,
        args.connect_only,
        args.upload_only,
    )
    elapsed = time.time() - start_time
    # Print summary
    print_summary(results)
    print(f"\nTotal time: {elapsed:.1f} seconds")
    # Exit with error code if any deployments failed
    failed_count = len([r for r in results if not r['success']])
    sys.exit(1 if failed_count > 0 else 0)

if __name__ == "__main__":
    main()
