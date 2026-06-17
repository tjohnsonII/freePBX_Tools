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
import re
import argparse
import py_compile
from typing import List

# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("")  # This enables ANSI escape sequences in Windows console


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
        # Best-effort only.
        pass


_configure_stdio_errors_replace()

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
    print(f"\n{Colors.YELLOW}{Colors.BOLD}Main Menu:{Colors.RESET}")
    print(f"  {Colors.CYAN}1){Colors.RESET} Deploy tools to server(s)")
    print(f"  {Colors.CYAN}2){Colors.RESET} Uninstall tools from server(s)")
    print(f"  {Colors.CYAN}3){Colors.RESET} 🔄 Uninstall + Install (clean deployment)")
    print(f"  {Colors.CYAN}4){Colors.RESET} Test dashboard on test server (69.39.69.102)")
    print(f"  {Colors.CYAN}5){Colors.RESET} View deployment status")
    print(f"  {Colors.CYAN}6){Colors.RESET} 🔌 SSH into a server")
    print(f"  {Colors.CYAN}7){Colors.RESET} 📱 Phone Config Analyzer")
    print(f"  {Colors.CYAN}8){Colors.RESET} 🔍 Validate install/uninstall symlinks")
    print(f"  {Colors.CYAN}9){Colors.RESET} 📦 Create + upload offline bundle (zip)")
    print(f"  {Colors.CYAN}11){Colors.RESET} 🚀 Push traceroute server helper to 192.168.50.1")
    print(f"  {Colors.CYAN}10){Colors.RESET} Exit")
    print()


def push_traceroute_server_helper() -> None:
    """Upload scripts/traceroute_server_ctl.sh to a traceroute server.

    Defaults to the lab host 192.168.50.1. Uses Paramiko SFTP if available
    (supports password auth or keys/agent), otherwise falls back to external scp.
    """

    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print("  🚀 Push traceroute server helper")
    print(f"{'='*70}{Colors.RESET}")

    default_host = os.environ.get("TRACEROUTE_PUSH_HOST", "192.168.50.1")
    default_user = os.environ.get("TRACEROUTE_PUSH_USER") or os.environ.get("FREEPBX_USER") or getpass.getuser()
    default_dir = os.environ.get("TRACEROUTE_PUSH_DIR", ".")

    host = input(f"Target host [{default_host}]: ").strip() or default_host
    username = input(f"SSH username [{default_user}]: ").strip() or default_user
    password = getpass.getpass("SSH password (leave blank to use SSH keys/agent): ")
    remote_dir = input(f"Remote directory (where traceroute_server_update.py lives) [{default_dir}]: ").strip() or default_dir

    repo_root = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(repo_root, "scripts", "traceroute_server_ctl.sh")
    if not os.path.exists(local_path):
        print(f"{Colors.RED}❌ Local script not found:{Colors.RESET} {local_path}")
        return

    # Build a remote path. For Paramiko/SFTP, '~' is not expanded; keep it relative.
    rd = remote_dir.strip()
    if rd in ("", ".", "~"):
        remote_path = "traceroute_server_ctl.sh"
    elif rd.startswith("~/"):
        remote_path = "traceroute_server_ctl.sh" if rd == "~/" else rd[2:].rstrip("/") + "/traceroute_server_ctl.sh"
    elif rd.startswith("/"):
        remote_path = rd.rstrip("/") + "/traceroute_server_ctl.sh"
    else:
        remote_path = rd.rstrip("/") + "/traceroute_server_ctl.sh"

    print(f"\n{Colors.YELLOW}Uploading:{Colors.RESET} {local_path}")
    print(f"{Colors.YELLOW}To:{Colors.RESET} {username}@{host}:{remote_path}\n")

    ok = False
    paramiko = _ensure_paramiko()
    if paramiko is not None:
        # Prefer Paramiko when available. If the server lacks SFTP subsystem,
        # _sftp_upload_file() will fall back to an exec-based streaming upload.
        ok = _sftp_upload_file(host, username, password, local_path, remote_path)
    else:
        if password:
            print(
                f"{Colors.YELLOW}Note:{Colors.RESET} Paramiko is not installed; using external scp (it will prompt for password)."
            )
        ok = _scp_upload_file(host, username, local_path, remote_path)

    if not ok:
        return

    # Best-effort chmod so it can be executed immediately.
    paramiko = _ensure_paramiko()
    if paramiko is not None:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                host,
                username=username,
                password=(password if password else None),
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
                allow_agent=True,
                look_for_keys=True,
            )
            ssh.exec_command(f"chmod +x '{remote_path}'")
            ssh.close()
            print(f"{Colors.GREEN}[OK]{Colors.RESET} chmod +x applied")
        except Exception:
            pass

    print(f"\n{Colors.GREEN}{Colors.BOLD}Next steps on the remote host:{Colors.RESET}")
    print(f"  1) cd {remote_dir}")
    print(f"  2) ./traceroute_server_ctl.sh start-follow")


