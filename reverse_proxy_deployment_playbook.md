# Reverse Proxy Deployment Playbook

## Purpose

This playbook is the standard process for publishing internal web apps in the lab without exposing random backend ports or re-solving DNS, TLS, and Apache issues every time.

Use this for any new app behind the Apache reverse proxy on `192.168.100.10`.

Core model:

`hostname -> DNS -> 192.168.100.10 -> Apache -> backend app`

---

## Environment Baseline

### Reverse proxy

- Apache server IP: `192.168.100.10`
- Apache listens on: `80`, `443`
- Public NAT forwards: `80` and `443` to `192.168.100.10`

### DNS

- Internal DNS: Windows DNS
- Common internal zone: `timsablab.ddns.net`
- Additional zone in use: `123hostedtools.com`
- Internal app hostnames should resolve to: `192.168.100.10`

### Apache config locations

- Site definitions: `/etc/apache2/sites-available/`
- Enabled site symlinks: `/etc/apache2/sites-enabled/`
- LetsEncrypt certs: `/etc/letsencrypt/live/`
- Global Apache error log: `/var/log/apache2/error.log`
- Per-app logs: `/var/log/apache2/<app>-error.log`, `/var/log/apache2/<app>-access.log`

### Required Apache commands

```bash
sudo apachectl configtest
sudo apachectl -S
sudo systemctl reload apache2
sudo systemctl restart apache2
sudo ss -tlnp | grep -E ':80|:443'
```

### Common Apache modules

```bash
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod headers
sudo a2enmod ssl
```

---

## Golden Rules

1. **DNS points to Apache, not the backend app.**
2. **Get HTTP working first. Add SSL second.**
3. **Never expose app ports publicly if Apache is fronting them.**
4. **Edit files in `sites-available`, not random files in `sites-enabled`.**
5. **Always test from the Apache server using `--resolve` before blaming browsers.**
6. **For HTTPS backends, Apache must proxy HTTPS to HTTPS.**
7. **Use per-app logs.**
8. **Use one naming pattern and stick to it.**
9. **Track each app: hostname, backend IP, backend port, protocol, Apache files, DNS record, cert status.**
10. **If the backend uses a self-signed or mismatched cert, disable SSL proxy verification in Apache.**

---

## Standard Deployment Workflow

### Step 1: Pick the hostname

Examples:

- `notes.timsablab.ddns.net`
- `api.timsablab.ddns.net`
- `portfolio.timsablab.ddns.net`
- `netbox.timsablab.ddns.net`

### Step 2: Identify backend target

Examples:

- `http://127.0.0.1:3001`
- `http://192.168.30.120:5000`
- `https://192.168.99.43:8090`

### Step 3: Confirm backend works directly

HTTP backend:

```bash
curl -I http://127.0.0.1:3001/
```

HTTPS backend:

```bash
curl -kI https://192.168.99.43:8090/
```

If backend does not work here, stop.

### Step 4: Create HTTP vhost

Create a file in `/etc/apache2/sites-available/`.

### Step 5: Enable the site

```bash
sudo a2ensite hostname.conf
```

### Step 6: Test Apache config

```bash
sudo apachectl configtest
```

Expected:

```text
Syntax OK
```

### Step 7: Reload Apache

```bash
sudo systemctl reload apache2
```

### Step 8: Local Apache test before DNS/browser work

HTTP:

```bash
curl -I --resolve hostname:80:127.0.0.1 http://hostname/
```

HTTPS:

```bash
curl -vkI --resolve hostname:443:127.0.0.1 https://hostname/
```

### Step 9: Create or verify DNS record points to `192.168.100.10`

PowerShell example:

```powershell
Add-DnsServerResourceRecordA -ZoneName "timsablab.ddns.net" -Name "notes" -IPv4Address "192.168.100.10"
```

Verify:

```powershell
Get-DnsServerResourceRecord -ZoneName "timsablab.ddns.net" -Name "notes"
nslookup notes.timsablab.ddns.net
Resolve-DnsName notes.timsablab.ddns.net
```

Expected:

```text
192.168.100.10
```

### Step 10: Get SSL cert

```bash
sudo certbot --apache -d hostname
```

### Step 11: If backend is HTTPS, fix generated SSL vhost

Certbot generates the `-le-ssl.conf` file, but HTTPS backends often need manual edits.

### Step 12: Convert HTTP vhost into redirect-only after SSL works

