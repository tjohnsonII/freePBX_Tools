#!/usr/bin/env python3
"""
FUNCTION MAP LEGEND
-------------------
uninstall_from_server(host, user, password, root_password):
    Uninstall FreePBX tools from a remote server via SSH.
main():
    Orchestrate the uninstallation process from CLI arguments.
"""
"""
Deploy uninstall command to FreePBX servers
Runs the uninstall.sh script to remove FreePBX tools from servers
"""

import os
import sys
import argparse
import time
import re

from typing import Any

paramiko: Any
try:
    import paramiko  # type: ignore
except ImportError:
    # Defer failure until a network operation is requested.
    paramiko = None


def _ensure_paramiko() -> None:
    if paramiko is None:
        raise RuntimeError("paramiko library not installed (required for SSH). Install with: pip install paramiko")


def _configure_stdio_errors_replace() -> None:
    """Prevent UnicodeEncodeError on Windows consoles with legacy codepages."""

    try:
        stdout_reconf = getattr(sys.stdout, "reconfigure", None)
        if callable(stdout_reconf):
            stdout_reconf(errors="replace")
        stderr_reconf = getattr(sys.stderr, "reconfigure", None)
        if callable(stderr_reconf):
            stderr_reconf(errors="replace")
    except Exception:
        pass


_configure_stdio_errors_replace()


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def load_credentials():
    env_user = os.getenv("FREEPBX_USER", "").strip()
    env_pass = (os.getenv("FREEPBX_PASSWORD", "") or "").rstrip("\r\n")
    env_root = (os.getenv("FREEPBX_ROOT_PASSWORD", "") or "").rstrip("\r\n")
    if env_user or env_pass or env_root:
        return env_user or "123net", env_pass, env_root

    try:
        from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD  # type: ignore
        return str(FREEPBX_USER), str(FREEPBX_PASSWORD), str(FREEPBX_ROOT_PASSWORD)
    except Exception:
        return "123net", "", ""