def create_offline_bundle():
    """Create a zip bundle of deployable files for manual upload/install."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print("  Create Offline Bundle")
    print(f"{'='*70}{Colors.RESET}")
    default_name = "freepbx-tools-bundle.zip"
    out_name = input(f"Output zip filename [{default_name}]: ").strip() or default_name
    cmd = [sys.executable, "deploy_freepbx_tools.py", "--bundle", out_name]
    print(f"\n{Colors.GREEN}{Colors.BOLD}Creating bundle...{Colors.RESET}\n")
    subprocess.run(cmd)
    print(
        f"\n{Colors.GREEN}[OK] Bundle created. Copy it to the server, unzip into /home/123net/freepbx-tools, then run bootstrap.sh + install.sh as root.{Colors.RESET}"
    )


def _ensure_paramiko():
    try:
        import paramiko  # type: ignore

        return paramiko
    except Exception:
        return None


def _sh_quote(s: str) -> str:
    """POSIX shell single-quote escaping."""

    return "'" + s.replace("'", "'\"'\"'") + "'"


def _ssh_put_file_via_cat(server: str, username: str, password: str, local_path: str, remote_path: str) -> bool:
    """Upload a file without SFTP by streaming bytes to `cat > remote_path`.

    This works on older SSH servers that do not provide the sftp subsystem.
    """

    paramiko = _ensure_paramiko()
    if paramiko is None:
        print(f"{Colors.RED}❌ paramiko is not installed (required for password-based upload).{Colors.RESET}")
        return False

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            server,
            username=username,
            password=(password if password else None),
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            allow_agent=True,
            look_for_keys=True,
        )

        # Ensure target directory exists (best-effort). If remote_path is relative, this is a no-op.
        remote_dir = os.path.dirname(remote_path)
        if remote_dir and remote_dir not in (".", "~"):
            ssh.exec_command(f"mkdir -p {_sh_quote(remote_dir)}")

        cmd = f"cat > {_sh_quote(remote_path)}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        try:
            with open(local_path, "rb") as f:
                data = f.read()
            stdin.write(data)
            stdin.channel.shutdown_write()

            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                err = ""
                try:
                    err = (stderr.read() or b"").decode("utf-8", errors="replace")
                except Exception:
                    pass
                print(f"{Colors.RED}[FAILED]{Colors.RESET} Remote write failed (exit {exit_status}): {err.strip()}")
                return False
        finally:
            try:
                stdin.close()
            except Exception:
                pass

        print(f"{Colors.GREEN}[OK]{Colors.RESET} Uploaded to {server}:{remote_path} (via cat)")
        return True
    except Exception as e:
        print(f"{Colors.RED}[FAILED]{Colors.RESET} Upload to {server} failed: {e}")
        return False
    finally:
        try:
            ssh.close()
        except Exception:
            pass


def _read_server_list_file(path: str) -> List[str]:
    servers: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                # CSV/TSV/space: take first column
                token = re.split(r"[\t,\s]", line, maxsplit=1)[0].strip()
                if token:
                    servers.append(token)
    except Exception as e:
        print(f"{Colors.RED}[ERROR] Failed to read server list file: {path} ({e}){Colors.RESET}")
    return servers


def _resolve_servers(servers) -> List[str]:
    if isinstance(servers, (list, tuple)):
        return [str(s).strip() for s in servers if str(s).strip()]

    if not isinstance(servers, str) or not servers.strip():
        return []

    servers = servers.strip()
    if os.path.exists(servers) and os.path.isfile(servers):
        return _read_server_list_file(servers)
    if "," in servers:
        return [p.strip() for p in servers.split(",") if p.strip()]
    return [servers]


def _sftp_upload_file(server: str, username: str, password: str, local_path: str, remote_path: str) -> bool:
    paramiko = _ensure_paramiko()
    if paramiko is None:
        print(f"{Colors.RED}❌ paramiko is not installed (required for password-based upload).{Colors.RESET}")
        print(f"{Colors.YELLOW}Install it with:{Colors.RESET} pip install paramiko")
        print(f"{Colors.YELLOW}Or upload manually with scp (SSH keys recommended).{Colors.RESET}")
        return False

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"{Colors.CYAN}[{server}]{Colors.RESET} Uploading {os.path.basename(local_path)} ...")
        ssh.connect(
            server,
            username=username,
            password=(password if password else None),
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            allow_agent=True,
            look_for_keys=True,
        )
        try:
            sftp = ssh.open_sftp()
            try:
                sftp.put(local_path, remote_path)
            finally:
                sftp.close()
            print(f"{Colors.GREEN}[OK]{Colors.RESET} Uploaded to {server}:{remote_path}")
            return True
        except Exception as e:
            # Common on very old SSH servers: SFTP subsystem not configured/available.
            print(f"{Colors.YELLOW}[WARN]{Colors.RESET} SFTP upload failed ({e}). Falling back to streaming upload...")
            # Close this SSH client and reconnect in the fallback helper (keeps logic simple).
            try:
                ssh.close()
            except Exception:
                pass
            return _ssh_put_file_via_cat(server, username, password, local_path, remote_path)
    except Exception as e:
        print(f"{Colors.RED}[FAILED]{Colors.RESET} Upload to {server} failed: {e}")
        return False
    finally:
        try:
            ssh.close()
        except Exception:
            pass


def _scp_upload_file(server: str, username: str, local_path: str, remote_path: str) -> bool:
    """Upload via external scp binary.

    Notes:
    - This will prompt interactively for password if needed.
    - Host key prompts may appear on first connection.
    """
    # OpenSSH 9.x defaults scp to SFTP mode, which can fail on older servers
    # that do not provide the sftp subsystem. "-O" forces the legacy scp/rcp protocol.
    scp_cmd = [
        "scp",
        "-O",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]

    # Very old boxes (e.g., FreeBSD 7.4 OpenSSH 5.1p1) may only advertise ssh-dss host keys.
    # Keep this scoped to the lab host.
    if server.strip() == "192.168.50.1":
        scp_cmd += [
            "-o",
            "HostKeyAlgorithms=+ssh-dss",
            "-o",
            "PubkeyAcceptedAlgorithms=+ssh-dss",
        ]

    scp_cmd += [
        local_path,
        f"{username}@{server}:{remote_path}",
    ]

    try:
        print(f"{Colors.CYAN}[{server}]{Colors.RESET} Running scp upload...")
        r = subprocess.run(scp_cmd)
        if r.returncode == 0:
            print(f"{Colors.GREEN}[OK]{Colors.RESET} Uploaded to {server}:{remote_path}")
            return True
        print(f"{Colors.RED}[FAILED]{Colors.RESET} scp failed with exit {r.returncode}")
        return False
    except FileNotFoundError:
        print(f"{Colors.RED}❌ scp not found on this machine.{Colors.RESET}")
        print(f"{Colors.YELLOW}Install OpenSSH client or use SFTP (Paramiko).{Colors.RESET}")
        return False


def create_and_upload_offline_bundle():
    """Create the offline bundle zip and upload it to target server(s)."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print("  📦 Create + Upload Offline Bundle")
    print(f"{'='*70}{Colors.RESET}")

    default_name = "freepbx-tools-bundle.zip"
    out_name = input(f"Output zip filename [{default_name}]: ").strip() or default_name

    # Create bundle locally (no servers needed)
    cmd = [sys.executable, "deploy_freepbx_tools.py", "--bundle", out_name]
    print(f"\n{Colors.GREEN}{Colors.BOLD}🔄 Creating bundle...{Colors.RESET}\n")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"{Colors.RED}❌ Bundle creation failed (exit {r.returncode}){Colors.RESET}")
        return

    bundle_path = os.path.abspath(out_name if out_name.lower().endswith(".zip") else out_name + ".zip")
    if not os.path.exists(bundle_path):
        print(f"{Colors.RED}❌ Expected bundle not found: {bundle_path}{Colors.RESET}")
        return

    # Choose upload targets
    targets = get_servers()
    if not targets:
        return
    server_list = _resolve_servers(targets)
    if not server_list:
        print(f"{Colors.RED}❌ No valid servers selected{Colors.RESET}")
        return

    if len(server_list) > 10:
        print(f"{Colors.RED}{Colors.BOLD}⚠️  WARNING:{Colors.RESET} You selected {len(server_list)} servers.")
        confirm = input("Type UPLOAD to confirm bulk upload: ").strip()
        if confirm != "UPLOAD":
            print(f"{Colors.RED}❌ Cancelled{Colors.RESET}")
            return

    print(f"\n{Colors.YELLOW}{Colors.BOLD}Upload method:{Colors.RESET}")
    print(f"  {Colors.CYAN}1){Colors.RESET} SFTP (Paramiko, supports password prompt here)")
    print(f"  {Colors.CYAN}2){Colors.RESET} scp (external, will prompt in terminal)")
    method = input("Choose method (1-2) [1]: ").strip() or "1"
    if method not in {"1", "2"}:
        print(f"{Colors.RED}❌ Invalid upload method{Colors.RESET}")
        return

    # Credentials
    # - SFTP uses Paramiko and will use the password entered here.
    # - scp is executed as an external command and will prompt interactively if needed.
    username, password, _ = get_credentials(need_root_password=False)
    remote_default = f"/home/{username}/{os.path.basename(bundle_path)}"
    remote_path = input(f"Remote path on server [{remote_default}]: ").strip() or remote_default

    print(f"\n{Colors.GREEN}{Colors.BOLD}🔄 Uploading bundle...{Colors.RESET}\n")
    ok = 0
    for server in server_list:
        if method == "1":
            success = _sftp_upload_file(server, username, password, bundle_path, remote_path)
        else:
            if password:
                print(f"{Colors.YELLOW}⚠️  Note:{Colors.RESET} scp will prompt; the password entered above is not passed to scp.")
            success = _scp_upload_file(server, username, bundle_path, remote_path)
        if success:
            ok += 1

    print(f"\n{Colors.CYAN}{Colors.BOLD}Upload Summary:{Colors.RESET}")
    print(f"  {Colors.GREEN}✅ Uploaded:{Colors.RESET} {ok}")
    print(f"  {Colors.RED}❌ Failed:{Colors.RESET} {len(server_list) - ok}")
    print(
        f"\n{Colors.YELLOW}Next steps on the server:{Colors.RESET}\n"
        f"  ssh {username}@<SERVER>\n"
        f"  rm -rf /home/{username}/freepbx-tools && mkdir -p /home/{username}/freepbx-tools\n"
        f"  unzip -o {remote_path} -d /home/{username}/freepbx-tools\n"
        f"  su - root\n"
        f"  cd /home/{username}/freepbx-tools && bash bootstrap.sh && ./install.sh\n"
    )

