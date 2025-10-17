#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_callflow_menu.py
Menu-driven wrapper to:
  1) snapshot FreePBX data -> JSON (via freepbx_dump.py)
  2) render SVG call-flow(s) for selected or all DIDs (via freepbx_callflow_graph.py)
Python 3.6 safe. No external modules.
"""

import json, os, sys, subprocess, time

DUMP_SCRIPT   = "/usr/local/bin/freepbx_dump.py"
GRAPH_SCRIPT  = "/usr/local/bin/freepbx_callflow_graph.py"
OUT_DIR       = "/home/123net/callflows"
DUMP_PATH     = os.path.join(OUT_DIR, "freepbx_dump.json")
DB_USER       = "root"
DEFAULT_SOCK  = "/var/lib/mysql/mysql.sock"
TC_STATUS_SCRIPT = "/usr/local/bin/freepbx_tc_status.py"
MODULE_ANALYZER_SCRIPT = "/usr/local/bin/freepbx_module_analyzer.py"


def run_tc_status(sock):
    """Invoke the time-condition status tool."""
    if not os.path.isfile(TC_STATUS_SCRIPT):
        print("Time Condition status tool not found at", TC_STATUS_SCRIPT)
        return
    print("\n=== Time Conditions: current override + last *code use ===\n")
    rc, out, err = run(["python3", TC_STATUS_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())


def run_module_analyzer(sock):
    """Invoke the FreePBX module analyzer tool."""
    if not os.path.isfile(MODULE_ANALYZER_SCRIPT):
        print("Module analyzer tool not found at", MODULE_ANALYZER_SCRIPT)
        return
    print("\n=== FreePBX Module Analysis ===\n")
    rc, out, err = run(["python3", MODULE_ANALYZER_SCRIPT, "--socket", sock, "--db-user", DB_USER])
    if rc == 0:
        print(out, end="")
    else:
        print((err or out).strip())


# ---------------- helpers ----------------

def run(cmd, env=None):
    """subprocess.run wrapper (3.6-safe: universal_newlines instead of text=)."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    return p.returncode, (p.stdout or ""), (p.stderr or "")

def detect_mysql_socket():
    rc, out, _ = run(["bash", "-lc", "mysql -NBe 'SHOW VARIABLES LIKE \"socket\";' 2>/dev/null | awk '{print $2}'"])
    path = (out.strip().splitlines() or [""])[0]
    return path if path else DEFAULT_SOCK

def ensure_outdir():
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
    except Exception:
        pass

def load_dump():
    if not os.path.isfile(DUMP_PATH):
        return {}
    with open(DUMP_PATH, "r") as f:
        return json.load(f)