```apache
<VirtualHost *:80>
    ServerName hostname
    Redirect permanent / https://hostname/
</VirtualHost>
```

### Step 13: Final reload

```bash
sudo apachectl configtest
sudo systemctl reload apache2
```

### Step 14: Final tests

Server-side:

```bash
curl -vkI --resolve hostname:443:127.0.0.1 https://hostname/
```

Client-side:

```powershell
ipconfig /flushdns
nslookup hostname
Test-NetConnection hostname -Port 443
```

---

## HTTP Backend Template

Use this when the backend app speaks plain HTTP.

### HTTP Example

- Hostname: `notes.timsablab.ddns.net`
- Backend: `http://127.0.0.1:3001`

### HTTP Initial vhost

```bash
sudo tee /etc/apache2/sites-available/notes.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName notes.timsablab.ddns.net

    ProxyRequests Off
    ProxyPreserveHost On
    ProxyAddHeaders On

    ProxyPass / http://127.0.0.1:3001/
    ProxyPassReverse / http://127.0.0.1:3001/

    ErrorLog ${APACHE_LOG_DIR}/notes-error.log
    CustomLog ${APACHE_LOG_DIR}/notes-access.log combined
</VirtualHost>
EOF
```

### HTTP Enable and reload

```bash
sudo a2ensite notes.timsablab.ddns.net.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

### HTTP Test locally

```bash
curl -I http://127.0.0.1:3001/
curl -I --resolve notes.timsablab.ddns.net:80:127.0.0.1 http://notes.timsablab.ddns.net/
```

### HTTP DNS

```powershell
Add-DnsServerResourceRecordA -ZoneName "timsablab.ddns.net" -Name "notes" -IPv4Address "192.168.100.10"
ipconfig /flushdns
nslookup notes.timsablab.ddns.net
```

### HTTP Certbot

```bash
sudo certbot --apache -d notes.timsablab.ddns.net
```

### HTTP Final redirect file

```bash
sudo tee /etc/apache2/sites-available/notes.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName notes.timsablab.ddns.net
    Redirect permanent / https://notes.timsablab.ddns.net/
</VirtualHost>
EOF
```

### HTTP Final HTTPS test

```bash
sudo apachectl configtest
sudo systemctl reload apache2
curl -vkI --resolve notes.timsablab.ddns.net:443:127.0.0.1 https://notes.timsablab.ddns.net/
```

---

## HTTPS Backend Template

Use this when the backend app itself already serves HTTPS.

### HTTPS Example

- Hostname: `prtg.timsablab.ddns.net`
- Backend: `https://192.168.99.43:8090`

### HTTPS Initial vhost

```bash
sudo tee /etc/apache2/sites-available/prtg.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName prtg.timsablab.ddns.net

    ProxyRequests Off
    ProxyPreserveHost On
    ProxyAddHeaders On

    SSLProxyEngine On
    SSLProxyVerify none
    SSLProxyCheckPeerName off
    SSLProxyCheckPeerCN off

    ProxyPass / https://192.168.99.43:8090/
    ProxyPassReverse / https://192.168.99.43:8090/

    ErrorLog ${APACHE_LOG_DIR}/prtg-error.log
    CustomLog ${APACHE_LOG_DIR}/prtg-access.log combined
</VirtualHost>
EOF
```

### HTTPS Enable and reload

```bash
sudo a2ensite prtg.timsablab.ddns.net.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

### HTTPS Test backend directly

```bash
curl -kI https://192.168.99.43:8090/
```

### HTTPS Certbot

```bash
sudo certbot --apache -d prtg.timsablab.ddns.net
```

### HTTPS Fix generated SSL vhost

```bash
sudo tee /etc/apache2/sites-available/prtg.timsablab.ddns.net-le-ssl.conf > /dev/null <<'EOF'
<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName prtg.timsablab.ddns.net

    SSLEngine on
    SSLProxyEngine On
    ProxyPreserveHost On

    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Forwarded-Port "443"

    SSLProxyVerify none
    SSLProxyCheckPeerName off
    SSLProxyCheckPeerCN off

    ProxyPass / https://192.168.99.43:8090/
    ProxyPassReverse / https://192.168.99.43:8090/

    ErrorLog ${APACHE_LOG_DIR}/prtg-error.log
    CustomLog ${APACHE_LOG_DIR}/prtg-access.log combined

    SSLCertificateFile /etc/letsencrypt/live/prtg.timsablab.ddns.net/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/prtg.timsablab.ddns.net/privkey.pem
    Include /etc/letsencrypt/options-ssl-apache.conf