def get_credentials(need_root_password=True):
    """Prompt for SSH credentials."""
    print(f"\n{Colors.YELLOW}{Colors.BOLD}🔑 SSH Credentials:{Colors.RESET}")
    
    username = input("SSH Username [123net]: ").strip() or "123net"
    password = getpass.getpass("SSH Password: ")
    
    root_password = ""
    if need_root_password:
        # Ask if root password is different
        root_same = input("\nIs root password the same as SSH password? (yes/no) [yes]: ").strip().lower()
        
        if root_same in ['no', 'n']:
            root_password = getpass.getpass("Root Password: ")
        else:
            root_password = password
            print("  → Using SSH password for root")
    
    return username, password, root_password

def create_temp_config(username, password, root_password):
    """DEPRECATED.

    Credentials are now passed to child scripts via environment variables to avoid:
    - writing secrets into the repo, and
    - breaking deployments with redacted placeholder values.
    """
    _ = (username, password, root_password)
    return None

def _run_with_credentials(cmd, username, password, root_password):
    env = os.environ.copy()
    env["FREEPBX_USER"] = username
    env["FREEPBX_PASSWORD"] = password
    env["FREEPBX_ROOT_PASSWORD"] = root_password
    return subprocess.run(cmd, env=env)

def _parse_install_symlinks(install_sh_text):
    bin_links = set()
    call_sim_links = set()

    for m in re.finditer(r"\bln\s+-s(?:f|fn)?\s+[^\n]*?\$BIN_DIR/([^\s\"]+)", install_sh_text):
        bin_links.add(m.group(1).strip())

    for m in re.finditer(r"\bln\s+-s(?:f|fn)?\s+[^\n]*?\$INSTALL_ROOT/call-simulation/([^\s\"]+)", install_sh_text):
        call_sim_links.add(m.group(1).strip())

    return bin_links, call_sim_links

