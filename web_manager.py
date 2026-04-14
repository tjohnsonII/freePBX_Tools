#!/usr/bin/env python3

"""
Flask Web Interface for FreePBX Tools Manager
This script provides a web dashboard and API endpoints for managing FreePBX tools deployment,
running phone config analysis, and querying the VPBX database. It uses Flask for HTTP routes
and Flask-SocketIO for real-time log streaming.

VARIABLE MAP LEGEND
-------------------
app                : Flask app instance (main web server)
socketio           : Flask-SocketIO instance for real-time events
active_deployments : dict, deployment_id -> status ('running', 'completed', etc.)
deployment_logs    : dict, deployment_id -> list of log lines (for streaming to UI)

Key request/response variables:
    - servers        : List of server IPs for deployment (from POST data)
    - username       : SSH username for deployment
    - password       : SSH password for deployment
    - root_password  : Root password for deployment (optional)
    - action         : Deployment action ('deploy', 'uninstall', 'redeploy')
    - deployment_id  : Unique hex string for tracking a deployment session

Other:
    - config.py      : Temporary credentials file written for deployment scripts
    - process        : Subprocess running deployment or analysis scripts
    - thread         : Background thread for async deployment
    - temp_path      : Path to temporarily saved uploaded config file
    - query_type     : Type of canned DB query requested by UI
    - params         : Dict of parameters for DB query
"""

# Flask and SocketIO imports for web and real-time features
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
# Standard library imports
import os  # For file and directory operations
import sys  # For system-level operations
import subprocess  # For running deployment scripts
import threading  # For background thread management
import time  # For timing and delays
import secrets  # For generating secure tokens


def _try_import_paramiko():
    try:
        import paramiko  # type: ignore

        return paramiko
    except Exception:
        return None


def _posix_join_dir_file(remote_dir: str, filename: str) -> str:
    rd = (remote_dir or "").strip()
    if rd in ("", ".", "~"):
        return filename
    if rd.startswith("~/"):
        # Paramiko SFTP doesn't expand '~' reliably; treat it as relative to home.
        rd = rd[2:]
    if rd.startswith("/"):
        return rd.rstrip("/") + "/" + filename
    return rd.rstrip("/") + "/" + filename


def _sh_quote(s: str) -> str:
    """POSIX shell single-quote escaping."""

    return "'" + s.replace("'", "'\"'\"'") + "'"


def _shell_path_from_remote_dir(remote_dir: str, filename: str) -> str:
    """Build a remote path for shell commands, safely handling ~ expansion.

    We prefer $HOME over literal ~ because quoting ~ disables expansion.
    """

    rd = (remote_dir or "").strip()
    if rd in ("", "."):
        return filename
    if rd == "~":
        return "$HOME/" + filename
    if rd.startswith("~/"):
        return "$HOME/" + rd[2:].rstrip("/") + "/" + filename
    if rd.startswith("/"):
        return rd.rstrip("/") + "/" + filename
    return rd.rstrip("/") + "/" + filename


def _ssh_put_via_cat(ssh, local_path: str, remote_shell_path: str, log) -> None:
    """Upload a file without SFTP by streaming bytes to `cat > ...` over exec."""

    log("Falling back to streaming upload (no SFTP subsystem)...")
    stdin, stdout, stderr = ssh.exec_command(f"cat > {_sh_quote(remote_shell_path)}")
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        stdin.write(data)
        stdin.channel.shutdown_write()
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            try:
                err = (stderr.read() or b"").decode("utf-8", errors="replace").strip()
            except Exception:
                err = ""
            raise RuntimeError(f"remote cat failed (exit {rc}): {err}")
    finally:
        try:
            stdin.close()
        except Exception:
            pass


