#!/usr/bin/env python

# Python 2-compatible traceroute HTTP server (FreeBSD-friendly)
# - Threaded server for concurrent requests
# - Supports ICMP (default), TCP mode via query param
# - Adjustable per-hop wait, query count, max TTL
# - Returns partial results on timeout instead of failing
# - Minimal CORS for integration with Next.js

import BaseHTTPServer
import SocketServer
import urlparse
import subprocess
import socket
import json
import urllib2
import re
import time
import logging
import threading
import os
import signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    daemon_threads = True

class TracerouteHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    server_version = "TracerouteHTTP/1.0"

    def log_message(self, fmt, *args):
        try:
            logging.info("%s - %s" % (self.address_string(), fmt % args))
        except Exception:
            pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse.urlparse(self.path)
        if parsed.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path == '/health':
            return self._send_json({'ok': True, 'ts': int(time.time())}, 200)

        params = urlparse.parse_qs(parsed.query or '')
        target = params.get('target', [''])[0]
        mode = params.get('mode', [''])[0]  # 'icmp' or 'tcp'
        try:
            wait = float(params.get('w', ['1'])[0])
        except Exception:
            wait = 1.0
        try:
            queries = int(params.get('q', ['1'])[0])
        except Exception:
            queries = 1
        try:
            max_ttl = int(params.get('m', ['20'])[0])
        except Exception:
            max_ttl = 20
        try:
            port = int(params.get('port', ['80'])[0])
        except Exception:
            port = 80
        resolve = params.get('resolve', ['false'])[0].lower() in ('1', 'true', 'yes')
        try:
            budget = int(params.get('budget', ['40'])[0])
        except Exception:
            budget = 40

        if not target:
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write("Missing 'target' parameter")
            return

        logging.info("Traceroute request target=%s mode=%s w=%s q=%s m=%s port=%s resolve=%s budget=%s", target, mode or 'icmp', wait, queries, max_ttl, port, resolve, budget)

        cmd = ['traceroute']
        if not resolve:
            cmd.append('-n')
        cmd.extend(['-w', str(wait), '-q', str(queries), '-m', str(max_ttl)])
        if mode == 'tcp':
            cmd.extend(['-P', 'tcp', '-p', str(port)])
        else:
            cmd.append('-I')
        cmd.append(target)

        start_ts = time.time()
        lines = []
        timed_out = False

        def reader(proc, sink):
            try:
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    sink.append(line)
            except Exception as e:
                logging.warning("stdout reader error: %s", str(e))

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
        except Exception as e:
            logging.error("Failed to start traceroute: %s", str(e))
            return self._send_json({'error': 'Failed to start traceroute', 'detail': str(e)}, 500)

        t = threading.Thread(target=reader, args=(proc, lines))
        t.daemon = True
        t.start()

        t.join(budget)
        if t.is_alive():
            timed_out = True
            try:
                try:
                    proc.terminate()
                except Exception:
                    pass
                time.sleep(0.5)
                if proc.poll() is None:
                    os.kill(proc.pid, signal.SIGKILL)
            except Exception as e:
                logging.warning("Failed to kill traceroute: %s", str(e))

        try:
            proc.wait()
        except Exception:
            pass

        # Parse output
        # Skip header lines until first hop line
        hops = []
        hop_counter = 1
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            # skip header which typically starts with 'traceroute to'
            if hop_counter == 1 and line.lower().startswith('traceroute to'):
                continue

            ip = "No response"
            latency = "---"
            hostname = "No response"
            geo = {"city": "", "country": "", "lat": None, "lon": None}

            if '* * *' in line or re.search(r'\*', line):
                # no response hop
                pass
            else:
                m = re.match(r'^(\d+)\s+([0-9.]+)\s+(\d+\.?\d*)\s+ms', line)
                if m:
                    ip = m.group(2)
                    latency = m.group(3) + " ms"
                    if resolve:
                        try:
                            hostname = socket.gethostbyaddr(ip)[0]
                        except Exception:
                            hostname = ip
                    else:
                        hostname = ip

                    try:
                        geo_url = "http://ip-api.com/json/%s" % ip
                        resp = urllib2.urlopen(geo_url, timeout=2)
                        data = json.load(resp)
                        geo = {
                            "city": data.get("city", ""),
                            "country": data.get("country", ""),
                            "lat": data.get("lat"),
                            "lon": data.get("lon"),
                        }
                    except Exception:
                        geo = {"city": "", "country": "", "lat": None, "lon": None}

                else:
                    # Unknown line format, keep as no response
                    pass

            hops.append({
                "hop": hop_counter,
                "ip": ip,
                "hostname": hostname,
                "latency": latency,
                "geo": geo,
            })
            hop_counter += 1

        elapsed = round(time.time() - start_ts, 3)
        result = {
            "target": target,
            "mode": (mode or 'icmp'),
            "hops": hops,
            "timed_out": timed_out,
            "elapsed_sec": elapsed,
        }

        status = 206 if timed_out else 200
        return self._send_json(result, status)

def run(host='', port=8000):
    server_address = (host, port)
    httpd = ThreadedHTTPServer(server_address, TracerouteHandler)
    print("Traceroute server listening on port %d..." % port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
