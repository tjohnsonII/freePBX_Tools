#!/usr/bin/env python3
"""
Deploy uninstall command to FreePBX servers
Runs the uninstall.sh script to remove FreePBX tools from servers
"""

import paramiko
import sys
import argparse
from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD

def uninstall_from_server(host, user, password, root_password):
    """Connect to server and run uninstall script"""
    print(f"[{host}] Starting uninstall...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Connect to server
        print(f"[{host}] Connecting...")
        ssh.connect(host, username=user, password=password, timeout=10)
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
        
        # Build command: su to root, cd to directory, run all uninstall commands, then remove ONLY specific directories
        cmd = (f"echo '{root_password}' | su root -c '"
               f"cd /home/123net/freepbx-tools && "
               f"./uninstall.sh --purge-cli-links && "
               f"./uninstall.sh --purge-callflows && "
               f"./uninstall.sh && "
               f"cd /home/123net/ && "
               f"rm -rf /home/123net/freepbx-tools/ && "
               f"rm -rf /home/123net/callflows/'")
        
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
        
        # Collect output
        install_output = stdout.read().decode('utf-8', errors='ignore')
        install_errors = stderr.read().decode('utf-8', errors='ignore')
        
        print(f"[{host}] Uninstall output:")
        print(install_output)
        
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
            print(verify_output)
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
                FREEPBX_USER, 
                FREEPBX_PASSWORD,
                FREEPBX_ROOT_PASSWORD
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
        print("✅ Successful Uninstalls:")
        for server in successful:
            print(f"  • {server}")
        print()
    
    if failed:
        print("❌ Failed Uninstalls:")
        for server in failed:
            print(f"  • {server}")
        print()
    
    sys.exit(0 if not failed else 1)

if __name__ == "__main__":
    main()
