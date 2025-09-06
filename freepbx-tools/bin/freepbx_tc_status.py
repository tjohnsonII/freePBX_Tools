#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_tc_status.py
Report Time Condition override state + last feature-code (*<id>) use from CDRs.
- Python 3.6 friendly (uses mysql CLI via subprocess)
- No external modules needed
"""

import argparse, subprocess, os, sys, re
from datetime import datetime

ASTERISK_DB     = "asterisk"
CDR_DB          = "asteriskcdrdb"   # FreePBX default
MYSQL_BIN       = "mysql"
ASTERISK_CLI    = "/usr/sbin/asterisk"

def run_mysql(sql, db, user="root", password=None, socket=None):
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    cmd = [MYSQL_BIN]
    if user:   cmd += ["--user", str(user)]
    if socket: cmd += ["--socket", str(socket)]
    if db:     cmd += [str(db)]
    cmd += ["-BN", "-e", sql]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("mysql error ({}):\n{}".format(db, p.stderr.strip()))
    return p.stdout

def timeconditions_list(mysql_kw):
    # Pull essentials + whether it links to a Calendar or Time Group
    cols = run_mysql("DESCRIBE timeconditions;", ASL_DB, **mysql_kw).splitlines()
    cols = [c.split("\t",1)[0] for c in cols if c.strip()]
    tg_col   = "timegroupid" if "timegroupid" in cols else ("time" if "time" in cols else None)
    name_col = "displayname" if "displayname" in cols else ("name" if "name" in cols else None)
    # calendar linkage (recent FreePBX): calendar_id column in timeconditions or tc_calendar table
    has_tc_calendar = False
    try:
        _ = run_mysql("DESCRIBE tc_calendar;", ASL_DB, **mysql_kw)
        has_tc_calendar = True
    except Exception:
        pass

    fields = ["timeconditions_id AS id"]
    fields.append((name_col + " AS name") if name_col else "CONCAT('TC ',timeconditions_id) AS name")
    fields.append((tg_col + " AS timegroupid") if tg_col else "NULL AS timegroupid")
    fields.append("COALESCE(destination_true,'') AS true_dest")   # present on newer
    fields.append("COALESCE(destination_false,'') AS false_dest") # present on newer
    sql = "SELECT {} FROM timeconditions ORDER BY timeconditions_id;".format(", ".join(fields))
    rows = run_mysql(sql, ASL_DB, **mysql_kw).strip().splitlines()
    out = []
    for ln in rows:
        parts = ln.split("\t")
        row = {
            "id": parts[0],
            "name": parts[1],
            "timegroupid": parts[2] if len(parts) > 2 else "",
            "true_dest": parts[3] if len(parts) > 3 else "",
            "false_dest": parts[4] if len(parts) > 4 else "",
            "mode": "Time Group"
        }
        # Check calendar linkage if table exists
        if has_tc_calendar:
            cal = run_mysql("SELECT calendar_id FROM tc_calendar WHERE timeconditions_id='{}' LIMIT 1;"
                            .format(row["id"]), ASL_DB, **mysql_kw).strip()
            if cal:
                row["mode"] = "Calendar"
        out.append(row)
    return out

def parse_astdb_states():
    """
    Read Asterisk AstDB for TC override flags.
    Different FreePBX versions use slightly different families; try several.
    We’ll return dict: { <id>: 'MATCHED'|'UNMATCHED' } (meaning forced state)
    """
    if not os.path.exists(ASTERISK_CLI):
        return {}
    # Collect database listings
    patterns = ["TC/", "TIMECONDITION/", "TIMECOND/"]
    states = {}
    for pat in patterns:
        try:
            out = subprocess.check_output([ASTERISK_CLI, "-rx", "database show {}".format(pat)],
                                          universal_newlines=True, stderr=subprocess.DEVNULL)
        except Exception:
            continue
        for line in out.splitlines():
            # Example lines:
            #  /TC/273                                   : UNMATCHED
            #  /TIMECONDITION/273/state                  : MATCHED
            m = re.search(r"/(TC|TIMECONDITION|TIMECOND)/(\d+)(?:/state)?\s*:\s*(MATCHED|UNMATCHED)", line, re.I)
            if m:
                tc_id = m.group(2)
                val   = m.group(3).upper()
                states[tc_id] = val
    return states

def last_feature_code_use(tc_id, mysql_kw_cdr):
    """
    Find the latest CDR where dst='*<id>' (feature code dial).
    Returns (when_iso, src, disposition, duration) or ("", "", "", "")
    """
    fc = "*{}".format(tc_id)
    sql = ("SELECT calldate, src, disposition, duration "
           "FROM cdr WHERE dst='{}' ORDER BY calldate DESC LIMIT 1;").format(fc)
    out = run_mysql(sql, CDR_DB, **mysql_kw_cdr).strip()
    if not out:
        return ("", "", "", "")
    parts = out.split("\t")
    # Normalize to ISO-ish for display
    when = parts[0].replace(" ", "T")
    return (when, parts[1], parts[2], parts[3])

def pad(s, n):
    s = str(s)
    return (s + " " * n)[:n]

def main():
    ap = argparse.ArgumentParser(
        description="Show Time Condition override state and last feature-code (*<id>) use from CDRs")
    ap.add_argument("--socket", help="MySQL socket (e.g. /var/lib/mysql/mysql.sock)")
    ap.add_argument("--db-user", default="root")
    ap.add_argument("--db-pass", default=None)
    ap.add_argument("--csv", action="store_true", help="Output CSV instead of pretty table")
    args = ap.parse_args()

    mysql_kw_core = dict(user=args.db_user, password=args.db_pass, socket=args.socket)
    mysql_kw_cdr  = dict(user=args.db_user, password=args.db_pass, socket=args.socket)

    # Some installs put CDR in same server but different DB name (default handled by const CDR_DB)
    global ASL_DB
    ASL_DB = ASTERISK_DB

    try:
        tcs = timeconditions_list(mysql_kw_core)
    except Exception as e:
        print("ERROR reading timeconditions:", e, file=sys.stderr)
        sys.exit(1)

    states = parse_astdb_states()

    rows = []
    for tc in tcs:
        tc_id = tc["id"]
        override = states.get(tc_id, "No Override")
        when, src, disp, dur = ("", "", "", "")
        # Only check CDR if we can reach CDR DB
        try:
            when, src, disp, dur = last_feature_code_use(tc_id, mysql_kw_cdr)
        except Exception:
            pass
        rows.append({
            "id": tc_id,
            "name": tc["name"],
            "mode": tc["mode"],
            "feature": "*" + tc_id,
            "override": override,
            "last_fc": when,
            "caller": src,
            "dispo": disp,
            "secs": dur
        })

    if args.csv:
        print("id,name,mode,feature,override,last_feature_code,caller,disposition,duration_s")
        for r in rows:
            print(",".join('"%s"' % (r[k].replace('"','""')) for k in
                           ["id","name","mode","feature","override","last_fc","caller","dispo","secs"]))
        return

    # pretty table
    headers = ["ID","Name","Mode","Feature","Override","Last *Code","Caller","Dispo","Sec"]
    widths  = [6, 34, 10, 8, 18, 20, 14, 8, 4]
    print("".join(pad(h, w) for h, w in zip(headers, widths)))
    print("-" * sum(widths))
    for r in rows:
        line = [
            pad(r["id"], widths[0]),
            pad(r["name"], widths[1]),
            pad(r["mode"], widths[2]),
            pad(r["feature"], widths[3]),
            pad(r["override"], widths[4]),
            pad(r["last_fc"], widths[5]),
            pad(r["caller"], widths[6]),
            pad(r["dispo"], widths[7]),
            pad(r["secs"], widths[8]),
        ]
        print("".join(line))

if __name__ == "__main__":
    main()
