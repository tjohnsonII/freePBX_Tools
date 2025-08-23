#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_dump.py
Normalize FreePBX call-flow data across schema differences and dump to JSON.
✓ Python 3.6 compatible (uses mysql CLI via subprocess; no external modules).
"""

import argparse, json, os, socket as pysocket, subprocess, sys, time

ASTERISK_DB = "asterisk"

# ---------------------------
# mysql helpers (3.6 friendly)
# ---------------------------

def run_mysql(sql, socket=None, user="root", password=None, db=ASTERISK_DB):
    """Run a SQL statement via mysql CLI and return stdout as text."""
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    cmd = ["mysql", "-BN"]
    if user:
        cmd += ["--user", str(user)]
    if socket:
        cmd += ["--socket", str(socket)]
    if db:
        cmd += [str(db)]
    cmd += ["-e", sql]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("mysql error:\n" + (p.stderr or "").strip())
    return p.stdout

def rows_as_dicts(sql, cols, **kw):
    """Run a SELECT that returns exactly len(cols) columns -> list[dict]."""
    out = run_mysql(sql, **kw).rstrip("\n")
    if not out:
        return []
    dicts = []
    for line in out.split("\n"):
        parts = line.split("\t")
        parts = (parts + [""] * len(cols))[:len(cols)]
        dicts.append(dict(zip(cols, parts)))
    return dicts

def get_tables(**kw):
    return set(run_mysql("SHOW TABLES;", **kw).split())

def get_columns(table, **kw):
    # DESCRIBE returns Field\tType\tNull\tKey\tDefault\tExtra
    lines = run_mysql(f"DESCRIBE `{table}`;", **kw).splitlines()
    return set([ln.split("\t",1)[0] for ln in lines if ln.strip()])

def has_table(t, **kw): return t in get_tables(**kw)
def first_table(options, **kw):
    tabs = get_tables(**kw)
    for t in options:
        if t in tabs:
            return t
    return None

# ---------------------------
# collectors (schema-aware)
# ---------------------------

def meta(**kw):
    host = pysocket.gethostname()
    try:
        mysql_ver = rows_as_dicts("SELECT VERSION();", ["ver"], **kw)[0]["ver"]
    except Exception:
        mysql_ver = ""
    fbpx = detect_freepbx_version(**kw)
    return {
        "hostname": host,
        "mysql_version": mysql_ver,
        "freepbx_version": fbpx,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
# Reliable FreePBX version detection
def detect_freepbx_version(**kw):
    # Try modules.framework version first
    if has_table("modules", **kw):
        rows = rows_as_dicts("SELECT version FROM modules WHERE modulename='framework';", ["version"], **kw)
        if rows and rows[0].get("version"):
            return rows[0]["version"]
    # Fallback: freepbx_settings
    if has_table("freepbx_settings", **kw):
        rows = rows_as_dicts("SELECT value FROM freepbx_settings WHERE keyword='version';", ["value"], **kw)
        if rows and rows[0].get("value"):
            return rows[0]["value"]
    # Defensive fallback: globals table (rare)
    if has_table("globals", **kw):
        rows = rows_as_dicts("SELECT value FROM globals WHERE variable='FREEPBX_VERSION';", ["value"], **kw)
        if rows and rows[0].get("value"):
            return rows[0]["value"]
    return ""

def inbound(**kw):
    # incoming: {did|extension}, {cidnum|cid}, destination, {description|routename}
    cols = get_columns("incoming", **kw)
    did_col   = "extension" if "extension" in cols else ("did" if "did" in cols else None)
    cid_col   = "cidnum" if "cidnum" in cols else ("cid" if "cid" in cols else None)
    label_col = "description" if "description" in cols else ("routename" if "routename" in cols else None)
    if not did_col or "destination" not in cols:
        return []
    select = [
        f"{did_col} AS did",
        (f"{cid_col} AS cid" if cid_col else "'' AS cid"),
        "destination",
        (f"COALESCE({label_col},'') AS label" if label_col else "'' AS label"),
    ]
    sql = "SELECT " + ", ".join(select) + " FROM incoming;"
    return rows_as_dicts(sql, ["did","cid","destination","label"], **kw)

def ringgroups(**kw):
    if not has_table("ringgroups", **kw): return []
    cols = get_columns("ringgroups", **kw)
    rt   = "grptime" if "grptime" in cols else ("ringtime" if "ringtime" in cols else "0")
    post = "postdest" if "postdest" in cols else "''"
    sql  = f"""SELECT grpnum, description, grplist, strategy,
                      {rt} AS ringtime, COALESCE({post},'') AS postdest
               FROM ringgroups;"""
    return rows_as_dicts(sql, ["grpnum","description","grplist","strategy","ringtime","postdest"], **kw)

def queues(**kw):
    if not (has_table("queues_config", **kw) and has_table("queues_details", **kw)):
        return []
    # Strategy + timeout
    details = rows_as_dicts("""
        SELECT id,
               MAX(CASE WHEN keyword='strategy' THEN data END) AS strategy,
               MAX(CASE WHEN keyword='timeout'  THEN data END) AS timeout
        FROM queues_details GROUP BY id;
    """, ["id","strategy","timeout"], **kw)
    strat = {d["id"]: {"strategy": d["strategy"] or "", "timeout": d["timeout"] or ""} for d in details}
    # Static members
    members = rows_as_dicts("""
        SELECT id,
               GROUP_CONCAT(TRIM(BOTH ',' FROM SUBSTRING_INDEX(SUBSTRING_INDEX(data,'@',1),'/',-1))
                            ORDER BY data SEPARATOR ',') AS members
        FROM queues_details
        WHERE keyword='member'
        GROUP BY id;
    """, ["id","members"], **kw)
    mem = {m["id"]: (m["members"] or "") for m in members}
    # High-level
    cols = get_columns("queues_config", **kw)
    namecol = "descr" if "descr" in cols else ("description" if "description" in cols else "name" if "name" in cols else "extension")
    qc = rows_as_dicts(f"SELECT extension, {namecol} FROM queues_config;", ["extension","name"], **kw)
    out = []
    for row in qc:
        qid = row["extension"]
        s = strat.get(qid, {"strategy":"", "timeout":""})
        out.append({
            "queue": qid,
            "queue_name": row["name"] or "",
            "strategy": s["strategy"],
            "timeout": s["timeout"],
            "members": mem.get(qid, "")
        })
    # Optional dynamic members
    if has_table("queue_members", **kw):
        dyn = rows_as_dicts(
            "SELECT queue_name, interface, IFNULL(penalty,'') FROM queue_members;",
            ["queue","interface","penalty"], **kw)
        out.append({"_dynamic_members": dyn})
    return out

def ivrs(**kw):
    if not has_table("ivr_details", **kw): return {"menus": [], "options": []}
    cols = get_columns("ivr_details", **kw)
    idcol = "ivr_id" if "ivr_id" in cols else ("id" if "id" in cols else None)
    ann   = "announcement" if "announcement" in cols else "NULL"
    if not idcol or "name" not in cols: return {"menus": [], "options": []}
    menus = rows_as_dicts(
        f"SELECT {idcol} AS ivr_id, name, {ann} AS announcement FROM ivr_details;",
        ["ivr_id","name","announcement"], **kw)
    options = []
    if has_table("ivr_entries", **kw):
        options = rows_as_dicts(
            "SELECT ivr_id, selection, dest FROM ivr_entries ORDER BY ivr_id, selection;",
            ["ivr_id","selection","dest"], **kw)
    return {"menus": menus, "options": options}

def timegroups(**kw):
    if not has_table("timegroups_details", **kw): return []
    cols = get_columns("timegroups_details", **kw)
    if {"id","timegroupid","time"}.issubset(cols):
        return rows_as_dicts(
            "SELECT id, timegroupid, time FROM timegroups_details ORDER BY id;",
            ["id","timegroupid","time"], **kw)
    # very old variants
    sel = [c for c in ["id","timegroupid","hour","minute","mday","mon","dow"] if c in cols]
    if not sel: return []
    return rows_as_dicts("SELECT " + ",".join(sel) + " FROM timegroups_details ORDER BY id;", sel, **kw)

def timeconditions(**kw):
    if not has_table("timeconditions", **kw): return []
    cols = get_columns("timeconditions", **kw)
    tg   = "timegroupid" if "timegroupid" in cols else ("time" if "time" in cols else "0")
    tcol = "destination_true" if "destination_true" in cols else ("truegoto" if "truegoto" in cols else "''")
    fcol = "destination_false" if "destination_false" in cols else ("falsegoto" if "falsegoto" in cols else "''")
    name = "displayname" if "displayname" in cols else ("name" if "name" in cols else "CONCAT('TC ',timeconditions_id)")
    sql  = f"""SELECT timeconditions_id, {name} AS displayname, {tg} AS timegroupid,
                      COALESCE({tcol},'') AS true_dest,
                      COALESCE({fcol},'') AS false_dest
               FROM timeconditions;"""
    return rows_as_dicts(sql, ["timeconditions_id","displayname","timegroupid","true_dest","false_dest"], **kw)

def announcements(**kw):
    tab = first_table(["announcement","announcements"], **kw)
    if not tab: return []
    cols = get_columns(tab, **kw)
    idcol = "announcement_id" if "announcement_id" in cols else ("id" if "id" in cols else None)
    desc  = "description" if "description" in cols else "NULL"
    post  = "post_dest" if "post_dest" in cols else ("return_dest" if "return_dest" in cols else "NULL")
    if not idcol: return []
    sql = f"SELECT {idcol} AS announcement_id, {desc} AS description, {post} AS post_dest FROM {tab};"
    return rows_as_dicts(sql, ["announcement_id","description","post_dest"], **kw)

def extensions(**kw):
    if not has_table("users", **kw): return []
    return rows_as_dicts("SELECT extension, name FROM users;", ["extension","name"], **kw)

def recordings(**kw):
    if not has_table("recordings", **kw): return []
    return rows_as_dicts("SELECT id, displayname, filename FROM recordings;",
                         ["id","displayname","filename"], **kw)

def trunks(**kw):
    if not has_table("trunks", **kw): return {"trunks": [], "trunk_dialpatterns": []}
    cols = get_columns("trunks", **kw)
    # choose common fields if present
    fields = ["trunkid","name","tech","outcid","outbound_cid","dialoutprefix","channelid","disabled",
              "keepcid","maxchans","continue_if_busy"]
    sel = []
    for c in fields:
        if c in cols:
            sel.append(c)
    if "trunkid" not in cols or "name" not in cols:
        base = rows_as_dicts("SELECT * FROM trunks;", list(cols)[:10], **kw)  # fallback
    else:
        # always include trunkid + name + tech (if present)
        proj = ["trunkid", "name"] + ([ "tech" ] if "tech" in cols else [])
        for c in sel:
            if c not in proj:
                proj.append(c)
        sql = "SELECT " + ", ".join(proj) + " FROM trunks;"
        base = rows_as_dicts(sql, proj, **kw)

    # trunk dial patterns (optional table)
    td = []
    if has_table("trunk_dialpatterns", **kw):
        c = get_columns("trunk_dialpatterns", **kw)
        pre  = "prepend_digits" if "prepend_digits" in c else ("prepend" if "prepend" in c else "''")
        pref = "match_pattern_prefix" if "match_pattern_prefix" in c else ("prefix" if "prefix" in c else "''")
        pas  = "match_pattern_pass" if "match_pattern_pass" in c else ("match_pattern" if "match_pattern" in c else "''")
        cid  = "match_cid" if "match_cid" in c else "''"
        sql = f"""SELECT trunkid, {pre} AS prepend, {pref} AS prefix, {pas} AS pattern, {cid} AS match_cid
                  FROM trunk_dialpatterns ORDER BY trunkid;"""
        td = rows_as_dicts(sql, ["trunkid","prepend","prefix","pattern","match_cid"], **kw)
    return {"trunks": base, "trunk_dialpatterns": td}

def outbound_routes(**kw):
    if not has_table("outbound_routes", **kw): 
        return {"routes": [], "patterns": [], "route_trunks": []}
    # routes
    rc = get_columns("outbound_routes", **kw)
    fields = ["route_id","name","outcid","outcid_mode","emergency_route","intrapbx","mohclass","time_group_id","password","enabled"]
    proj = [f for f in fields if f in rc]
    if "route_id" not in rc or "name" not in rc:
        routes = rows_as_dicts("SELECT * FROM outbound_routes;", list(rc)[:6], **kw)
    else:
        sql = "SELECT " + ", ".join(["route_id","name"] + [c for c in proj if c not in ("route_id","name")]) + " FROM outbound_routes;"
        routes = rows_as_dicts(sql, ["route_id","name"] + [c for c in proj if c not in ("route_id","name")], **kw)

    # patterns
    pats, pt_cols = [], set()
    if has_table("outbound_route_patterns", **kw):
        pc = get_columns("outbound_route_patterns", **kw)
        pre  = "prepend_digits" if "prepend_digits" in pc else ("prepend" if "prepend" in pc else "''")
        pref = "match_pattern_prefix" if "match_pattern_prefix" in pc else ("prefix" if "prefix" in pc else "''")
        pas  = "match_pattern_pass"   if "match_pattern_pass"   in pc else ("match_pattern" if "match_pattern" in pc else "''")
        cid  = "match_cid" if "match_cid" in pc else "''"
        sql  = f"""SELECT route_id, {pre} AS prepend, {pref} AS prefix, {pas} AS pattern, {cid} AS match_cid
                   FROM outbound_route_patterns ORDER BY route_id;"""
        pats = rows_as_dicts(sql, ["route_id","prepend","prefix","pattern","match_cid"], **kw)
        pt_cols = pc

    # route → trunk priorities
    rts = []
    if has_table("outbound_route_trunks", **kw):
        tc = get_columns("outbound_route_trunks", **kw)
        rid = "route_id"
        pr  = "trunkpriority" if "trunkpriority" in tc else ("seq" if "seq" in tc else "0")
        tid = "trunk_id" if "trunk_id" in tc else ("trunkid" if "trunkid" in tc else "0")
        sql = f"SELECT {rid} AS route_id, {pr} AS priority, {tid} AS trunkid FROM outbound_route_trunks;"
        rts = rows_as_dicts(sql, ["route_id","priority","trunkid"], **kw)
        # decorate with trunk names if we can
        if has_table("trunks", **kw):
            names = rows_as_dicts("SELECT trunkid, name FROM trunks;", ["trunkid","name"], **kw)
            name_by_id = {n["trunkid"]: n["name"] for n in names}
            for row in rts:
                row["trunk_name"] = name_by_id.get(row["trunkid"], "")

    return {"routes": routes, "patterns": pats, "route_trunks": rts}

# ---------------------------
# main
# ---------------------------

def main():
    ap = argparse.ArgumentParser(description="Dump normalized FreePBX data to JSON")
    ap.add_argument("--socket", help="MySQL socket path (e.g. /var/lib/mysql/mysql.sock)")
    ap.add_argument("--db-user", default="root")
    ap.add_argument("--db-pass", default=None)
    ap.add_argument("--out", default="/home/123net/callflows/freepbx_dump.json")
    args = ap.parse_args()

    kw = dict(socket=args.socket, user=args.db_user, password=args.db_pass, db=ASTERISK_DB)

    try:
        payload = {
            "meta":            meta(**kw),
            "inbound":         inbound(**kw),              # DIDs / Inbound Routes
            "ringgroups":      ringgroups(**kw),
            "queues":          queues(**kw),
            "ivrs":            ivrs(**kw),
            "timeconditions":  timeconditions(**kw),
            "timegroups":      timegroups(**kw),
            "announcements":   announcements(**kw),
            "extensions":      extensions(**kw),
            "recordings":      recordings(**kw),
            "trunks":          trunks(**kw),               # trunks + trunk_dialpatterns
            "outbound":        outbound_routes(**kw),      # routes + patterns + route→trunks
        }
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    print("Wrote", args.out)

if __name__ == "__main__":
    main()