def uninstall_from_server(host, user, password, root_password):
    """Connect to server and run uninstall script"""
    _ensure_paramiko()
    print(f"[{host}] Starting uninstall...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Connect to server
        print(f"[{host}] Connecting...")
        ssh.connect(
            host,
            username=user,
            password=(password if password else None),
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
            allow_agent=True,
            look_for_keys=True,
        )
        print(f"[OK] [{host}] Connected")
        
        # Check if directory exists
        stdin, stdout, stderr = ssh.exec_command('test -d /home/123net/freepbx-tools && echo "EXISTS"')
        if stdout.read().decode().strip() != "EXISTS":
            print(f"[SKIP] [{host}] FreePBX tools not installed")
            ssh.close()
            return True
        
        # Safety check - list what will be removed
        print(f"[{host}] Checking directories to remove...")
        stdin, stdout, stderr = ssh.exec_command('ls -ld /home/123net/freepbx-tools /home/123net/callflows 2>/dev/null')
        dirs_output = stdout.read().decode()
        if dirs_output:
            print(f"[{host}] Will remove:")
            print(dirs_output)
        
        # Run uninstall as root with full cleanup
        print(f"[{host}] Running uninstall script as root...")

        if not root_password:
            raise RuntimeError("Root password is required to uninstall via su")

        chan = ssh.invoke_shell()
        chan.settimeout(2.0)
        start = time.time()
        out = []

        def _send(line: str) -> None:
            # Paramiko's type stubs expect bytes; encode explicitly for Pylance.
            chan.send((line + "\n").encode("utf-8"))

        def _drain():
            buf = ""
            while chan.recv_ready():
                chunk = chan.recv(4096).decode("utf-8", errors="ignore")
                if not chunk:
                    break
                buf += chunk
            if buf:
                out.append(buf)
            return buf

        def _wait_for(pattern, max_wait=15):
            rx = re.compile(pattern, re.IGNORECASE)
            buf = ""
            end = time.time() + max_wait
            while time.time() < end:
                time.sleep(0.2)
                buf += _drain()
                if rx.search(buf):
                    return True
                if time.time() - start > 120:
                    break
            return False

        _drain()
        _send("su - root")
        if _wait_for(r"password:"):
            _send(root_password)

        time.sleep(0.5)
        _drain()

        _send("cd /home/123net/freepbx-tools")
        _send("./uninstall.sh --purge-cli-links --purge-callflows -y")
        _send("cd /home/123net/")
        _send("rm -rf /home/123net/freepbx-tools/ /home/123net/callflows/")
        _send("exit")
        time.sleep(1.0)
        _drain()

        install_output = "".join(out)
        install_errors = ""
        
        # Collect output/errors (best-effort; interactive shell doesn't separate streams)
        
        print(f"[{host}] Uninstall output:")
        _safe_print(install_output)
        
        if install_errors:
            print(f"[{host}] Uninstall errors:")
            print(install_errors)
        
        # Verify removal
        print(f"[{host}] Verifying removal...")
        stdin, stdout, stderr = ssh.exec_command('ls -ld /home/123net/freepbx-tools /home/123net/callflows 2>&1')
        verify_output = stdout.read().decode()
        if "No such file or directory" in verify_output or not verify_output.strip():
            print(f"[OK] [{host}] Directories successfully removed")
            print(f"[OK] [{host}] Uninstall completed successfully")
            ssh.close()
            return True
        else:
            print(f"[WARNING] [{host}] Some directories may still exist:")
            _safe_print(verify_output)
            ssh.close()
            return False
            
    except paramiko.AuthenticationException:
        print(f"[FAILED] [{host}] Authentication failed")
        return False
    except paramiko.SSHException as e:
        print(f"[FAILED] [{host}] SSH error: {e}")
        return False
    except Exception as e:
        print(f"[FAILED] [{host}] Error: {e}")
        return False
    finally:
        try:
            ssh.close()
        except:
            pass

def main():
    parser = argparse.ArgumentParser(description='Uninstall FreePBX Tools from remote servers')
    parser.add_argument('--servers', required=True, 
                       help='Comma-separated IP addresses or file with server list')
    default_user, default_pass, default_root = load_credentials()
    parser.add_argument('--user', default=default_user, help='SSH username')
    parser.add_argument('--password', default=default_pass, help='SSH password (leave blank for key/agent auth)')
    parser.add_argument('--root-password', default=default_root, help='Root password (for su root)')
    args = parser.parse_args()
    
    # Parse server list
    servers = []
    if ',' in args.servers:
        servers = [s.strip() for s in args.servers.split(',')]
    else:
        # Assume it's a file
        try:
            with open(args.servers, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Handle CSV/TSV format - take first column
                        parts = line.replace(',', '\t').split('\t')
                        if parts[0]:
                            servers.append(parts[0].strip())
        except FileNotFoundError:
            # Not a file, treat as single server
            servers = [args.servers]
    
    if not servers:
        print("ERROR: No servers specified")
        sys.exit(1)
    
    print("=" * 70)
    print("  FreePBX Tools Uninstall")
    print("=" * 70)
    print(f"Servers: {len(servers)}")
    print()
    print("=" * 70)
    print(f"  Uninstalling from {len(servers)} servers")
    print("=" * 70)
    print()
    
    # Process servers
    successful = []
    failed = []
    
    for server in servers:
        try:
            success = uninstall_from_server(
                server, 
                args.user,
                (args.password if args.password != "***REMOVED***" else ""),
                (args.root_password if args.root_password != "***REMOVED***" else "")
            )
            
            if success:
                successful.append(server)
            else:
                failed.append(server)
                
        except KeyboardInterrupt:
            print("\n[CANCELLED] Uninstall interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"[FAILED] [{server}] Unexpected error: {e}")
            failed.append(server)
        
        print()
    
    # Summary
    print("=" * 70)
    print("  Uninstall Summary")
    print("=" * 70)
    print()
    print(f"Total servers: {len(servers)}")
    print(f"[OK] Successful: {len(successful)}")
    if failed:
        print(f"[FAILED] Failed: {len(failed)}")
    print()
    
    if successful:
        print("[OK] Successful Uninstalls:")
        for server in successful:
            print(f"  - {server}")
        print()
    
    if failed:
        print("[FAILED] Failed Uninstalls:")
        for server in failed:
            print(f"  - {server}")
        print()
    
    sys.exit(0 if not failed else 1)

if __name__ == "__main__":
    main()