def _parse_uninstall_symlinks(uninstall_sh_text):
    bin_links = set()
    call_sim_links = set()

    lines = uninstall_sh_text.splitlines()
    in_for = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("for n in"):
            in_for = True
            continue
        if in_for and line.startswith("do"):
            in_for = False
            continue
        if in_for:
            token = line.strip().strip('\\').strip()
            if token and not token.startswith('#'):
                bin_links.add(token)

    for m in re.finditer(r"unlink_if_symlink\s+\"\$\{CALL_SIM_DIR\}/([^\"]+)\"", uninstall_sh_text):
        call_sim_links.add(m.group(1).strip())

    return bin_links, call_sim_links

def validate_installer_uninstaller_symlinks():
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}")
    print("  🔍 Validate install/uninstall symlink consistency")
    print(f"{'='*70}{Colors.RESET}")

    install_path = os.path.join("freepbx-tools", "install.sh")
    uninstall_path = os.path.join("freepbx-tools", "uninstall.sh")

    if not os.path.exists(install_path):
        print(f"{Colors.RED}❌ Missing: {install_path}{Colors.RESET}")
        return
    if not os.path.exists(uninstall_path):
        print(f"{Colors.RED}❌ Missing: {uninstall_path}{Colors.RESET}")
        return

    with open(install_path, "r", encoding="utf-8", errors="ignore") as f:
        install_text = f.read()
    with open(uninstall_path, "r", encoding="utf-8", errors="ignore") as f:
        uninstall_text = f.read()

    install_bin, install_call_sim = _parse_install_symlinks(install_text)
    uninstall_bin, uninstall_call_sim = _parse_uninstall_symlinks(uninstall_text)

    missing_bin = sorted(install_bin - uninstall_bin)
    extra_bin = sorted(uninstall_bin - install_bin)
    missing_call_sim = sorted(install_call_sim - uninstall_call_sim)
    extra_call_sim = sorted(uninstall_call_sim - install_call_sim)

    print(f"\n{Colors.YELLOW}BIN_DIR symlinks:{Colors.RESET} install={len(install_bin)}, uninstall={len(uninstall_bin)}")
    if missing_bin:
        print(f"{Colors.RED}❌ Missing in uninstall.sh (will remain installed):{Colors.RESET}")
        for n in missing_bin:
            print(f"  • {n}")
    else:
        print(f"{Colors.GREEN}✅ All install.sh BIN_DIR symlinks are covered by uninstall.sh{Colors.RESET}")
    if extra_bin:
        print(f"{Colors.YELLOW}ℹ️  Extra symlinks removed by uninstall.sh (not created by install.sh):{Colors.RESET}")
        for n in extra_bin[:25]:
            print(f"  • {n}")
        if len(extra_bin) > 25:
            print(f"  … +{len(extra_bin)-25} more")

    print(f"\n{Colors.YELLOW}call-simulation symlinks:{Colors.RESET} install={len(install_call_sim)}, uninstall={len(uninstall_call_sim)}")
    if missing_call_sim:
        print(f"{Colors.RED}❌ Missing in uninstall.sh:{Colors.RESET}")
        for n in missing_call_sim:
            print(f"  • {n}")
    else:
        print(f"{Colors.GREEN}✅ All install.sh call-simulation symlinks are covered by uninstall.sh{Colors.RESET}")
    if extra_call_sim:
        print(f"{Colors.YELLOW}ℹ️  Extra call-simulation symlinks removed by uninstall.sh:{Colors.RESET}")
        for n in extra_call_sim:
            print(f"  • {n}")


