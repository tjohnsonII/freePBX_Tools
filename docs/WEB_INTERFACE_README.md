# FreePBX Tools Manager - Web Interface

🌐 Modern web-based interface for managing FreePBX tool deployments and analysis.

## Features

### 🚀 Deployment Management
- **Single Server Deployment** - Deploy to one server with IP address
- **Multi-Server Deployment** - Deploy to multiple servers (comma-separated IPs)
- **Bulk Deployment** - Use server list files (ProductionServers.txt)
- **Live Progress Monitoring** - Real-time deployment logs via WebSocket
- **Multiple Actions**:
  - Install tools
  - Uninstall tools
  - Clean reinstall (uninstall + install)

### 📱 Phone Configuration Analyzer
- **Drag & Drop Interface** - Drop .cfg files directly into browser
- **Instant Analysis** - Analyze Yealink/Polycom configs
- **Security Scanning** - Check for weak passwords, default configs
- **JSON Export** - Download analysis results

### 🗄️ VPBX Database Queries
- **Pre-built Queries**:
  - Companies with Yealink phones
  - Search by phone model
  - Vendor statistics
  - Security issues
- **Interactive Results** - Sortable tables with export options
- **Custom Parameters** - Adjust limits, filters on the fly

### 📊 Status Dashboard
- **Active Deployments** - Track running operations
- **Historical Logs** - Review past deployments
- **Quick Access** - Jump to deployment details

## Installation

### 1. Install Python Dependencies

```bash
pip install -r web_requirements.txt
```

### 2. Start the Web Server

```bash
python web_manager.py
```

### 3. Access the Interface

Open your browser to:
```
http://localhost:5000
```

Or from another machine on your network:
```
http://YOUR_IP_ADDRESS:5000
```

## Usage

### Deploying Tools

1. **Select Server Target**:
   - Single server: Enter IP address
   - Multiple servers: Comma-separated IPs
   - Server file: Choose from dropdown (ProductionServers.txt)

2. **Enter Credentials**:
   - SSH username (default: 123net)
   - SSH password
   - Root password (optional if same as SSH)

3. **Choose Action**:
   - Install Tools
   - Uninstall Tools
   - Clean Reinstall

4. **Monitor Progress**:
   - Real-time logs appear in terminal window
   - Status badge shows completion status

### Analyzing Phone Configs

1. **Export Config from Phone**:
   - Access phone web interface
   - Settings > Configuration
   - Export "MAC-all.cfg" file

2. **Upload to Analyzer**:
   - Drag .cfg file to upload area
   - Or click to browse for file

3. **Review Results**:
   - Security issues highlighted
   - SIP account details
   - Network configuration
   - Feature status

### Running VPBX Queries

1. **Select Query Type**:
   - Choose from dropdown menu

2. **Set Parameters** (if applicable):
   - Model name for search
   - Result limit

3. **View Results**:
   - Interactive table
   - Sortable columns
   - Export to CSV

## Architecture

```
web_manager.py          # Flask application
├── /api/servers        # GET server list files
├── /api/deploy         # POST start deployment
├── /api/deployment/:id # GET deployment status
├── /api/phone-config/analyze  # POST analyze config
└── /api/vpbx/query     # POST database query

templates/
└── index.html          # Single-page application UI
```

### WebSocket Events

```
socket.emit('log', {deployment_id, message})
socket.emit('deployment_complete', {deployment_id, status})
```

## Security Notes

⚠️ **Important Security Considerations:**

1. **Credentials Handling**:
   - Passwords transmitted over HTTP (use HTTPS in production)
   - Temporary config.py created with credentials (deleted after use)
   - Never commit config.py to git

2. **Network Access**:
   - Web server binds to 0.0.0.0 (all interfaces)
   - Consider firewall rules in production
   - Use SSH tunneling for remote access

3. **Production Deployment**:
   ```bash
   # Use HTTPS with SSL certificate
   # Add authentication middleware
   # Enable rate limiting
   # Use environment variables for secrets
   ```

## Configuration

### Change Port

Edit `web_manager.py`:
```python
socketio.run(app, debug=True, host='0.0.0.0', port=5000)
                                                    ^^^^ Change here
```

### Enable HTTPS

```python
socketio.run(app, 
             host='0.0.0.0', 
             port=5000,
             certfile='cert.pem',
             keyfile='key.pem')
```

### Add Authentication

```python
from flask_httpauth import HTTPBasicAuth
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    # Your auth logic here
    return username == 'admin' and password == 'secret'

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')
```

## Troubleshooting

### Port Already in Use
```bash
# Change port in web_manager.py
# Or kill existing process:
lsof -ti:5000 | xargs kill
```

### WebSocket Connection Failed
- Check firewall settings
- Ensure Socket.IO CDN is accessible
- Try refreshing browser

### Database Not Found
```bash
# Ensure vpbx_data.db exists:
python create_vpbx_database.py
```

### Deployment Stuck
- Check SSH connectivity to target servers
- Verify credentials are correct
- Review deployment logs for errors

## Development

### Run in Debug Mode

```python
socketio.run(app, debug=True)
```

### Add New Query Type

1. Add option to HTML select:
```html
<option value="my_query">My Custom Query</option>
```

2. Add handler in `/api/vpbx/query`:
```python
elif query_type == 'my_query':
    cursor.execute("""
        SELECT * FROM sites WHERE ...
    """)
```

### Customize UI

Edit `templates/index.html`:
- Modify CSS variables for colors
- Add new tabs
- Customize layout

## License

Part of the FreePBX Tools suite.

## Support

For issues or questions:
- Check logs in browser console (F12)
- Review server logs in terminal
- Verify all dependencies installed
