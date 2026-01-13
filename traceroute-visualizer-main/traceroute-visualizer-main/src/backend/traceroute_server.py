#!/usr/local/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false

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

LOG_PATH = os.environ.get('TRACEROUTE_LOG', '/tmp/traceroute_server.log')
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format='%(asctime)s %(message)s')


class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _json_bytes(obj):
    try:
        return json.dumps(obj).encode('utf-8')
    except Exception:
        return ('{"error":"Failed to serialize JSON"}').encode('utf-8')


def _send_json(handler, obj, status=200):
    body = _json_bytes(obj)
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _safe_float(s):
    try:
        return float(s)
    except Exception:
        return None


class TracerouteHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    server_version = "TracerouteHTTP/1.1"

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
            return _send_json(self, {'ok': True, 'ts': int(time.time())}, 200)

        params = urlparse.parse_qs(parsed.query or '')
        target = params.get('target', [''])[0]

        # Optional tunables
        mode = (params.get('mode', ['icmp'])[0] or 'icmp').lower()  # icmp|tcp
        resolve = (params.get('resolve', ['0'])[0] or '0').lower() in ('1', 'true', 'yes')
        w = params.get('w', ['2'])[0]
        q = params.get('q', ['3'])[0]
        m = params.get('m', ['20'])[0]
        port = params.get('port', ['80'])[0]
        budget = params.get('budget', ['40'])[0]  # total wall-clock seconds

        try:
            budget = int(budget)
        except Exception:
            budget = 40

        if not target:
            return _send_json(self, {"error": "Missing 'target' parameter"}, 400)

        logging.info("Traceroute request target=%s mode=%s resolve=%s w=%s q=%s m=%s port=%s budget=%s",
                     target, mode, resolve, w, q, m, port, budget)

        cmd = ['traceroute']
        if not resolve:
            cmd.append('-n')

        # Common flags (work on most Linux; FreeBSD supports -w -q -m as well)
        cmd.extend(['-w', str(w), '-q', str(q), '-m', str(m)])

        if mode == 'tcp':
            # Linux traceroute: -T for TCP, FreeBSD: -P tcp -p PORT
            # We'll try the FreeBSD-style first if available.
            cmd.extend(['-P', 'tcp', '-p', str(port)])
        else:
            # Prefer ICMP when available
            cmd.append('-I')

        cmd.append(target)

        start_ts = time.time()
        lines = []
        timed_out = False

        def reader(proc, sink):
            try:
                while True:
                    chunk = proc.stdout.readline()
                    if not chunk:
                        break
                    sink.append(chunk)
            except Exception as e:
                logging.warning("stdout reader error: %s", str(e))

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
        except Exception as e:
            logging.error("Failed to start traceroute: %s", str(e))
            return _send_json(self, {'error': 'Failed to start traceroute', 'detail': str(e)}, 500)

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
                    kill_sig = getattr(signal, 'SIGKILL', signal.SIGTERM)
                    os.kill(proc.pid, kill_sig)
            except Exception as e:
                logging.warning("Failed to kill traceroute: %s", str(e))

        try:
            proc.wait()
        except Exception:
            pass

        # Decode and parse traceroute output
        decoded = []
        for raw in lines:
            try:
                if isinstance(raw, bytes):
                    decoded.append(raw.decode('utf-8', 'ignore'))
                else:
                    decoded.append(raw)
            except Exception:
                decoded.append(str(raw))

        hops = []
        hop_counter = 1
        for raw in decoded:
            line = (raw or '').strip()
            if not line:
                continue
            if hop_counter == 1 and line.lower().startswith('traceroute to'):
                continue

            ip = "No response"
            latency = "---"
            hostname = "No response"
            geo = {"city": "", "country": "", "lat": None, "lon": None}

            if '* * *' in line or '*' in line:
                pass
            else:
                # Example: "1 192.168.1.1 0.123 ms 0.456 ms 0.789 ms"
                m1 = re.match(r'^(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+ms', line)
                if m1:
                    ip = m1.group(2)
                    latency = m1.group(3) + " ms"
                    hostname = ip
                    if resolve:
                        try:
                            hostname = socket.gethostbyaddr(ip)[0]
                        except Exception:
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
            "mode": mode,
            "hops": hops,
            "timed_out": timed_out,
            "elapsed_sec": elapsed,
        }

        status = 206 if timed_out else 200
        return _send_json(self, result, status)


def run(port=8000, host=''):
    server_address = (host, port)
    httpd = ThreadedHTTPServer(server_address, TracerouteHandler)
    print("Traceroute server listening on %s:%d..." % (host or '0.0.0.0', port))
    httpd.serve_forever()


if __name__ == '__main__':
    run()