def _build_deploy_cmd(script_name, servers):
    """Build a deploy/uninstall command line.

    The deploy scripts support either:
      - positional server file, OR
      - --servers <ip1> <ip2> ...

    The manager's UI returns:
      - a single IP string
      - a comma-separated string of IPs
      - a filename (ProductionServers.txt/custom file)
    """
    cmd = [sys.executable, script_name]

    if isinstance(servers, (list, tuple)):
        flat = [str(s).strip() for s in servers if str(s).strip()]
        if not flat:
            return cmd
        return cmd + ["--servers"] + flat

    if not isinstance(servers, str) or not servers.strip():
        return cmd

    servers = servers.strip()

    # If it's a real file path, prefer positional arg so deploy script can parse the file.
    if os.path.exists(servers) and os.path.isfile(servers):
        return cmd + [servers]

    # If it's comma-separated, split into list.
    if "," in servers:
        parts = [p.strip() for p in servers.split(",") if p.strip()]
        return cmd + ["--servers"] + parts

    return cmd + ["--servers", servers]


def _self_test():
    """Non-interactive sanity checks for manager + deploy scripts."""
    print("\n=== freepbx_tools_manager self-test (OFFLINE) ===\n")
    print("This self-test is designed to run on a developer machine.")
    print("- No FreePBX instance required")
    print("- No network/SSH connections are performed")
    print("- Checks focus on syntax, packaging, and installer consistency\n")

    required_paths = [
        os.path.join("freepbx-tools", "install.sh"),
        os.path.join("freepbx-tools", "uninstall.sh"),
        os.path.join("freepbx-tools", "bootstrap.sh"),
        "deploy_freepbx_tools.py",
        "deploy_uninstall_tools.py",
    ]
    missing = [p for p in required_paths if not os.path.exists(p)]
    if missing:
        print("Missing required files:")
        for p in missing:
            print(f"  - {p}")
        return 1

    # Python syntax check
    to_compile = [
        "freepbx_tools_manager.py",
        "deploy_freepbx_tools.py",
        "deploy_uninstall_tools.py",
    ]
    for f in to_compile:
        py_compile.compile(f, doraise=True)
    print("[OK] Python scripts compile")

    # Guard against common bash + set -e pitfall:
    #   ((ok++)) returns exit status 1 on first increment when ok was 0.
    # If install.sh uses 'set -e', that can abort the installer even when
    # installation actually succeeded.
    print("\n[INFO] Checking freepbx-tools/install.sh for set -e safe counters...")
    install_sh_path = os.path.join("freepbx-tools", "install.sh")
    try:
        with open(install_sh_path, "r", encoding="utf-8", errors="ignore") as f:
            install_lines = f.read().splitlines()

        uses_set_e = any(
            re.search(r"^\s*set\s+-.*e", line) for line in install_lines
        )

        suspicious = []
        counter_vars = {"ok", "fail", "missing"}
        for idx, raw in enumerate(install_lines, start=1):
            line = raw.strip()
            m = re.search(r"\(\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\+\+\s*\)\)", line)
            if not m:
                continue
            var = m.group(1)
            if var not in counter_vars:
                continue
            # Under set -e, ensure the increment is guarded (e.g. `|| true`).
            if uses_set_e and "||" not in line:
                suspicious.append((idx, line))

        # Guard against smoke tests that execute tool entrypoints.
        # These can block/hang depending on environment (TTY, DB access, etc.).
        bad_exec_patterns = [
            r"\bfreepbx_callflow_menu\.py\b.*\s--help\b",
            r"\bfreepbx_tc_status\.py\b.*\s--help\b",
        ]
        bad_exec_hits = []
        for idx, raw in enumerate(install_lines, start=1):
            for pat in bad_exec_patterns:
                if re.search(pat, raw):
                    bad_exec_hits.append((idx, raw.strip()))
                    break

        if bad_exec_hits:
            print("[FAIL] install.sh smoke test executes tool scripts (can hang):")
            for idx, line in bad_exec_hits[:15]:
                print(f"  - L{idx}: {line}")
            if len(bad_exec_hits) > 15:
                print(f"  ... +{len(bad_exec_hits) - 15} more")
            print("[INFO] Prefer syntax-only checks: python3 -m py_compile <file>")
            return 4

        if suspicious:
            print("[FAIL] install.sh has unguarded counter increments under set -e:")
            for idx, line in suspicious[:15]:
                print(f"  - L{idx}: {line}")
            if len(suspicious) > 15:
                print(f"  ... +{len(suspicious) - 15} more")
            return 4

        print("[OK] install.sh counter increments are set -e safe")
    except Exception as e:
        print(f"[FAIL] Could not check {install_sh_path}: {e}")
        return 4

    # Symlink consistency (prints details)
    validate_installer_uninstaller_symlinks()

    # Deploy script dry-run (must not attempt network)
    print("\n[INFO] Running deploy_freepbx_tools.py --dry-run (no SSH, no changes)...")
    r = subprocess.run([sys.executable, "deploy_freepbx_tools.py", "--dry-run", "--workers", "1", "--servers", "127.0.0.1"], check=False)
    if r.returncode != 0:
        print("[FAIL] deploy_freepbx_tools.py dry-run failed")
        return 2
    print("[OK] deploy_freepbx_tools.py dry-run")

    # Uninstall script help should work
    print("\n[INFO] Checking deploy_uninstall_tools.py --help...")
    r = subprocess.run([sys.executable, "deploy_uninstall_tools.py", "--help"], check=False)
    if r.returncode != 0:
        print("[FAIL] deploy_uninstall_tools.py --help failed")
        return 3
    print("[OK] deploy_uninstall_tools.py --help")

    print("\n=== self-test PASSED ===")
    return 0

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
    
    print(f"\n{Colors.YELLOW}{Colors.BOLD}Deploy mode:{Colors.RESET}")
    print(f"  {Colors.CYAN}1){Colors.RESET} Full deploy (upload + root install)")
    print(f"  {Colors.CYAN}2){Colors.RESET} Connect-only (SSH + remote exec test, no changes)")
    print(f"  {Colors.CYAN}3){Colors.RESET} Upload-only (upload files, no root install)")
    print(f"  {Colors.CYAN}4){Colors.RESET} Create offline bundle (zip for manual upload/install)")
    mode = input("Choose mode (1-4) [1]: ").strip() or "1"
    if mode not in {"1", "2", "3", "4"}:
        print(f"{Colors.RED}❌ Invalid mode{Colors.RESET}")
        return

    # Offline bundle does not need a server selection or credentials.
    if mode == "4":
        create_offline_bundle()
        return

    servers = get_servers()
    if not servers:
        return

    test_root = False
    if mode == "2":
        root_choice = input("Also test 'su root' after login? (yes/no) [no]: ").strip().lower()
        test_root = root_choice in {"yes", "y"}
    
    # Get credentials
    # - Full deploy needs root password
    # - Connect-only can optionally test su-to-root
    username, password, root_password = get_credentials(need_root_password=(mode == "1" or test_root))
    
    # Confirm deployment
    print(f"\n{Colors.YELLOW}📦 Ready to deploy to:{Colors.RESET} {Colors.CYAN}{servers}{Colors.RESET}")
    print(f"   {Colors.YELLOW}Username:{Colors.RESET} {Colors.CYAN}{username}{Colors.RESET}")
    confirm = input(f"{Colors.YELLOW}Continue with deployment? (yes/no):{Colors.RESET} ").strip().lower()
    
    if confirm != "yes":
        print(f"{Colors.RED}❌ Cancelled{Colors.RESET}")
        return
    
    # Run deployment
    print(f"\n{Colors.GREEN}{Colors.BOLD}🔄 Starting deployment...{Colors.RESET}\n")
    cmd = _build_deploy_cmd("deploy_freepbx_tools.py", servers)
    if mode == "2":
        cmd.append("--connect-only")
    elif mode == "3":
        cmd.append("--upload-only")
    _run_with_credentials(cmd, username, password, root_password)

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
    cmd = _build_deploy_cmd("deploy_uninstall_tools.py", servers)
    _run_with_credentials(cmd, username, password, root_password)

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
    
    # Step 1: Uninstall
    print(f"\n{Colors.CYAN}{Colors.BOLD}Step 1/2: Uninstalling...{Colors.RESET}")
    print("="*70)
    cmd = _build_deploy_cmd("deploy_uninstall_tools.py", servers)
    result = _run_with_credentials(cmd, username, password, root_password)
    
    if result.returncode != 0:
        print(f"\n{Colors.RED}❌ Uninstall failed. Aborting deployment.{Colors.RESET}")
        return
    
    print(f"\n{Colors.GREEN}[OK] Uninstall complete{Colors.RESET}")
    
    # Step 2: Install
    print(f"\n{Colors.CYAN}{Colors.BOLD}Step 2/2: Installing...{Colors.RESET}")
    print("="*70)
    cmd = _build_deploy_cmd("deploy_freepbx_tools.py", servers)
    result = _run_with_credentials(cmd, username, password, root_password)
    
    if result.returncode == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}[OK] Clean deployment completed successfully!{Colors.RESET}")
    else:
        print(f"\n{Colors.RED}[ERROR] Installation failed.{Colors.RESET}")

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
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}🔄 Deploying to test server...{Colors.RESET}\n")
    cmd = _build_deploy_cmd("deploy_freepbx_tools.py", "69.39.69.102")
    _run_with_credentials(cmd, username, password, root_password)

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
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--self-test", action="store_true", help="Run non-interactive sanity checks and exit")
    args, _unknown = ap.parse_known_args()

    if args.self_test:
        raise SystemExit(_self_test())

    while True:
        print_banner()
        print_menu()
        
        choice = input(f"{Colors.YELLOW}Choose option (1-10):{Colors.RESET} ").strip()
        
        if choice == "1":
            deploy_tools()
        elif choice == "2":
            uninstall_tools()
        elif choice == "11":
            push_traceroute_server_helper()
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
            validate_installer_uninstaller_symlinks()
        elif choice == "9":
            create_and_upload_offline_bundle()
        elif choice == "10":
            print(f"\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{Colors.RED}❌ Invalid choice. Please enter 1-10.{Colors.RESET}\n")
        
        input(f"\n{Colors.YELLOW}Press Enter to continue...{Colors.RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.GREEN}👋 Goodbye!{Colors.RESET}\n")
        sys.exit(0)
        sys.exit(0)
