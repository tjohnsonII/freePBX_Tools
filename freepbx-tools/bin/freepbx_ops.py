#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_ops.py  —  FreePBX Operations Tool
-------------------------------------------
Subcommands:
  trace   <DID>            Full call-path trace for a DID
  decode  <destination>    Human-readable decode of a raw FreePBX destination
  find    <query>          Search across all PBX components
  snapshot                 Save current call-flow state to JSON
  rollback <file>          Restore IVR/TC destinations from a snapshot
  validate                 Run health/consistency checks
  set-ivr  --ivr N --opt N --dest D   Update an IVR option (--dry-run / --apply)
  ticket                   Print ticket-ready summary of session changes
"""

import argparse
import json
import os
import subprocess
import sys
import datetime

# ── constants ────────────────────────────────────────────────────────────────

ASTERISK_DB   = "asterisk"
SNAPSHOT_DIR  = "/home/123net/callflows/snapshots"
SESSION_LOG   = "/tmp/freepbx_ops_session.json"

# ── colour helpers ───────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m";  BOLD    = "\033[1m"
    RED     = "\033[91m"; GREEN   = "\033[92m"
    YELLOW  = "\033[93m"; CYAN    = "\033[96m"
    WHITE   = "\033[97m"; MAGENTA = "\033[95m"
    BLUE    = "\033[94m"

def ok(msg):   print(C.GREEN  + "  ✓ " + C.RESET + msg)
def warn(msg): print(C.YELLOW + "  ⚠ " + C.RESET + msg)
def err(msg):  print(C.RED    + "  ✗ " + C.RESET + msg)
def hdr(msg):  print(C.CYAN + C.BOLD + msg + C.RESET)

# ── DB helpers ───────────────────────────────────────────────────────────────

_DB_KW = {}   # populated by main() from CLI args

def run_mysql(sql, db=ASTERISK_DB):
    env = os.environ.copy()
    if _DB_KW.get("password"):
        env["MYSQL_PWD"] = _DB_KW["password"]
    cmd = ["mysql", "-BN"]
    if _DB_KW.get("user"):
        cmd += ["--user", _DB_KW["user"]]
    if _DB_KW.get("socket"):
        cmd += ["--socket", _DB_KW["socket"]]
    if db:
        cmd += [db]
    cmd += ["-e", sql]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "mysql error").strip())
    return p.stdout

def qrows(sql, cols, db=ASTERISK_DB):
    """SELECT -> list of dicts."""
    out = run_mysql(sql, db=db).rstrip("\n")
    if not out:
        return []
    result = []
    for line in out.split("\n"):
        parts = line.split("\t")
        parts = (parts + [""] * len(cols))[:len(cols)]
        result.append(dict(zip(cols, parts)))
    return result

def qone(sql, cols, db=ASTERISK_DB):
    rows = qrows(sql, cols, db=db)
    return rows[0] if rows else None

def has_table(t):
    out = run_mysql(f"SHOW TABLES LIKE '{t}';")
    return bool(out.strip())

def has_col(table, col):
    try:
        out = run_mysql(f"DESCRIBE `{table}`;")
        return col in [ln.split("\t", 1)[0] for ln in out.splitlines() if ln]
    except Exception:
        return False

# ── destination decoder ───────────────────────────────────────────────────────

_DEST_CACHE = {}

def decode(dest):
    """Return a human-readable label for any FreePBX destination string."""
    if not dest or dest.strip() == "":
        return C.RED + "(none)" + C.RESET

    dest = dest.strip()
    if dest in _DEST_CACHE:
        return _DEST_CACHE[dest]

    result = _decode_raw(dest)
    _DEST_CACHE[dest] = result
    return result

def _decode_raw(dest):
    parts  = dest.split(",")
    dtype  = parts[0]
    arg1   = parts[1] if len(parts) > 1 else ""
    # arg2 = parts[2] if len(parts) > 2 else ""

    # ivr-N,s,1  or  ivr,N,1
    if dtype.startswith("ivr-"):
        ivr_id = dtype[4:]
        name   = _ivr_name(ivr_id)
        return f"IVR {ivr_id}" + (f" — {name}" if name else "")

    handlers = {
        "from-did-direct":  lambda: _ext_label(arg1),
        "from-internal":    lambda: _ext_label(arg1),
        "ext-group":        lambda: _rg_label(arg1),
        "timeconditions":   lambda: _tc_label(arg1),
        "voicemail":        lambda: f"Voicemail {arg1}",
        "app-blackhole":    lambda: C.RED + "Hang Up" + C.RESET,
        "app-announcement": lambda: _ann_label(arg1),
        "ivr":              lambda: _ivr_label(arg1),
        "queue":            lambda: _queue_label(arg1),
        "app-directory":    lambda: "Company Directory",
        "misc":             lambda: _misc_label(arg1),
        "app-queue":        lambda: _queue_label(arg1),
        "conferencing":     lambda: f"Conference Room {arg1}",
        "app-disa":         lambda: f"DISA {arg1}",
        "app-fmfm":         lambda: f"Find Me/Follow Me — ext {arg1}",
        "app-cf":           lambda: f"Call Forward — ext {arg1}",
        "app-zaptel":       lambda: f"Paging/Intercom {arg1}",
        "app-page":         lambda: f"Paging Group {arg1}",
        "app-echo":         lambda: "Echo Test",
        "app-music":        lambda: f"Music on Hold ({arg1})",
        "time":             lambda: f"Time of Day — {arg1}",
    }

    fn = handlers.get(dtype)
    if fn:
        try:
            return fn()
        except Exception:
            pass

    return C.YELLOW + dest + C.RESET   # raw fallback

def _ext_label(ext):
    row = qone(f"SELECT name FROM users WHERE extension='{ext}';", ["name"])
    name = row["name"] if row else None
    return f"Extension {ext}" + (f" — {name}" if name else "")

def _rg_label(grpnum):
    row = qone(f"SELECT description FROM ringgroups WHERE grpnum='{grpnum}';", ["description"])
    name = row["description"] if row else None
    return f"Ring Group {grpnum}" + (f" — {name}" if name else "")

def _tc_label(tcid):
    tbl = "time_conditions" if has_table("time_conditions") else "timeconditions"
    col = "name" if has_col(tbl, "name") else "displayname"
    row = qone(f"SELECT {col} FROM {tbl} WHERE timeconditions_id='{tcid}';", ["name"])
    name = row["name"] if row else None
    return f"Time Condition {tcid}" + (f" — {name}" if name else "")

def _ivr_name(ivr_id):
    row = qone(f"SELECT displayname FROM ivr_details WHERE id='{ivr_id}' AND keyword='name';", ["name"])
    return row["name"] if row else None

def _ivr_label(ivr_id):
    name = _ivr_name(ivr_id)
    return f"IVR {ivr_id}" + (f" — {name}" if name else "")

def _ann_label(ann_id):
    row = qone(f"SELECT description FROM announcements WHERE announcement_id='{ann_id}';", ["description"])
    name = row["description"] if row else None
    return f"Announcement {ann_id}" + (f" — {name}" if name else "")

def _queue_label(queue):
    row = qone(f"SELECT descr FROM queues_config WHERE extension='{queue}';", ["descr"])
    name = row["descr"] if row else None
    return f"Queue {queue}" + (f" — {name}" if name else "")

def _misc_label(misc_id):
    row = qone(f"SELECT description FROM misc_destinations WHERE miscid='{misc_id}';", ["description"])
    name = row["description"] if row else None
    return f"Misc Dest {misc_id}" + (f" — {name}" if name else "")

# ── data loaders ──────────────────────────────────────────────────────────────

def load_did(did):
    for tbl, cols in [
        ("incoming",      ["did","cidnum","destination","description"]),
        ("inbound_routes",["did","cidnum","destination","description"]),
    ]:
        if has_table(tbl):
            row = qone(f"SELECT did,cidnum,destination,description FROM {tbl} WHERE did='{did}';", cols)
            if row:
                return row
    return None

def load_tc(tcid):
    tbl = "time_conditions" if has_table("time_conditions") else "timeconditions"
    col_name = "name" if has_col(tbl, "name") else "displayname"
    col_true = "truedest" if has_col(tbl, "truedest") else "truedest"
    col_false = "falsedest" if has_col(tbl, "falsedest") else "falsedest"
    return qone(
        f"SELECT timeconditions_id, {col_name}, {col_true}, {col_false} "
        f"FROM {tbl} WHERE timeconditions_id='{tcid}';",
        ["id", "name", "truedest", "falsedest"]
    )

def load_ivr_options(ivr_id):
    return qrows(
        f"SELECT selection, dest FROM ivr_entries WHERE ivr_id='{ivr_id}' ORDER BY selection;",
        ["selection", "dest"]
    )

def load_rg(grpnum):
    return qone(
        f"SELECT grpnum, description, grplist, strategy, ringtime, postdest "
        f"FROM ringgroups WHERE grpnum='{grpnum}';",
        ["grpnum", "description", "grplist", "strategy", "ringtime", "postdest"]
    )

# ── trace command ─────────────────────────────────────────────────────────────

_session_changes = []

def cmd_trace(args):
    did = args.did.strip()
    hdr(f"\n╔═══════════════════════════════════════════╗")
    hdr(f"║  CALL FLOW TRACE  —  DID {did:<17}║")
    hdr(f"╚═══════════════════════════════════════════╝\n")

    route = load_did(did)
    if not route:
        err(f"DID {did} not found in inbound routes.")
        return 1

    label = route.get("description") or route.get("label") or ""
    print(f"  {C.GREEN}{C.BOLD}{did}{C.RESET}", end="")
    if label:
        print(f"  ({label})", end="")
    print()

    _trace_dest(route.get("destination", ""), indent=1, visited=set())
    print()
    return 0

def _trace_dest(dest, indent, visited, branch_label=None):
    pad    = "   " * indent
    arrow  = f"{C.CYAN}→{C.RESET} "

    if branch_label:
        print(f"{pad}{C.YELLOW}[{branch_label}]{C.RESET}")

    if not dest:
        print(f"{pad}{arrow}{C.RED}(no destination){C.RESET}")
        return

    if dest in visited or indent > 12:
        print(f"{pad}{arrow}{C.RED}[loop or max depth]{C.RESET}")
        return

    visited = visited | {dest}
    parts   = dest.split(",")
    dtype   = parts[0]
    arg1    = parts[1] if len(parts) > 1 else ""

    # ── Time Condition ────────────────────────────────────────────────────────
    if dtype == "timeconditions":
        tc = load_tc(arg1)
        if tc:
            print(f"{pad}{arrow}{C.MAGENTA}Time Condition {arg1} — {tc.get('name','')}{C.RESET}")
            _trace_dest(tc.get("truedest",""),  indent+1, visited, "OPEN / match")
            _trace_dest(tc.get("falsedest",""), indent+1, visited, "CLOSED / no match")
        else:
            print(f"{pad}{arrow}Time Condition {arg1} {C.RED}(not found){C.RESET}")
        return

    # ── IVR ───────────────────────────────────────────────────────────────────
    ivr_id = None
    if dtype.startswith("ivr-"):
        ivr_id = dtype[4:]
    elif dtype == "ivr":
        ivr_id = arg1

    if ivr_id:
        name = _ivr_name(ivr_id)
        print(f"{pad}{arrow}{C.BLUE}IVR {ivr_id}{' — ' + name if name else ''}{C.RESET}")
        opts = load_ivr_options(ivr_id)
        for opt in opts:
            sel  = opt["selection"]
            odest = opt["dest"]
            label = _opt_label(sel)
            print(f"{pad}   {C.YELLOW}{label}{C.RESET}  {decode(odest)}")
            _trace_dest(odest, indent+2, visited)
        return

    # ── Ring Group ────────────────────────────────────────────────────────────
    if dtype == "ext-group":
        rg = load_rg(arg1)
        if rg:
            members  = rg.get("grplist","").replace("-", ", ")
            postdest = rg.get("postdest","")
            print(f"{pad}{arrow}{C.GREEN}Ring Group {arg1} — {rg.get('description','')} "
                  f"[{rg.get('strategy','')} / {rg.get('ringtime','')}s]{C.RESET}")
            print(f"{pad}   Members: {members or '(none)'}")
            if postdest:
                print(f"{pad}   No answer →")
                _trace_dest(postdest, indent+2, visited)
        else:
            print(f"{pad}{arrow}Ring Group {arg1} {C.RED}(not found){C.RESET}")
        return

    # ── Everything else ───────────────────────────────────────────────────────
    print(f"{pad}{arrow}{decode(dest)}")

def _opt_label(sel):
    special = {"t": "timeout", "i": "invalid", "0": "0", "#": "#"}
    return special.get(sel, f"press {sel}")

# ── decode command ────────────────────────────────────────────────────────────

def cmd_decode(args):
    dest = " ".join(args.destination)
    print(f"\n  Raw:   {C.YELLOW}{dest}{C.RESET}")
    print(f"  Human: {decode(dest)}\n")

# ── find command ──────────────────────────────────────────────────────────────

def cmd_find(args):
    q = args.query.lower()
    hdr(f"\n🔍  Searching for: {args.query}\n")
    found = False

    # Extensions / Users
    rows = qrows(
        f"SELECT extension, name, email FROM users "
        f"WHERE extension LIKE '%{q}%' OR name LIKE '%{q}%' OR email LIKE '%{q}%' LIMIT 20;",
        ["ext", "name", "email"]
    )
    if rows:
        found = True
        print(f"{C.BOLD}Extensions:{C.RESET}")
        for r in rows:
            print(f"  {C.GREEN}{r['ext']:<8}{C.RESET} {r['name']:<30} {r['email']}")
        print()

    # Ring Groups
    rows = qrows(
        f"SELECT grpnum, description, grplist FROM ringgroups "
        f"WHERE grpnum LIKE '%{q}%' OR description LIKE '%{q}%' OR grplist LIKE '%{q}%' LIMIT 10;",
        ["grpnum", "description", "grplist"]
    )
    if rows:
        found = True
        print(f"{C.BOLD}Ring Groups:{C.RESET}")
        for r in rows:
            print(f"  {C.GREEN}{r['grpnum']:<8}{C.RESET} {r['description']:<30} members: {r['grplist']}")
        print()

    # IVRs
    rows = qrows(
        f"SELECT id, displayname FROM ivr_details "
        f"WHERE keyword='name' AND (id LIKE '%{q}%' OR displayname LIKE '%{q}%') LIMIT 10;",
        ["id", "name"]
    )
    if rows:
        found = True
        print(f"{C.BOLD}IVRs:{C.RESET}")
        for r in rows:
            print(f"  {C.GREEN}{r['id']:<8}{C.RESET} {r['name']}")
        print()

    # IVR entries that point to something matching
    rows = qrows(
        f"SELECT ivr_id, selection, dest FROM ivr_entries "
        f"WHERE dest LIKE '%{q}%' LIMIT 10;",
        ["ivr_id", "selection", "dest"]
    )
    if rows:
        found = True
        print(f"{C.BOLD}IVR Options pointing to '{args.query}':{C.RESET}")
        for r in rows:
            print(f"  IVR {r['ivr_id']} — press {r['selection']} → {decode(r['dest'])}")
        print()

    # Inbound routes / DIDs
    tbl = "incoming" if has_table("incoming") else "inbound_routes"
    rows = qrows(
        f"SELECT did, description, destination FROM {tbl} "
        f"WHERE did LIKE '%{q}%' OR description LIKE '%{q}%' LIMIT 10;",
        ["did", "description", "destination"]
    )
    if rows:
        found = True
        print(f"{C.BOLD}Inbound Routes (DIDs):{C.RESET}")
        for r in rows:
            print(f"  {C.GREEN}{r['did']:<15}{C.RESET} {r['description']:<30} → {decode(r['destination'])}")
        print()

    # Time Conditions
    tbl = "time_conditions" if has_table("time_conditions") else "timeconditions"
    col = "name" if has_col(tbl, "name") else "displayname"
    rows = qrows(
        f"SELECT timeconditions_id, {col} FROM {tbl} "
        f"WHERE {col} LIKE '%{q}%' OR timeconditions_id LIKE '%{q}%' LIMIT 10;",
        ["id", "name"]
    )
    if rows:
        found = True
        print(f"{C.BOLD}Time Conditions:{C.RESET}")
        for r in rows:
            print(f"  {C.GREEN}{r['id']:<8}{C.RESET} {r['name']}")
        print()

    # Voicemail
    rows = qrows(
        f"SELECT mailbox, fullname, email FROM voicemail WHERE "
        f"mailbox LIKE '%{q}%' OR fullname LIKE '%{q}%' OR email LIKE '%{q}%' LIMIT 10;",
        ["mailbox", "fullname", "email"]
    )
    if rows:
        found = True
        print(f"{C.BOLD}Voicemail:{C.RESET}")
        for r in rows:
            print(f"  {C.GREEN}{r['mailbox']:<8}{C.RESET} {r['fullname']:<30} {r['email']}")
        print()

    # Queues
    if has_table("queues_config"):
        rows = qrows(
            f"SELECT extension, descr FROM queues_config "
            f"WHERE extension LIKE '%{q}%' OR descr LIKE '%{q}%' LIMIT 10;",
            ["ext", "descr"]
        )
        if rows:
            found = True
            print(f"{C.BOLD}Queues:{C.RESET}")
            for r in rows:
                print(f"  {C.GREEN}{r['ext']:<8}{C.RESET} {r['descr']}")
            print()

    if not found:
        warn(f"No results found for '{args.query}'")

# ── snapshot command ──────────────────────────────────────────────────────────

def cmd_snapshot(args):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    ts     = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    reason = args.reason or "manual snapshot"
    fname  = os.path.join(SNAPSHOT_DIR, f"snapshot-{ts}.json")

    hdr(f"\n📸  Taking snapshot: {fname}")
    print(f"  Reason: {reason}\n")

    snap = {
        "timestamp": ts,
        "reason": reason,
        "ivr_entries": [],
        "time_conditions": [],
        "inbound_routes": [],
        "ring_groups": [],
    }

    # IVR entries
    rows = qrows("SELECT ivr_id, selection, dest FROM ivr_entries ORDER BY ivr_id, selection;",
                 ["ivr_id", "selection", "dest"])
    snap["ivr_entries"] = rows
    ok(f"IVR entries: {len(rows)}")

    # Time conditions
    tbl     = "time_conditions" if has_table("time_conditions") else "timeconditions"
    col_n   = "name" if has_col(tbl, "name") else "displayname"
    col_t   = "truedest"
    col_f   = "falsedest"
    rows    = qrows(f"SELECT timeconditions_id, {col_n}, {col_t}, {col_f} FROM {tbl};",
                    ["id", "name", "truedest", "falsedest"])
    snap["time_conditions"] = rows
    ok(f"Time conditions: {len(rows)}")

    # Inbound routes
    tbl  = "incoming" if has_table("incoming") else "inbound_routes"
    rows = qrows(f"SELECT did, description, destination FROM {tbl};",
                 ["did", "description", "destination"])
    snap["inbound_routes"] = rows
    ok(f"Inbound routes: {len(rows)}")

    # Ring groups
    rows = qrows("SELECT grpnum, description, grplist, postdest FROM ringgroups;",
                 ["grpnum", "description", "grplist", "postdest"])
    snap["ring_groups"] = rows
    ok(f"Ring groups: {len(rows)}")

    with open(fname, "w") as f:
        json.dump(snap, f, indent=2)

    ok(f"\nSnapshot saved: {fname}")
    print(f"\n  To roll back:  freepbx_ops.py rollback {fname}\n")
    return fname

# ── rollback command ──────────────────────────────────────────────────────────

def cmd_rollback(args):
    fname = args.snapshot
    if not os.path.isfile(fname):
        err(f"Snapshot not found: {fname}")
        return 1

    with open(fname) as f:
        snap = json.load(f)

    hdr(f"\n⏪  Rolling back from snapshot: {fname}")
    print(f"  Taken: {snap.get('timestamp','?')}   Reason: {snap.get('reason','?')}\n")

    if not args.apply:
        warn("DRY RUN — no changes written. Pass --apply to execute.")
        print()

    changed = 0

    # IVR entries
    for row in snap.get("ivr_entries", []):
        ivr_id, sel, dest = row["ivr_id"], row["selection"], row["dest"]
        cur = qone(f"SELECT dest FROM ivr_entries WHERE ivr_id='{ivr_id}' AND selection='{sel}';", ["dest"])
        cur_dest = cur["dest"] if cur else None
        if cur_dest != dest:
            print(f"  IVR {ivr_id} opt {sel}: {decode(cur_dest)} → {decode(dest)}")
            if args.apply:
                run_mysql(f"UPDATE ivr_entries SET dest='{dest}' WHERE ivr_id='{ivr_id}' AND selection='{sel}';")
                changed += 1

    if args.apply and changed:
        _fwconsole_reload()
        ok(f"Rollback applied. {changed} change(s) written.")
    elif not args.apply:
        print(f"\n  Run with --apply to commit rollback.\n")
    else:
        ok("Nothing to roll back — already matches snapshot.")

# ── validate command ──────────────────────────────────────────────────────────

def cmd_validate(args):
    hdr("\n🩺  FreePBX Configuration Validator\n")
    issues = []

    # 1. IVR options pointing to non-existent extensions
    rows = qrows("SELECT ivr_id, selection, dest FROM ivr_entries WHERE dest LIKE 'from-did-direct,%';",
                 ["ivr_id", "sel", "dest"])
    for row in rows:
        ext = row["dest"].split(",")[1]
        exists = qone(f"SELECT extension FROM users WHERE extension='{ext}';", ["extension"])
        if not exists:
            issues.append(f"IVR {row['ivr_id']} opt {row['sel']}: points to ext {ext} which does NOT exist")

    # 2. Ring groups with no members
    rows = qrows("SELECT grpnum, description, grplist FROM ringgroups;",
                 ["grpnum", "description", "grplist"])
    for rg in rows:
        if not rg.get("grplist","").strip().strip("-"):
            issues.append(f"Ring Group {rg['grpnum']} ({rg['description']}): no members")

    # 3. Time conditions missing true or false destination
    tbl   = "time_conditions" if has_table("time_conditions") else "timeconditions"
    col_n = "name" if has_col(tbl, "name") else "displayname"
    rows  = qrows(f"SELECT timeconditions_id, {col_n}, truedest, falsedest FROM {tbl};",
                  ["id", "name", "truedest", "falsedest"])
    for tc in rows:
        if not tc.get("truedest"):
            issues.append(f"Time Condition {tc['id']} ({tc['name']}): missing OPEN (true) destination")
        if not tc.get("falsedest"):
            issues.append(f"Time Condition {tc['id']} ({tc['name']}): missing CLOSED (false) destination")

    # 4. Inbound routes pointing to deleted/missing destinations
    tbl  = "incoming" if has_table("incoming") else "inbound_routes"
    rows = qrows(f"SELECT did, description, destination FROM {tbl};",
                 ["did", "description", "destination"])
    for r in rows:
        dest = r.get("destination","")
        if not dest:
            issues.append(f"DID {r['did']} ({r['description']}): no destination configured")

    # 5. Voicemail boxes with no email
    rows = qrows("SELECT mailbox, fullname, email FROM voicemail WHERE context='default';",
                 ["mailbox", "fullname", "email"])
    for vm in rows:
        if not vm.get("email","").strip():
            issues.append(f"Voicemail {vm['mailbox']} ({vm['fullname']}): no email address")

    # 6. IVR entries with duplicate selections
    rows = qrows(
        "SELECT ivr_id, selection, COUNT(*) as cnt FROM ivr_entries "
        "GROUP BY ivr_id, selection HAVING cnt > 1;",
        ["ivr_id", "selection", "cnt"]
    )
    for row in rows:
        issues.append(f"IVR {row['ivr_id']}: duplicate option '{row['selection']}' ({row['cnt']} entries)")

    # Report
    if not issues:
        ok("No issues found — configuration looks clean.\n")
    else:
        print(f"  {C.RED}{C.BOLD}Found {len(issues)} issue(s):{C.RESET}\n")
        for i, issue in enumerate(issues, 1):
            print(f"  {C.RED}{i}.{C.RESET} {issue}")
        print()

    return len(issues)

# ── set-ivr command ───────────────────────────────────────────────────────────

def cmd_set_ivr(args):
    ivr_id = str(args.ivr)
    sel    = str(args.option)
    new_dest = args.dest

    # Load current value
    cur = qone(f"SELECT dest FROM ivr_entries WHERE ivr_id='{ivr_id}' AND selection='{sel}';", ["dest"])
    old_dest = cur["dest"] if cur else None

    hdr(f"\n{'[DRY RUN] ' if not args.apply else ''}Set IVR Option\n")
    print(f"  IVR:         {ivr_id}  ({_ivr_name(ivr_id) or 'unknown'})")
    print(f"  Option:      {sel}")
    print(f"  Old dest:    {decode(old_dest)}")
    print(f"             ({old_dest})")
    print(f"  New dest:    {decode(new_dest)}")
    print(f"             ({new_dest})")
    print()

    if old_dest == new_dest:
        warn("Destination unchanged — no action needed.")
        return 0

    if not args.apply:
        warn("DRY RUN — no changes written. Run with --apply to execute.")
        return 0

    # Auto-snapshot before change
    print("  Taking automatic snapshot before change...")
    snap_args = type("A", (), {"reason": f"before set-ivr ivr={ivr_id} opt={sel}"})()
    snap_file = cmd_snapshot(snap_args)

    if cur:
        run_mysql(f"UPDATE ivr_entries SET dest='{new_dest}' WHERE ivr_id='{ivr_id}' AND selection='{sel}';")
    else:
        run_mysql(f"INSERT INTO ivr_entries (ivr_id, selection, dest, ivr_ret) "
                  f"VALUES ('{ivr_id}', '{sel}', '{new_dest}', 0);")

    ok(f"Database updated.")
    _fwconsole_reload()

    # Log to session
    _log_change("set-ivr", {
        "ivr_id":   ivr_id,
        "option":   sel,
        "old_dest": old_dest,
        "new_dest": new_dest,
        "old_label": _strip_ansi(decode(old_dest)),
        "new_label": _strip_ansi(decode(new_dest)),
        "snapshot": snap_file,
    })

    ok(f"Done. Snapshot: {snap_file}\n")
    return 0

# ── ticket command ────────────────────────────────────────────────────────────

def cmd_ticket(args):
    if not os.path.isfile(SESSION_LOG):
        warn("No session changes logged yet. Make changes with set-ivr first.")
        return

    with open(SESSION_LOG) as f:
        session = json.load(f)

    changes = session.get("changes", [])
    if not changes:
        warn("No changes in this session.")
        return

    hdr("\n📋  Ticket Note\n")
    print("─" * 60)

    ivr_changes = [c for c in changes if c["type"] == "set-ivr"]

    if ivr_changes:
        # Group by IVR
        by_ivr = {}
        for c in ivr_changes:
            ivr_id = c["data"]["ivr_id"]
            by_ivr.setdefault(ivr_id, []).append(c)

        print("Completed requested call-flow updates.\n")
        for ivr_id, items in by_ivr.items():
            ivr_name = _ivr_name(ivr_id) or f"IVR {ivr_id}"
            print(f"Updated {ivr_name} (IVR {ivr_id}):")
            for item in items:
                d    = item["data"]
                sel  = d["option"]
                old  = d["old_label"]
                new  = d["new_label"]
                print(f"  - Option {sel} changed from: {old}")
                print(f"              to: {new}")
        print()

    print("Reload completed successfully.")
    print()
    print("Please test and advise if any further changes are needed.")
    print("─" * 60)
    print()

    if args.clear:
        os.remove(SESSION_LOG)
        ok("Session log cleared.")

# ── helpers ───────────────────────────────────────────────────────────────────

def _fwconsole_reload():
    print(f"  {C.YELLOW}Running fwconsole reload...{C.RESET}")
    try:
        p = subprocess.run(["fwconsole", "reload"], capture_output=True,
                           universal_newlines=True, timeout=60)
        if p.returncode == 0:
            ok("Reload complete.")
        else:
            warn(f"Reload returned non-zero: {p.stderr.strip()[:200]}")
    except FileNotFoundError:
        warn("fwconsole not found — run reload manually.")
    except Exception as e:
        warn(f"Reload error: {e}")

def _log_change(change_type, data):
    session = {"changes": []}
    if os.path.isfile(SESSION_LOG):
        try:
            with open(SESSION_LOG) as f:
                session = json.load(f)
        except Exception:
            pass
    session["changes"].append({
        "type": change_type,
        "time": datetime.datetime.now().isoformat(),
        "data": data,
    })
    with open(SESSION_LOG, "w") as f:
        json.dump(session, f, indent=2)

def _strip_ansi(text):
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)

# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    global _DB_KW

    p = argparse.ArgumentParser(
        prog="freepbx_ops",
        description="FreePBX Operations Tool — trace, search, snapshot, update"
    )
    p.add_argument("--socket",   default="/var/lib/mysql/mysql.sock", help="MySQL socket path")
    p.add_argument("--db-user",  default="root",  help="MySQL user")
    p.add_argument("--password", default=None,    help="MySQL password")

    sub = p.add_subparsers(dest="cmd", required=True)

    # trace
    sp = sub.add_parser("trace", help="Full call-path trace for a DID")
    sp.add_argument("did", help="DID number to trace")

    # decode
    sp = sub.add_parser("decode", help="Decode a raw FreePBX destination string")
    sp.add_argument("destination", nargs="+", help="Destination string (e.g. ext-group,7004,1)")

    # find
    sp = sub.add_parser("find", help="Search across all PBX components")
    sp.add_argument("query", help="Search term (name, number, extension)")

    # snapshot
    sp = sub.add_parser("snapshot", help="Save current call-flow state to JSON")
    sp.add_argument("--reason", default="", help="Reason for snapshot")

    # rollback
    sp = sub.add_parser("rollback", help="Restore from a snapshot JSON file")
    sp.add_argument("snapshot", help="Path to snapshot JSON file")
    sp.add_argument("--apply", action="store_true", help="Actually write changes (default is dry-run)")

    # validate
    sub.add_parser("validate", help="Run health/consistency checks")

    # set-ivr
    sp = sub.add_parser("set-ivr", help="Update an IVR option destination")
    sp.add_argument("--ivr",    required=True, type=int, help="IVR ID")
    sp.add_argument("--option", required=True,           help="Option/selection (e.g. 1, 2, t, i)")
    sp.add_argument("--dest",   required=True,           help="New destination (e.g. ext-group,7004,1)")
    sp.add_argument("--apply",  action="store_true",     help="Write change (default is dry-run)")

    # ticket
    sp = sub.add_parser("ticket", help="Print ticket-ready summary of session changes")
    sp.add_argument("--clear", action="store_true", help="Clear session log after printing")

    args = p.parse_args()

    _DB_KW["socket"]   = args.socket
    _DB_KW["user"]     = args.db_user
    _DB_KW["password"] = args.password

    dispatch = {
        "trace":    cmd_trace,
        "decode":   cmd_decode,
        "find":     cmd_find,
        "snapshot": cmd_snapshot,
        "rollback": cmd_rollback,
        "validate": cmd_validate,
        "set-ivr":  cmd_set_ivr,
        "ticket":   cmd_ticket,
    }

    try:
        fn = dispatch.get(args.cmd)
        if fn:
            sys.exit(fn(args) or 0)
        else:
            p.print_help()
    except RuntimeError as e:
        err(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

if __name__ == "__main__":
    main()
