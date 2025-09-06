#!/usr/bin/env python3
# freepbx_callflow_graph.py
# Build a call-flow SVG for a DID, expanding Time Conditions, IVRs, Ring Groups, Queues, etc.
# No Python DB drivers needed: we shell out to the mysql CLI.

import argparse, subprocess, sys, re

DB = "asterisk"

# ---------- DB helper ---------------------------------------------------------

def q(sql, socket=None, user="root", password=None):
    """
    Execute a SQL query using the mysql CLI and return results as a list of tuples.
    """
    cmd = ["mysql", "-NBe", sql, DB, "-u", user]
    if password:
        cmd += ["-p" + password]
    if socket:
        cmd += ["--socket", socket]
    # py3.6-safe: use universal_newlines instead of text=True
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        return []
    out = p.stdout.strip()
    if not out:
        return []
    return [tuple(line.split("\t")) for line in out.splitlines()]

# ---------- Friendly labels / lookups ----------------------------------------

def human_time_rules(rows):
    """Convert FreePBX timegroup rules to a readable multiline string."""
    def pretty(rule):
        # FreePBX stores "HH:MM-HH:MM|mday|mon|dow"
        parts = rule.split("|")
        time = parts[0] if len(parts) > 0 else "*"
        mday = parts[1] if len(parts) > 1 else "*"
        mon  = parts[2] if len(parts) > 2 else "*"
        dow  = parts[3] if len(parts) > 3 else "*"

        def anyify(x): return "any" if (x.strip() == "*" or x.strip() == "") else x
        # 09:00-17:00 -> 09h00-17h00
        time = time.replace(":", "h", 1).replace(":", "m", 1)
        return f"{time} | day:{anyify(mday)} | mon:{anyify(mon)} | dow:{anyify(dow)}"

    rules = [pretty(r[1]) for r in rows]
    return "\n".join(rules) if rules else "no rules"

def fetch_users_map(socket, user, password):
    rows = q("SELECT extension,name FROM users;", socket, user, password)
    return {ext: name for (ext, name) in rows}

def fetch_ringgroup(grpnum, socket, user, password):
    sql = ("SELECT grpnum,description,grplist,strategy,grptime,COALESCE(postdest,'') "
           "FROM ringgroups WHERE grpnum='{g}'").format(g=grpnum)
    rg = q(sql, socket, user, password)
    return rg[0] if rg else None

def fetch_queue_details(queue_id, socket, user, password):
    """Return (name, strategy, timeout, members_csv)"""
    rows = q("""
        SELECT id,
               MAX(CASE WHEN keyword='strategy' THEN data END),
               MAX(CASE WHEN keyword='timeout'  THEN data END)
        FROM queues_details WHERE id='%s';""" % queue_id, socket, user, password)
    strategy, timeout = (rows[0][1], rows[0][2]) if rows else ("", "")

    mem = q("""
        SELECT GROUP_CONCAT(
                 TRIM(BOTH ',' FROM SUBSTRING_INDEX(SUBSTRING_INDEX(data,'@',1),'/',-1))
                 ORDER BY data SEPARATOR ',')
        FROM queues_details WHERE id='%s' AND keyword='member';""" % queue_id, socket, user, password)
    members = mem[0][0] if mem and mem[0][0] else ""

    qc = q("SELECT extension,descr FROM queues_config WHERE extension='%s'" % queue_id,
           socket, user, password)
    name = qc[0][1] if qc else ""
    return name, strategy, timeout, members

def fetch_ivr(ivr_id, socket, user, password):
    head = q("SELECT id,name,announcement FROM ivr_details WHERE id='%s'" % ivr_id,
             socket, user, password)
    if not head:
        return None, []
    name = head[0][1]
    entries = q("SELECT ivr_id, selection, dest FROM ivr_entries "
                "WHERE ivr_id='%s' ORDER BY selection" % ivr_id,
                socket, user, password)
    return name, [(sel, dest) for (_ivr, sel, dest) in entries]

def fetch_timecondition(tc_id, socket, user, password):
    rows = q(("SELECT timeconditions_id,displayname,`time`,"
              "COALESCE(truegoto,''),COALESCE(falsegoto,'') "
              "FROM timeconditions WHERE timeconditions_id='%s'") % tc_id,
             socket, user, password)
    if not rows:
        return None
    _id, display, tg_id, truegoto, falsegoto = rows[0]
    tg_rows = q("SELECT timegroupid, `time` FROM timegroups_details "
                "WHERE timegroupid='%s' ORDER BY id" % tg_id, socket, user, password)
    return {"display": display, "tg_id": tg_id,
            "rules": human_time_rules(tg_rows),
            "true": truegoto, "false": falsegoto}