</VirtualHost>
</IfModule>
EOF
```

### HTTPS Convert to redirect-only

```bash
sudo tee /etc/apache2/sites-available/prtg.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName prtg.timsablab.ddns.net
    Redirect permanent / https://prtg.timsablab.ddns.net/
</VirtualHost>
EOF
```

### HTTPS Final test

```bash
sudo apachectl configtest
sudo systemctl reload apache2
curl -vkI --resolve prtg.timsablab.ddns.net:443:127.0.0.1 https://prtg.timsablab.ddns.net/
```

Expected response example:

```text
HTTP/1.1 302 Moved Temporarily
Server: PRTG
Location: /index.htm
```

---

## Node.js Example

### Node.js Scenario

- App: `portfolio.timsablab.ddns.net`
- Backend: `http://127.0.0.1:3005`

### Node.js Run backend

```bash
node server.js
```

Better long-term:

```bash
pm2 start server.js --name portfolio
pm2 save
pm2 startup
```

### Node.js Verify backend

```bash
curl -I http://127.0.0.1:3005/
```

### Node.js Apache vhost

```bash
sudo tee /etc/apache2/sites-available/portfolio.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName portfolio.timsablab.ddns.net

    ProxyRequests Off
    ProxyPreserveHost On
    ProxyAddHeaders On

    ProxyPass / http://127.0.0.1:3005/
    ProxyPassReverse / http://127.0.0.1:3005/

    ErrorLog ${APACHE_LOG_DIR}/portfolio-error.log
    CustomLog ${APACHE_LOG_DIR}/portfolio-access.log combined
</VirtualHost>
EOF
```

### Node.js Enable and reload

```bash
sudo a2ensite portfolio.timsablab.ddns.net.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

### Node.js DNS

```powershell
Add-DnsServerResourceRecordA -ZoneName "timsablab.ddns.net" -Name "portfolio" -IPv4Address "192.168.100.10"
ipconfig /flushdns
nslookup portfolio.timsablab.ddns.net
```

### Node.js SSL

```bash
sudo certbot --apache -d portfolio.timsablab.ddns.net
```

### Node.js Redirect HTTP to HTTPS

```bash
sudo tee /etc/apache2/sites-available/portfolio.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName portfolio.timsablab.ddns.net
    Redirect permanent / https://portfolio.timsablab.ddns.net/
</VirtualHost>
EOF
```

### Node.js Final test

```bash
sudo apachectl configtest
sudo systemctl reload apache2
curl -vkI --resolve portfolio.timsablab.ddns.net:443:127.0.0.1 https://portfolio.timsablab.ddns.net/
```

---

## Python / FastAPI Example

### FastAPI Scenario

- App: `api.timsablab.ddns.net`
- Backend: `http://127.0.0.1:8000`

### FastAPI Run backend

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

### FastAPI Verify backend

```bash
curl -I http://127.0.0.1:8000/
```

### FastAPI Apache vhost

```bash
sudo tee /etc/apache2/sites-available/api.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName api.timsablab.ddns.net

    ProxyRequests Off
    ProxyPreserveHost On
    ProxyAddHeaders On

    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/

    ErrorLog ${APACHE_LOG_DIR}/api-error.log
    CustomLog ${APACHE_LOG_DIR}/api-access.log combined
</VirtualHost>
EOF
```

### FastAPI Enable and reload

```bash
sudo a2ensite api.timsablab.ddns.net.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

### FastAPI DNS

```powershell
Add-DnsServerResourceRecordA -ZoneName "timsablab.ddns.net" -Name "api" -IPv4Address "192.168.100.10"
ipconfig /flushdns
nslookup api.timsablab.ddns.net
```

### FastAPI SSL

```bash
sudo certbot --apache -d api.timsablab.ddns.net
```

### FastAPI Redirect HTTP to HTTPS

```bash
sudo tee /etc/apache2/sites-available/api.timsablab.ddns.net.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName api.timsablab.ddns.net
    Redirect permanent / https://api.timsablab.ddns.net/