def _ssh_sftp_put_and_chmod(host: str, username: str, password: str, local_path: str, remote_dir: str, log) -> None:
    paramiko = _try_import_paramiko()
    if paramiko is None:
        raise RuntimeError("paramiko is required for password-based push. Install it with: pip install paramiko")

    filename = os.path.basename(local_path)
    remote_path = _posix_join_dir_file(remote_dir, filename)
    remote_shell_path = _shell_path_from_remote_dir(remote_dir, filename)
    log(f"Connecting to {username}@{host}...")

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

    try:
        if remote_dir and remote_dir not in (".", "~"):
            rd = remote_dir
            if rd.startswith("~/"):
                rd = rd[2:]
            if rd and rd not in (".", "~"):
                log(f"Ensuring remote dir exists: {remote_dir}")
                # Use $HOME-based shell pathing for ~ to avoid quoting issues.
                if remote_dir == "~":
                    ssh.exec_command("mkdir -p $HOME")
                elif remote_dir.startswith("~/"):
                    ssh.exec_command(f"mkdir -p {_sh_quote('$HOME/' + remote_dir[2:].rstrip('/'))}")
                else:
                    ssh.exec_command(f"mkdir -p {_sh_quote(remote_dir)}")

        log(f"Uploading to {remote_path}...")
        try:
            sftp = ssh.open_sftp()
            try:
                sftp.put(local_path, remote_path)
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass
        except Exception as e:
            log(f"SFTP failed: {e}")
            _ssh_put_via_cat(ssh, local_path, remote_shell_path, log)

        log("Applying chmod +x...")
        ssh.exec_command(f"chmod +x {_sh_quote(remote_shell_path)}")
        log("Upload complete.")
    finally:
        try:
            ssh.close()
        except Exception:
            pass


# Initialize Flask app and SocketIO for real-time communication
app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)  # Secure session key
socketio = SocketIO(app, cors_allowed_origins="*")  # Allow all origins for dev


# Dictionaries to track active deployments and their logs
active_deployments = {}  # deployment_id -> status
deployment_logs = {}     # deployment_id -> list of log lines


# Main dashboard route
@app.route('/')
def index():
    """Main dashboard page (renders index.html)"""
    return render_template('index.html')


# API endpoint to get available server lists (for UI dropdowns)
@app.route('/api/servers', methods=['GET'])
def get_servers():
    """Get available server lists (returns info about server files)"""
    server_files = []
    # Check for production server list
    if os.path.exists('ProductionServers.txt'):
        with open('ProductionServers.txt', 'r') as f:
            count = len([l for l in f.readlines() if l.strip()])  # Count non-empty lines
        server_files.append({
            'name': 'ProductionServers.txt',
            'count': count,
            'type': 'production'
        })
    # Check for custom server list
    if os.path.exists('server_ips.txt'):
        with open('server_ips.txt', 'r') as f:
            count = len([l for l in f.readlines() if l.strip()])
        server_files.append({
            'name': 'server_ips.txt',
            'count': count,
            'type': 'custom'
        })
    return jsonify(server_files)