def fetch_announcement(ann_id, socket, user, password):
    """Return (description, post_dest) or (None, None)"""
    rows = q(("SELECT description, COALESCE(post_dest,'') "
              "FROM announcement WHERE announcement_id='%s'") % ann_id,
             socket, user, password)
    if not rows:
        return None, None
    return rows[0][0], rows[0][1]

def fetch_system_recording(rec_id, socket, user, password):
    """Return display name of a system recording id, or None."""
    # FreePBX uses table `recordings` (id, displayname, ...) in recent versions.
    rows = q("SELECT displayname FROM recordings WHERE id='%s'" % rec_id,
             socket, user, password)
    if rows:
        return rows[0][0]
    # Some installs use `systemrecordings` (older schema)
    rows = q("SELECT displayname FROM systemrecordings WHERE id='%s'" % rec_id,
             socket, user, password)
    return rows[0][0] if rows else None

# ---------- Graph helper ------------------------------------------------------

class Graph:
    def __init__(self):
        self.lines = [
            'digraph G {',
            '  rankdir=LR;',
            '  node [shape=box, style="rounded,filled", fillcolor="#f7f7f7", fontname="Helvetica"];',
            '  edge [fontname="Helvetica"];'
        ]
        self.ids = 0
        self.node_ids = {}

    def new_id(self):
        self.ids += 1
        return f"n{self.ids}"

    def add_node(self, key, label):
        if key in self.node_ids:
            return self.node_ids[key]
        nid = self.new_id()
        safe = label.replace('"', r"\"")
        self.lines.append(f'  {nid} [label="{safe}"];')
        self.node_ids[key] = nid
        return nid

    def add_edge(self, a, b, label=None):
        if label:
            self.lines.append(f'  {a} -> {b} [label="{label}"];')
        else:
            self.lines.append(f'  {a} -> {b};')

    def render(self):
        self.lines.append('}')
        return "\n".join(self.lines)

# ---------- Resolver ----------------------------------------------------------

def parse_dest(dest):
    parts = dest.split(",")
    if not parts:
        return ("raw", dest, [])
    return (parts[0], parts[1:], dest)