def refresh_dump(sock):
    ensure_outdir()
    print("\n[+] Refreshing FreePBX snapshot (this reads MySQL)…")
    cmd = ["python3", DUMP_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--out", DUMP_PATH]
    rc, out, err = run(cmd)
    if rc == 0:
        print("    ✓ Snapshot written to", DUMP_PATH)
        return True
    print("    ✖ Snapshot failed:\n" + (err or out))
    return False

def summarize(data):
    def count(key, sub=None):
        if key not in data: return 0
        if sub:
            return len(data[key].get(sub, []))
        return len(data[key])
    print("\n=== Inventory ===")
    print(" Host:            {}".format(data.get("meta", {}).get("hostname", "")))
    print(" FreePBX version: {}".format(data.get("meta", {}).get("freepbx_version", "")))
    print(" MySQL version:   {}".format(data.get("meta", {}).get("mysql_version", "")))
    print(" Generated:       {}".format(data.get("meta", {}).get("generated_at_utc", "")))
    print("")
    print(" Inbound routes (DIDs):     {:>4}".format(count("inbound")))
    print(" IVRs (menus):              {:>4}".format(count("ivrs", "menus")))
    print(" IVR options:               {:>4}".format(count("ivrs", "options")))
    print(" Queues:                    {:>4}".format(count("queues")))
    print(" Ring groups:               {:>4}".format(count("ringgroups")))
    print(" Time conditions:           {:>4}".format(count("timeconditions")))
    print(" Time groups:               {:>4}".format(count("timegroups")))
    print(" Announcements:             {:>4}".format(count("announcements")))
    print(" Extensions:                {:>4}".format(count("extensions")))
    print(" Trunks:                    {:>4}".format(len(data.get("trunks", {}).get("trunks", []))))
    print(" Outbound routes:           {:>4}".format(len(data.get("outbound", {}).get("routes", []))))
    print(" Outbound patterns:         {:>4}".format(len(data.get("outbound", {}).get("patterns", []))))
    print("")

def list_dids(data, show_limit=50):
    dids = data.get("inbound", [])
    rows = []
    for i, r in enumerate(dids, 1):
        label = r.get("label") or ""
        cid   = r.get("cid") or ""
        dest  = r.get("destination") or ""
        rows.append((i, r.get("did",""), label, cid, dest))
    if not rows:
        print("No inbound routes found.")
        return []
    print("Index | DID           | Label                         | CID   | Destination")
    print("------+---------------+-------------------------------+-------+-------------------------------")
    for i, did, label, cid, dest in rows[:show_limit]:
        print("{:>5} | {:<13} | {:<29} | {:<5} | {}".format(i, did, label[:29], cid[:5], dest[:40]))
    if len(rows) > show_limit:
        print("… {} more not shown. (Use selection to target them anyway.)".format(len(rows) - show_limit))
    return rows

def parse_selection(sel, max_index):
    sel = sel.strip()
    if sel in ("*", "all", "ALL"):
        return list(range(1, max_index+1))
    chosen = set()
    for part in sel.split(","):
        part = part.strip()
        if not part: continue
        if "-" in part:
            a,b = part.split("-",1)
            try:
                a, b = int(a), int(b)
                for x in range(min(a,b), max(a,b)+1):
                    if 1 <= x <= max_index: chosen.add(x)
            except ValueError:
                pass
        else:
            try:
                x = int(part)
                if 1 <= x <= max_index: chosen.add(x)
            except ValueError:
                pass
    return sorted(chosen)

def render_dids(did_rows, indexes, sock, skip_labels=None):
    ensure_outdir()
    ok = 0; bad = 0
    for idx in indexes:
        _, did, label, _, _ = did_rows[idx-1]
        if skip_labels and label and label.strip().lower() in skip_labels:
            print("• Skipping DID {} (label='{}')".format(did, label))
            continue
        out_file = os.path.join(OUT_DIR, "callflow_{}.svg".format(did))
        cmd = ["python3", GRAPH_SCRIPT, "--socket", sock, "--db-user", DB_USER, "--did", str(did), "--out", out_file]
        rc, out, err = run(cmd)
        if rc == 0 and os.path.isfile(out_file):
            print("✓ DID {} -> {}".format(did, out_file))
            ok += 1
        else:
            print("✖ DID {} FAILED: {}".format(did, (err or out).strip()))
            bad += 1
    print("\nDone. Success: {}, Failed: {}".format(ok, bad))

# ---------------- menu ----------------

def main():
    if not os.path.isfile(DUMP_SCRIPT):
        print("ERROR: {} not found.".format(DUMP_SCRIPT)); sys.exit(1)
    if not os.path.isfile(GRAPH_SCRIPT):
        print("ERROR: {} not found.".format(GRAPH_SCRIPT)); sys.exit(1)

    sock = detect_mysql_socket()
    data = load_dump()
    if not data:
        # first run: force snapshot so menu has content
        if not refresh_dump(sock):
            sys.exit(1)
        data = load_dump()

    while True:
        print("\n========== FreePBX Call-Flow Menu ==========")
        print(" 1) Refresh DB snapshot")
        print(" 2) Show inventory (counts) + list DIDs")
        print(" 3) Generate call-flow for selected DID(s)")
        print(" 4) Generate call-flows for ALL DIDs")
        print(" 5) Generate call-flows for ALL DIDs (skip labels: OPEN)")
        print(" 6) Show Time-Condition status (+ last *code use)")
        print(" 7) Run FreePBX module analysis")
        print(" 8) Run full Asterisk diagnostic")
        print(" 9) Quit")
        choice = input("\nChoose: ").strip()

        if choice == "1":
            if refresh_dump(sock):
                data = load_dump()

        elif choice == "2":
            summarize(data)
            list_dids(data)

        elif choice == "3":
            did_rows = list_dids(data)
            if not did_rows: continue
            sel = input("\nEnter indexes (e.g. 1,3,5-8) or * for all: ")
            idxs = parse_selection(sel, len(did_rows))
            if not idxs:
                print("No valid selection.")
                continue
            render_dids(did_rows, idxs, sock)

        elif choice == "4":
            did_rows = list_dids(data, show_limit=0) or list_dids(data)  # ensures we have rows
            if not did_rows: continue
            render_dids(did_rows, list(range(1, len(did_rows)+1)), sock)

        elif choice == "5":
            did_rows = list_dids(data, show_limit=0) or list_dids(data)
            if not did_rows: continue
            # lowercase match set; you can add more labels here if you want to exclude them
            render_dids(did_rows, list(range(1, len(did_rows)+1)), sock,
                        skip_labels=set(["open"]))

        elif choice == "6":
            run_tc_status(sock)

        elif choice == "7":
            run_module_analyzer(sock)

        elif choice == "8":
            diag = "/usr/local/bin/asterisk-full-diagnostic.sh"
            if not os.path.isfile(diag):
                print("Diagnostic script not found at", diag)
            else:
                print("\nRunning full diagnostic (this may take ~10–30s)…\n")
                rc, out, err = run([diag])
                # The script prints its own output; nothing else to do.

        elif choice == "9":
            print("Bye.")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