# API endpoint to start a deployment process (runs in background thread)
@app.route('/api/deploy', methods=['POST'])
def deploy():
    """Start a deployment process (deploy, uninstall, or redeploy)"""
    data = request.get_json()  # Parse JSON body
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    servers = data.get('servers')  # List of server IPs
    username = data.get('username', '123net')  # SSH username
    password = data.get('password')  # SSH password
    root_password = data.get('root_password', password)  # Root password
    action = data.get('action', 'deploy')  # Action type
    if not password:
        return jsonify({'error': 'Password required'}), 400
    # Create temporary config.py with credentials for deployment scripts
    config_content = f"""# Temporary credentials
FREEPBX_USER = "{username}"
FREEPBX_PASSWORD = "***REMOVED***"
FREEPBX_ROOT_PASSWORD = "***REMOVED***"
"""
    with open('config.py', 'w') as f:
        f.write(config_content)
    # Generate unique deployment ID for tracking
    deployment_id = secrets.token_hex(8)
    # Background thread to run deployment so HTTP request returns immediately
    def run_deployment():
        try:
            deployment_logs[deployment_id] = []  # Initialize log list
            active_deployments[deployment_id] = 'running'  # Mark as running
            # Determine which script to run based on action
            if action == 'deploy':
                script = 'deploy_freepbx_tools.py'
            elif action == 'uninstall':
                script = 'deploy_uninstall_tools.py'
            elif action == 'redeploy':
                # Redeploy: uninstall first, then install
                socketio.emit('log', {
                    'deployment_id': deployment_id,
                    'message': '🔄 Phase 1: Uninstalling existing tools...'
                })
                subprocess.run(['python', 'deploy_uninstall_tools.py', '--servers', servers],
                             capture_output=True, text=True)
                

                socketio.emit('log', {
                    'deployment_id': deployment_id,
                    'message': '🔄 Phase 2: Installing tools...'
                })
                script = 'deploy_freepbx_tools.py'
            # Start the deployment script as a subprocess
            process = subprocess.Popen(
                ['python', script, '--servers', servers],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env={**os.environ, 'PYTHONUNBUFFERED': '1'},
            )
            # Stream output lines to web UI in real time
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    if line:
                        deployment_logs[deployment_id].append(line.strip())
                        socketio.emit('log', {
                            'deployment_id': deployment_id,
                            'message': line.strip()
                        })
            process.wait()  # Wait for process to finish
            # Mark deployment as completed or failed
            if process.returncode == 0:
                active_deployments[deployment_id] = 'completed'
                socketio.emit('deployment_complete', {
                    'deployment_id': deployment_id,
                    'status': 'success'
                })
            else:
                active_deployments[deployment_id] = 'failed'
                socketio.emit('deployment_complete', {
                    'deployment_id': deployment_id,
                    'status': 'failed'
                })
        except Exception as e:
            # Handle any errors in the deployment process
            active_deployments[deployment_id] = 'error'
            socketio.emit('deployment_complete', {
                'deployment_id': deployment_id,
                'status': 'error',
                'error': str(e)
            })
    # Start the deployment thread
    thread = threading.Thread(target=run_deployment)
    thread.daemon = True
    thread.start()
    # Return deployment ID to client
    return jsonify({
        'deployment_id': deployment_id,
        'status': 'started'
    })


# API endpoint to get deployment status and logs
@app.route('/api/deployment/<deployment_id>', methods=['GET'])
def get_deployment_status(deployment_id):
    """Get deployment status and logs for a given deployment ID"""
    return jsonify({
        'status': active_deployments.get(deployment_id, 'unknown'),
        'logs': deployment_logs.get(deployment_id, [])
    })


@app.route('/api/traceroute/push-helper', methods=['POST'])
def push_traceroute_helper():
    """Push scripts/traceroute_server_ctl.sh to a traceroute server.

    Returns a deployment_id; logs stream over the existing Socket.IO 'log' event.
    """

    data = request.get_json() or {}
    host = data.get('host', '192.168.50.1')
    username = data.get('username', 'tjohnson')
    password = data.get('password', '')
    remote_dir = data.get('remote_dir', '.')

    local_path = os.path.abspath(os.path.join('scripts', 'traceroute_server_ctl.sh'))
    if not os.path.exists(local_path):
        return jsonify({'error': f'Local helper not found: {local_path}'}), 500

    deployment_id = secrets.token_hex(8)

    def log(msg: str) -> None:
        deployment_logs.setdefault(deployment_id, []).append(msg)
        socketio.emit('log', {'deployment_id': deployment_id, 'message': msg})

    def run_push():
        try:
            active_deployments[deployment_id] = 'running'
            log('Starting traceroute helper push...')
            log(f'Local: {local_path}')
            log(f'Remote: {username}@{host} dir={remote_dir}')
            _ssh_sftp_put_and_chmod(host, username, password, local_path, remote_dir, log)
            active_deployments[deployment_id] = 'completed'
            socketio.emit('deployment_complete', {'deployment_id': deployment_id, 'status': 'success'})
        except Exception as e:
            active_deployments[deployment_id] = 'failed'
            log(f'ERROR: {e}')
            socketio.emit('deployment_complete', {'deployment_id': deployment_id, 'status': 'failed', 'error': str(e)})

    thread = threading.Thread(target=run_push)
    thread.daemon = True
    thread.start()

    return jsonify({'deployment_id': deployment_id, 'status': 'started'})