def resolve_recursive(graph, key, dest, users_map, socket, user, password, depth=0, max_depth=25):
    if depth > max_depth:
        return graph.add_node(key, f"Max depth reached at {dest}")

    ctx, rest, raw = parse_dest(dest)

    def add_terminal(lbl):
        return graph.add_node(key, lbl)

    # Time Conditions
    if ctx == "timeconditions":
        tc_id = rest[0]
        info = fetch_timecondition(tc_id, socket, user, password)
        if not info:
            return add_terminal(f"Time Condition {tc_id} (not found)")
        lbl = f"Time Condition: {info['display']}\nTime Group {info['tg_id']}\n{info['rules']}"
        nid = graph.add_node(key, lbl)
        tchild = resolve_recursive(graph, f"{raw}#T", info["true"], users_map, socket, user, password, depth+1, max_depth)
        fchild = resolve_recursive(graph, f"{raw}#F", info["false"], users_map, socket, user, password, depth+1, max_depth)
        graph.add_edge(nid, tchild, "TRUE")
        graph.add_edge(nid, fchild, "FALSE")
        return nid

    # IVR
    elif ctx.startswith("ivr-"):
        ivr_id = ctx.split("-")[1]
        name, options = fetch_ivr(ivr_id, socket, user, password)
        if name is None:
            return add_terminal(f"IVR {ivr_id} (not found)")
        nid = graph.add_node(key, f"IVR {ivr_id}: {name}")
        for sel, d in options:
            child = resolve_recursive(graph, f"{raw}#{sel}", d, users_map, socket, user, password, depth+1, max_depth)
            graph.add_edge(nid, child, sel)
        return nid

    # Announcements (app-announcement-<id>,s,1)
    elif ctx.startswith("app-announcement-"):
        ann_id = ctx.split("-")[-1]
        desc, post = fetch_announcement(ann_id, socket, user, password)
        lbl = f"Announcement {ann_id}: {desc or '(no description)'}"
        nid = graph.add_node(key, lbl)
        if post:
            child = resolve_recursive(graph, f"{raw}#post", post, users_map, socket, user, password, depth+1, max_depth)
            graph.add_edge(nid, child, "after")
        return nid

    # Play System Recording (play-system-recording,<id>,1)
    elif ctx == "play-system-recording":
        rec_id = rest[0] if rest else ""
        name = fetch_system_recording(rec_id, socket, user, password) if rec_id else None
        return add_terminal(f"Play System Recording: {name or rec_id or '(unknown)'}")

    # Queues (ext-queues,<qid>,1)
    elif ctx == "ext-queues":
        qid = rest[0]
        name, strategy, timeout, members = fetch_queue_details(qid, socket, user, password)
        # Map queue member extensions to names where possible
        pretty_members = []
        for m in (members.split(",") if members else []):
            m = m.strip()
            if not m:
                continue
            if m.endswith("#"):   # external number
                pretty_members.append(m)
            else:
                pretty_members.append(f"{m} {users_map.get(m,'')}".strip())
        label = (f"Queue {qid}: {name or '[no name]'}\n"
                 f"strategy={strategy or '-'} timeout={timeout or '-'}\n"
                 f"members: {', '.join(pretty_members) if pretty_members else '-'}")
        return add_terminal(label)

    # Ring Group (ext-group,<grp>,1)
    elif ctx == "ext-group":
        grp = rest[0]
        rg = fetch_ringgroup(grp, socket, user, password)
        if not rg:
            return add_terminal(f"Ring Group {grp} (not found)")
        _grpnum, desc, grplist, strategy, grptime, postdest = rg
        members = []
        for token in (grplist or "").split("-"):
            token = token.strip()
            if not token:
                continue
            if token.endswith("#"):
                members.append(token)  # external number
            else:
                members.append(f"{token} {users_map.get(token, '')}".strip())
        label = (f"Ring Group {grp}: {desc}\n"
                 f"strategy={strategy} ring={grptime}s\n"
                 f"members: {', '.join(members) if members else '-'}")
        nid = graph.add_node(key, label)
        if postdest:
            child = resolve_recursive(graph, f"{raw}#post", postdest, users_map, socket, user, password, depth+1, max_depth)
            graph.add_edge(nid, child, "post")
        return nid

    # Direct to extension
    elif ctx == "from-did-direct":
        ext = rest[0]
        name = users_map.get(ext, "")
        return add_terminal(f"Extension {ext}{(' — ' + name) if name else ''}")

    # Voicemail
    elif ctx == "ext-local":
        target = rest[0] if rest else ""
        m = re.match(r"vm([ubsi])(\d+)", target)
        if m:
            code, ext = m.groups()
            suffix = {"u":"unavailable", "b":"busy", "s":"no message", "i":"immediate"}[code]
            name = users_map.get(ext, "")
            return add_terminal(f"Voicemail {ext}{(' — '+name) if name else ''} ({suffix})")

    # Directory
    elif ctx == "directory":
        return add_terminal("Directory")

    # Conference
    elif ctx == "ext-meetme":
        room = rest[0] if rest else ""
        return add_terminal(f"Conference {room}")

    # Blackhole / terminate
    elif ctx == "app-blackhole":
        return add_terminal("Terminate Call (blackhole)")

    # Fallback: show the raw target for unknown modules
    else:
        return add_terminal(raw)

# ---------- CLI ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Render FreePBX callflow for a DID to SVG (expands Time Conditions, IVR, Queues, Ring Groups, Announcements)")
    ap.add_argument("--did", required=True, help="DID to render (incoming.extension)")
    ap.add_argument("--out", required=True, help="Output SVG path")
    ap.add_argument("--db-user", default="root")
    ap.add_argument("--db-pass", default=None)
    ap.add_argument("--socket", default=None, help="MySQL socket path (e.g., /var/lib/mysql/mysql.sock)")
    args = ap.parse_args()

    # Find inbound route for this DID
    rows = q("SELECT extension, COALESCE(description,''), destination "
             "FROM incoming WHERE extension='%s';" % args.did,
             args.socket, args.db_user, args.db_pass)
    if not rows:
        sys.stderr.write("No inbound route for DID %s\n" % args.did)
        sys.exit(2)
    did, label, dest = rows[0]

    users_map = fetch_users_map(args.socket, args.db_user, args.db_pass)

    g = Graph()
    root = g.add_node(("root", did), f"DID: {did}\n{label or '(no label)'}")
    child = resolve_recursive(g, ("dest", dest), dest, users_map, args.socket, args.db_user, args.db_pass)
    g.add_edge(root, child)

    dot = g.render()
    # Render to SVG using dot (graphviz)
    p = subprocess.run(["dot", "-Tsvg", "-o", args.out], input=dot.encode("utf-8"))
    if p.returncode != 0:
        sys.stderr.write("graphviz dot failed\n")
        sys.exit(3)

if __name__ == "__main__":
    main()
