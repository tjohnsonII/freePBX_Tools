That JSON looks great — you’ve got all the key objects (inbound routes, IVRs, queues, ring groups, announcements, time conditions/groups, outbound routes/patterns, trunks, extensions, recordings). Two quick improvements I’d make:

fill in meta.freepbx_version reliably;

tighten the run_mysql() arg building (minor cleanup).

Here’s a drop-in update of freepbx_dump.py with those tweaks plus a couple of defensive queries (it keeps your current outputs/shape the same):


# freepbx_render_from_dump.sh
# Render FreePBX call flow SVGs from a JSON dump using the callflow graph tool.
#
# VARIABLE MAP (Key Script Variables)
# -----------------------------------
# JSON_FILE      : Path to FreePBX data JSON dump
# SVG_DIR        : Output directory for SVG files
# DID_LIST       : List of DIDs to render
# GRAPH_SCRIPT   : Path to callflow graph rendering script
#
# FUNCTION MAP (Major Script Sections)
# ------------------------------------
# (main script body) : Loops through DIDs, calls rendering tool, prints results
#

import argparse, json, os, subprocess, sys, datetime, socket as pysocket

ASTERISK_DB = "asterisk"

def run_mysql(sql, socket=None, user="root", password=None, db=ASTERISK_DB):
    """
    Run a SQL statement via mysql CLI and return stdout as text.
    Uses --batch/-B and -N (no headers) for easy parsing (tab-separated).
    """
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    cmd = ["mysql"]
    if user:
        cmd += ["--user", user]
    if socket:
        cmd += ["--socket", socket]
    if db:
        cmd += [db]
    cmd += ["-BN", "-e", sql]
    # Python 3.6: use universal_newlines, not text=
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("mysql error:\n" + p.stderr.strip())
    return p.stdout

def rows_as_dicts(sql, cols, **kw):
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
    return set(x.strip() for x in run_mysql("SHOW TABLES;", **kw).splitlines() if x.strip())

def get_columns(table, **kw):
    out = run_mysql(f"DESCRIBE `{table}`;", **kw)
    cols = []
    for line in out.splitlines():
        if not line.strip():
            continue
        cols.append(line.split("\t", 1)[0])
    return set(cols)

def has_table(t, **kw): return t in get_tables(**kw)

def first_table(options, **kw):
    tabs = get_tables(**kw)
    for t in options:
        if t in tabs:
            return t
    return None

# ------------ collectors ------------

def inbound(**kw):
    cols = get_columns("incoming", **kw)
    did_col = "extension" if "extension" in cols else ("did" if "did" in cols else None)
    cid_col = "cidnum" if "cidnum" in cols else ("cid" if "cid" in cols else None)
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
    if not has_table("ringgroups", **kw):
        return []
    cols = get_columns("ringgroups", **kw)
    rt = "grptime" if "grptime" in cols else ("ringtime" if "ringtime" in cols else "0")
    post = "postdest" if "postdest" in cols else "''"
    sql = f"""SELECT grpnum, description, grplist, strategy,
                     {rt} AS ringtime, COALESCE({post},'') AS postdest
              FROM ringgroups;"""
    return rows_as_dicts(sql, ["grpnum","description","grplist","strategy","ringtime","postdest"], **kw)

def queues(**kw):
    if not (has_table("queues_config", **kw) and has_table("queues_details", **kw)):
        return []
    details = rows_as_dicts("""
        SELECT id,
               MAX(CASE WHEN keyword='strategy' THEN data END) AS strategy,
               MAX(CASE WHEN keyword='timeout'  THEN data END) AS timeout
        FROM queues_details GROUP BY id;
    """, ["id","strategy","timeout"], **kw)
    strategy = {d["id"]: {"strategy": d["strategy"] or "", "timeout": d["timeout"] or ""} for d in details}
    members = rows_as_dicts("""
        SELECT id,
               GROUP_CONCAT(TRIM(BOTH ',' FROM SUBSTRING_INDEX(SUBSTRING_INDEX(data,'@',1),'/',-1))
                            ORDER BY data SEPARATOR ',') AS members
        FROM queues_details
        WHERE keyword='member'
        GROUP BY id;
    """, ["id","members"], **kw)
    mem = {m["id"]: (m["members"] or "") for m in members}
    qc = rows_as_dicts("SELECT extension, descr FROM queues_config;", ["extension","descr"], **kw)
    out = []
    for row in qc:
        qid = row["extension"]
        s = strategy.get(qid, {"strategy":"", "timeout":""})
        out.append({
            "queue": qid,
            "queue_name": row["descr"] or "",
            "strategy": s["strategy"],
            "timeout": s["timeout"],
            "members": mem.get(qid, "")
        })
    if has_table("queue_members", **kw):
        dyn = rows_as_dicts(
            "SELECT queue_name, interface, IFNULL(penalty,'') FROM queue_members;",
            ["queue","interface","penalty"], **kw)
        out.append({"_dynamic_members": dyn})
    return out

