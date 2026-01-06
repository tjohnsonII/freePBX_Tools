"""
chrome_cookies_live.py
Extracts live cookies from a running Chrome instance using the DevTools Protocol.
Requires: pip install requests
"""
import requests
import json
import sys

def get_chrome_cookies(domain=None, port=9222):
    # Get list of open tabs
    try:
        tabs = requests.get(f"http://localhost:{port}/json").json()
    except Exception as e:
        print(f"[ERROR] Could not connect to Chrome DevTools: {e}")
        return []
    if not tabs:
        print("[ERROR] No tabs found. Is Chrome running with --remote-debugging-port?")
        return []
    # Use the first tab for session
    tab = tabs[0]
    ws_url = tab.get('webSocketDebuggerUrl')
    if not ws_url:
        print("[ERROR] No WebSocket debugger URL found.")
        return []
    # Use the DevTools Protocol to get cookies
    import websocket
    import threading
    import time
    cookies = []
    result = {}
    def on_message(ws, message):
        msg = json.loads(message)
        if 'result' in msg and 'cookies' in msg['result']:
            result['cookies'] = msg['result']['cookies']
            ws.close()
    def on_error(ws, error):
        print(f"[ERROR] WebSocket error: {error}")
        ws.close()
    def on_close(ws, close_status_code, close_msg):
        pass
    def on_open(ws):
        # Send command to get all cookies
        if domain:
            cmd = {
                "id": 1,
                "method": "Network.getCookies",
                "params": {"urls": [domain]}
            }
        else:
            cmd = {
                "id": 1,
                "method": "Network.getAllCookies"
            }
        ws.send(json.dumps(cmd))
    ws = websocket.WebSocketApp(ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open)
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    timeout = 5
    for _ in range(timeout * 10):
        if 'cookies' in result:
            break
        time.sleep(0.1)
    ws.close()
    return result.get('cookies', [])

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract live cookies from Chrome via DevTools Protocol.")
    parser.add_argument('--domain', type=str, help='Domain to filter cookies (e.g. https://example.com)')
    parser.add_argument('--port', type=int, default=9222, help='DevTools port (default: 9222)')
    parser.add_argument('--output', type=str, help='Output file (JSON)')
    args = parser.parse_args()
    cookies = get_chrome_cookies(args.domain, args.port)
    print(f"[INFO] Extracted {len(cookies)} cookies.")
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2)
        print(f"[INFO] Cookies saved to {args.output}")
    else:
        print(json.dumps(cookies, indent=2))

if __name__ == "__main__":
    main()
