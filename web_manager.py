#!/usr/bin/env python3
"""
Flask Web Interface for FreePBX Tools Manager
"""
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
import os
import sys
import subprocess
import threading
import time
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*")

# Store active deployments
active_deployments = {}
deployment_logs = {}

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/api/servers', methods=['GET'])
def get_servers():
    """Get available server lists"""
    server_files = []
    
    if os.path.exists('ProductionServers.txt'):
        with open('ProductionServers.txt', 'r') as f:
            count = len([l for l in f.readlines() if l.strip()])
        server_files.append({
            'name': 'ProductionServers.txt',
            'count': count,
            'type': 'production'
        })
    
    if os.path.exists('server_ips.txt'):
        with open('server_ips.txt', 'r') as f:
            count = len([l for l in f.readlines() if l.strip()])
        server_files.append({
            'name': 'server_ips.txt',
            'count': count,
            'type': 'custom'
        })
    
    return jsonify(server_files)

@app.route('/api/deploy', methods=['POST'])
def deploy():
    """Start a deployment process"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    servers = data.get('servers')
    username = data.get('username', '123net')
    password = data.get('password')
    root_password = data.get('root_password', password)
    action = data.get('action', 'deploy')  # deploy, uninstall, or redeploy
    
    if not password:
        return jsonify({'error': 'Password required'}), 400
    
    # Create temporary config
    config_content = f"""# Temporary credentials
FREEPBX_USER = "{username}"
FREEPBX_PASSWORD = "***REMOVED***"
FREEPBX_ROOT_PASSWORD = "***REMOVED***"
"""
    
    with open('config.py', 'w') as f:
        f.write(config_content)
    
    # Generate deployment ID
    deployment_id = secrets.token_hex(8)
    
    # Start deployment in background thread
    def run_deployment():
        try:
            deployment_logs[deployment_id] = []
            active_deployments[deployment_id] = 'running'
            
            if action == 'deploy':
                script = 'deploy_freepbx_tools.py'
            elif action == 'uninstall':
                script = 'deploy_uninstall_tools.py'
            elif action == 'redeploy':
                # First uninstall, then install
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
            
            # Run deployment
            process = subprocess.Popen(
                ['python', script, '--servers', servers],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Stream output
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    if line:
                        deployment_logs[deployment_id].append(line.strip())
                        socketio.emit('log', {
                            'deployment_id': deployment_id,
                            'message': line.strip()
                        })
            
            process.wait()
            
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
            active_deployments[deployment_id] = 'error'
            socketio.emit('deployment_complete', {
                'deployment_id': deployment_id,
                'status': 'error',
                'error': str(e)
            })
    
    thread = threading.Thread(target=run_deployment)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'deployment_id': deployment_id,
        'status': 'started'
    })

@app.route('/api/deployment/<deployment_id>', methods=['GET'])
def get_deployment_status(deployment_id):
    """Get deployment status"""
    return jsonify({
        'status': active_deployments.get(deployment_id, 'unknown'),
        'logs': deployment_logs.get(deployment_id, [])
    })

@app.route('/api/phone-config/analyze', methods=['POST'])
def analyze_phone_config():
    """Analyze phone configuration file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    # Save uploaded file temporarily
    temp_path = os.path.join('/tmp', str(file.filename))
    file.save(temp_path)
    
    try:
        # Run analyzer
        result = subprocess.run(
            ['python', 'phone_config_analyzer.py', temp_path, '--json'],
            capture_output=True,
            text=True
        )
        
        # Parse JSON output
        import json
        analysis = json.loads(result.stdout)
        
        return jsonify(analysis)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.route('/api/vpbx/query', methods=['POST'])
def vpbx_query():
    """Execute VPBX database query"""
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    query_type = data.get('query_type')
    params = data.get('params', {})
    
    import sqlite3
    
    try:
        conn = sqlite3.connect('vpbx_data.db')
        cursor = conn.cursor()
        
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
        
        # Convert to list of dicts
        data = [dict(zip(columns, row)) for row in results]
        
        conn.close()
        
        return jsonify({
            'results': data,
            'count': len(data)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🌐 Starting FreePBX Tools Manager Web Interface...")
    print("📱 Access at: http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