def ivrs(**kw):
    if not has_table("ivr_details", **kw):
        return []
    cols = get_columns("ivr_details", **kw)
    ivr_id = "ivr_id" if "ivr_id" in cols else ("id" if "id" in cols else None)
    if not ivr_id or "name" not in cols:
        return []
    ann = "announcement" if "announcement" in cols else "NULL"
    ivr = rows_as_dicts(f"SELECT {ivr_id} AS ivr_id, name, {ann} AS announcement FROM ivr_details;",
                        ["ivr_id","name","announcement"], **kw)
    entries = []
    if has_table("ivr_entries", **kw):
        entries = rows_as_dicts(
            "SELECT ivr_id, selection, dest FROM ivr_entries ORDER BY ivr_id, selection;",
            ["ivr_id","selection","dest"], **kw)
    return {"menus": ivr, "options": entries}

def timegroups(**kw):
    if not has_table("timegroups_details", **kw):
        return []
    cols = get_columns("timegroups_details", **kw)
    if {"id","timegroupid","time"}.issubset(cols):
        return rows_as_dicts(
            "SELECT id, timegroupid, time FROM timegroups_details ORDER BY id;",
            ["id","timegroupid","time"], **kw)
    sel_cols = [c for c in ["id","timegroupid","hour","minute","mday","mon","dow"] if c in cols]
    if not sel_cols:
        return []
    sql = "SELECT " + ",".join(sel_cols) + " FROM timegroups_details ORDER BY id;"
    return rows_as_dicts(sql, sel_cols, **kw)

def timeconditions(**kw):
    if not has_table("timeconditions", **kw):
        return []
    cols = get_columns("timeconditions", **kw)
    tg = "timegroupid" if "timegroupid" in cols else ("time" if "time" in cols else "0")
    tcol = "destination_true" if "destination_true" in cols else ("truegoto" if "truegoto" in cols else "''")
    fcol = "destination_false" if "destination_false" in cols else ("falsegoto" if "falsegoto" in cols else "''")
    name = "displayname" if "displayname" in cols else ("name" if "name" in cols else "concat('TC ',timeconditions_id)")
    sql = f"""SELECT timeconditions_id, {name} AS displayname, {tg} AS timegroupid,
                     COALESCE({tcol},'') AS true_dest,
                     COALESCE({fcol},'') AS false_dest
              FROM timeconditions;"""
    return rows_as_dicts(sql, ["timeconditions_id","displayname","timegroupid","true_dest","false_dest"], **kw)

def announcements(**kw):
    tab = first_table(["announcement","announcements"], **kw)
    if not tab:
        return []
    cols = get_columns(tab, **kw)
    idcol = "announcement_id" if "announcement_id" in cols else ("id" if "id" in cols else None)
    desc = "description" if "description" in cols else "NULL"
    ret = "post_dest" if "post_dest" in cols else ("return_dest" if "return_dest" in cols else "NULL")
    if not idcol:
        return []
    sql = f"SELECT {idcol} AS announcement_id, {desc} AS description, {ret} AS post_dest FROM {tab};"
    return rows_as_dicts(sql, ["announcement_id","description","post_dest"], **kw)

def extensions(**kw):
    if not has_table("users", **kw):
        return []
    return rows_as_dicts("SELECT extension, name FROM users;", ["extension","name"], **kw)

def recordings(**kw):
    if not has_table("recordings", **kw):
        return []
    return rows_as_dicts("SELECT id, displayname, filename FROM recordings;",
                         ["id","displayname","filename"], **kw)

def trunks(**kw):
    out = {"trunks": [], "trunk_dialpatterns": []}
    if has_table("trunks", **kw):
        out["trunks"] = rows_as_dicts("""
            SELECT trunkid, name, tech, channelid, outcid, dialoutprefix,
                   keepcid, maxchans, disabled
            FROM trunks;
        """, ["trunkid","name","tech","channelid","outcid","dialoutprefix",
              "keepcid","maxchans","disabled"], **kw)
    # Try both possible pattern tables
    tdp = None
    for tab in ["trunk_dialpatterns", "trunks_dialpatterns"]:
        if has_table(tab, **kw):
            tdp = tab; break
    if tdp:
        out["trunk_dialpatterns"] = rows_as_dicts(f"""
            SELECT trunkid, match_cid, prepend, prefix, pattern
            FROM {tdp};
        """, ["trunkid","match_cid","prepend","prefix","pattern"], **kw)
    return out