# API endpoint to analyze an uploaded phone configuration file
@app.route('/api/phone-config/analyze', methods=['POST'])
def analyze_phone_config():
    """Analyze phone configuration file (uploads, runs analyzer, returns JSON)"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not file.filename:
        return jsonify({'error': 'Invalid filename'}), 400
    # Save uploaded file temporarily to /tmp
    temp_path = os.path.join('/tmp', str(file.filename))
    file.save(temp_path)
    try:
        # Run analyzer script as subprocess
        result = subprocess.run(
            ['python', 'phone_config_analyzer.py', temp_path, '--json'],
            capture_output=True,
            text=True
        )
        # Parse JSON output from analyzer
        import json
        analysis = json.loads(result.stdout)
        return jsonify(analysis)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


# API endpoint to execute a VPBX database query (various canned queries)
@app.route('/api/vpbx/query', methods=['POST'])
def vpbx_query():
    """Execute VPBX database query (supports several query types)"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    query_type = data.get('query_type')
    params = data.get('params', {})
    import sqlite3
    try:
        conn = sqlite3.connect('vpbx_data.db')
        cursor = conn.cursor()
        # Run the appropriate query based on query_type
        if query_type == 'yealink_companies':
            cursor.execute("""
                SELECT s.company_name, s.system_ip, COUNT(d.id) as phone_count
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.vendor = 'yealink'
                GROUP BY s.company_name, s.system_ip
                ORDER BY phone_count DESC
                LIMIT ?
            """, (params.get('limit', 20),))
        elif query_type == 'model_search':
            model = params.get('model', '')
            cursor.execute("""
                SELECT s.company_name, s.system_ip, COUNT(d.id) as count
                FROM sites s
                JOIN devices d ON s.site_id = d.site_id
                WHERE d.model LIKE ?
                GROUP BY s.company_name, s.system_ip
                ORDER BY count DESC
            """, (f'%{model}%',))
        elif query_type == 'vendor_stats':
            cursor.execute("""
                SELECT vendor, COUNT(DISTINCT site_id) as sites, COUNT(*) as phones
                FROM devices
                WHERE vendor IS NOT NULL
                GROUP BY vendor
                ORDER BY phones DESC
            """)
        elif query_type == 'security_issues':
            cursor.execute("""
                SELECT s.site_id, s.company_name, s.system_ip,
                       si.severity, COUNT(*) as issue_count
                FROM sites s
                JOIN security_issues si ON s.site_id = si.site_id
                GROUP BY s.site_id, s.company_name, si.severity
                ORDER BY 
                    CASE si.severity 
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END,
                    issue_count DESC
            """)
        else:
            return jsonify({'error': 'Invalid query type'}), 400
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        # Convert results to list of dicts for JSON response
        data = [dict(zip(columns, row)) for row in results]
        conn.close()
        return jsonify({
            'results': data,
            'count': len(data)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


WEBSERVER_URLS = [
    'https://123hostedtools.com',
    'https://auth.123hostedtools.com',
    'https://tools.123hostedtools.com',
    'https://grafana.123hostedtools.com',
    'https://prtg.timsablab.ddns.net',
    'https://freepbx.timsablab.ddns.net',
    'https://mail.timsablab.ddns.net',
]

# Whitelisted SSH commands for webserver debugging
_WEBSERVER_ALLOWED_COMMANDS = {
    'apache_status':   'systemctl status apache2 --no-pager',
    'vhost_list':      'apachectl -S 2>&1',
    'config_test':     'apachectl configtest 2>&1',
    'reload_apache':   'sudo systemctl reload apache2',
    'check_all_vhosts': '/opt/vhost-tools/check-all-vhosts.sh 2>&1',
    'tail_error_log':  'tail -n 60 /var/log/apache2/error.log 2>&1',
    'tail_access_log': 'tail -n 60 /var/log/apache2/access.log 2>&1',
}


@app.route('/api/webserver/check-urls', methods=['POST'])
def webserver_check_urls():
    """HTTP health check for all known webserver vhost URLs."""
    import urllib.request
    import urllib.error
    import ssl
    import time

    data = request.get_json() or {}
    urls = data.get('urls') or WEBSERVER_URLS
    timeout = int(data.get('timeout', 8))

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    results = []
    for url in urls:
        start = time.time()
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                elapsed = int((time.time() - start) * 1000)
                results.append({
                    'url': url, 'status': resp.status,
                    'ok': resp.status < 400, 'ms': elapsed,
                    'error': None,
                })
        except urllib.error.HTTPError as e:
            elapsed = int((time.time() - start) * 1000)
            # 401/403 may be expected (FreePBX, restricted apps)
            results.append({
                'url': url, 'status': e.code,
                'ok': e.code in (401, 403), 'ms': elapsed,
                'error': None,
            })
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            results.append({
                'url': url, 'status': None,
                'ok': False, 'ms': elapsed,
                'error': str(e),
            })
    return jsonify({'results': results})


@app.route('/api/webserver/ssh-run', methods=['POST'])
def webserver_ssh_run():
    """Run a whitelisted Apache/webserver command over SSH and return output."""
    data = request.get_json() or {}
    host = data.get('host', '192.168.100.10')
    username = data.get('username', 'tim2')
    password = data.get('password', '')
    command_key = data.get('command', '')

    if command_key not in _WEBSERVER_ALLOWED_COMMANDS:
        return jsonify({'error': f'Unknown command key: {command_key}. '
                        f'Allowed: {list(_WEBSERVER_ALLOWED_COMMANDS)}'}), 400

    shell_cmd = _WEBSERVER_ALLOWED_COMMANDS[command_key]

    paramiko = _try_import_paramiko()
    if paramiko is None:
        return jsonify({'error': 'paramiko not installed. Run: pip install paramiko'}), 500

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username,
                    password=password or None,
                    timeout=15, allow_agent=True, look_for_keys=True)
        _, stdout, stderr = ssh.exec_command(shell_cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        rc = stdout.channel.recv_exit_status()
        ssh.close()
        return jsonify({'ok': rc == 0, 'rc': rc,
                        'output': out or err, 'command': shell_cmd})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/webserver/check-one-vhost', methods=['POST'])
def webserver_check_one_vhost():
    """Run /opt/vhost-tools/check-one-vhost.sh <hostname> <backend_url> over SSH."""
    data = request.get_json() or {}
    host = data.get('host', '192.168.100.10')
    username = data.get('username', 'tim2')
    password = data.get('password', '')
    vhost = (data.get('vhost') or '').strip()
    backend = (data.get('backend') or 'http://127.0.0.1').strip()

    if not vhost:
        return jsonify({'error': 'vhost is required'}), 400

    # Sanitize: only allow hostname chars and dots/dashes
    import re
    if not re.match(r'^[a-zA-Z0-9.\-]+$', vhost):
        return jsonify({'error': 'Invalid vhost name'}), 400

    shell_cmd = f'/opt/vhost-tools/check-one-vhost.sh {_sh_quote(vhost)} {_sh_quote(backend)} 2>&1'

    paramiko = _try_import_paramiko()
    if paramiko is None:
        return jsonify({'error': 'paramiko not installed'}), 500

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username,
                    password=password or None,
                    timeout=15, allow_agent=True, look_for_keys=True)
        _, stdout, stderr = ssh.exec_command(shell_cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        rc = stdout.channel.recv_exit_status()
        ssh.close()
        return jsonify({'ok': rc == 0, 'rc': rc,
                        'output': out or err, 'command': shell_cmd})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Main entry point: start the Flask web server with SocketIO
if __name__ == '__main__':
    print("🌐 Starting FreePBX Tools Manager Web Interface...")
    print("📱 Access at: http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