</VirtualHost>
EOF
```

### FastAPI Final test

```bash
sudo apachectl configtest
sudo systemctl reload apache2
curl -vkI --resolve api.timsablab.ddns.net:443:127.0.0.1 https://api.timsablab.ddns.net/
```

---

## Command-Only Quick Checklist

### HTTP backend app

```bash
sudo tee /etc/apache2/sites-available/APP.DOMAIN.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName APP.DOMAIN
    ProxyRequests Off
    ProxyPreserveHost On
    ProxyAddHeaders On
    ProxyPass / http://BACKEND_HOST:BACKEND_PORT/
    ProxyPassReverse / http://BACKEND_HOST:BACKEND_PORT/
    ErrorLog ${APACHE_LOG_DIR}/APP-error.log
    CustomLog ${APACHE_LOG_DIR}/APP-access.log combined
</VirtualHost>
EOF

sudo a2ensite APP.DOMAIN.conf
sudo apachectl configtest
sudo systemctl reload apache2
curl -I http://BACKEND_HOST:BACKEND_PORT/
curl -I --resolve APP.DOMAIN:80:127.0.0.1 http://APP.DOMAIN/
sudo certbot --apache -d APP.DOMAIN
```

### HTTPS backend app

```bash
sudo tee /etc/apache2/sites-available/APP.DOMAIN.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName APP.DOMAIN
    ProxyRequests Off
    ProxyPreserveHost On
    ProxyAddHeaders On
    SSLProxyEngine On
    SSLProxyVerify none
    SSLProxyCheckPeerName off
    SSLProxyCheckPeerCN off
    ProxyPass / https://BACKEND_HOST:BACKEND_PORT/
    ProxyPassReverse / https://BACKEND_HOST:BACKEND_PORT/
    ErrorLog ${APACHE_LOG_DIR}/APP-error.log
    CustomLog ${APACHE_LOG_DIR}/APP-access.log combined
</VirtualHost>
EOF

sudo a2ensite APP.DOMAIN.conf
sudo apachectl configtest
sudo systemctl reload apache2
curl -kI https://BACKEND_HOST:BACKEND_PORT/
sudo certbot --apache -d APP.DOMAIN
```

---

## Troubleshooting Matrix

| Symptom | Meaning | First check |
| --- | --- | --- |
| Old personal site loads | Default Apache vhost caught request | `sudo apachectl -S` |
| MikroTik login loads | Request hit router, not Apache | DNS + router web service |
| `502 Proxy Error` | Apache matched but backend target/protocol is wrong | backend curl + Apache vhost |
| `ERR_CONNECTION_REFUSED` | Nothing listening or path blocked | `Test-NetConnection`, Apache listen, firewall |
| Wrong cert | Wrong SSL vhost matched or stale client cache | `curl --resolve ... 127.0.0.1` |
| Browser shows old content | Client cache or stale DNS | `ipconfig /flushdns`, incognito |

---

## Deployed Apps Tracking Table

| App | Hostname | Backend Protocol | Backend IP | Backend Port | DNS Target | HTTP Vhost | HTTPS Vhost | Cert Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRTG | `prtg.timsablab.ddns.net` | HTTPS | `192.168.99.43` | `8090` | `192.168.100.10` | `prtg.timsablab.ddns.net.conf` | `prtg.timsablab.ddns.net-le-ssl.conf` | Working | Apache proxies HTTPS-to-HTTPS |
| Grafana | `grafana.123hostedtools.com` | HTTP | `192.168.99.187` | `3000` | `192.168.100.10` | `grafana.123hostedtools.com.conf` | `grafana.123hostedtools.com-le-ssl.conf` | Working | Apache proxies HTTP backend |
| FreePBX | `freepbx.timsablab.ddns.net` | HTTPS | `192.168.142.42` | `443` | `192.168.100.10` | `freepbx.timsablab.ddns.net.conf` | `freepbx.timsablab.ddns.net-le-ssl.conf` | Working | HTTPS backend |
| Mail | `mail.timsablab.ddns.net` | HTTPS | `192.168.30.103` | `443` | `192.168.100.10` | `mail.timsablab.ddns.net.conf` | `mail.timsablab.ddns.net-le-ssl.conf` | Working | Path-based proxy |

---

## Final Notes

If a new app fails, do not jump straight into browser guessing. Use this order:

1. Backend direct curl
2. Apache local `--resolve` curl
3. `apachectl -S`
4. DNS resolution
5. Client network test
6. Apache logs

That order will save you a ton of time.