def outbound(**kw):
    out = {"routes": [], "patterns": [], "route_trunks": []}
    if has_table("outbound_routes", **kw):
        # freepbx14+: time_group_id exists; older boxes may not have it -> NULL
        cols = get_columns("outbound_routes", **kw)
        tgid = "time_group_id" if "time_group_id" in cols else "NULL"
        out["routes"] = rows_as_dicts(f"""
            SELECT route_id, name, mohclass, password, outcid, outcid_mode,
                   IFNULL(emergency_route,'') AS emergency_route,
                   {tgid} AS time_group_id
            FROM outbound_routes;
        """, ["route_id","name","mohclass","password","outcid","outcid_mode","emergency_route","time_group_id"], **kw)
    # patterns
    pat_tab = first_table(["outbound_route_patterns","outbound_route_sequence"], **kw)
    if pat_tab == "outbound_route_patterns":
        out["patterns"] = rows_as_dicts("""
            SELECT route_id, match_cid, prepend, prefix, match_pattern_pass AS pattern
            FROM outbound_route_patterns;
        """, ["route_id","match_cid","prepend","prefix","pattern"], **kw)
    elif pat_tab == "outbound_route_sequence":
        # very old
        out["patterns"] = rows_as_dicts("""
            SELECT route_id, match_cid, prepend, prefix, match_pattern AS pattern
            FROM outbound_route_sequence;
        """, ["route_id","match_cid","prepend","prefix","pattern"], **kw)
    # route -> trunks mapping
    if has_table("outbound_route_trunks", **kw):
        # try to denormalize trunkid->name for convenience when possible
        maprows = rows_as_dicts("""
            SELECT ort.route_id, ort.seq AS priority, t.trunkid, t.name AS trunk_name
            FROM outbound_route_trunks ort
            LEFT JOIN trunks t ON t.trunkid=ort.trunk_id OR t.trunkid=ort.trunkid;
        """, ["route_id","priority","trunkid","trunk_name"], **kw)
        out["route_trunks"] = maprows
    return out

def detect_freepbx_version(**kw):
    # Best effort: modules.framework version; fallbacks try freepbx_settings/version
    try_order = []
    if has_table("modules", **kw):
        try_order.append(("SELECT version FROM modules WHERE modulename='framework';", "version"))
    if has_table("freepbx_settings", **kw):
        try_order.append(("SELECT value FROM freepbx_settings WHERE keyword='version';", "value"))
    for sql, col in try_order:
        rows = rows_as_dicts(sql, [col], **kw)
        if rows and rows[0].get(col):
            return rows[0][col]
    return ""

# ------------ main ------------

def main():
    ap = argparse.ArgumentParser(description="Dump normalized FreePBX call-flow data to JSON")
    ap.add_argument("--socket", help="MySQL socket path (e.g. /var/lib/mysql/mysql.sock)")
    ap.add_argument("--db-user", default="root")
    ap.add_argument("--db-pass", default=None)
    ap.add_argument("--out", default="/home/123net/callflows/freepbx_dump.json")
    args = ap.parse_args()

    kw = dict(socket=args.socket, user=args.db_user, password=args.db_pass, db=ASTERISK_DB)

    try:
        payload = {
            "inbound": inbound(**kw),
            "ringgroups": ringgroups(**kw),
            "queues": queues(**kw),
            "ivrs": ivrs(**kw),
            "timeconditions": timeconditions(**kw),
            "timegroups": timegroups(**kw),
            "announcements": announcements(**kw),
            "extensions": extensions(**kw),
            "recordings": recordings(**kw),
            "trunks": trunks(**kw),
            "outbound": outbound(**kw),
            "meta": {
                "hostname": pysocket.gethostname(),
                "mysql_version": run_mysql("SELECT @@version;", **kw).strip(),
                "freepbx_version": detect_freepbx_version(**kw),
                "generated_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            },
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

Regenerate
SOCK=$(mysql -NBe 'SHOW VARIABLES LIKE "socket";' 2>/dev/null | awk '{print $2}')
: "${SOCK:=/var/lib/mysql/mysql.sock}"

python3 /usr/local/bin/freepbx_dump.py \
  --socket "$SOCK" --db-user root \
  --out /home/123net/callflows/freepbx_dump.json