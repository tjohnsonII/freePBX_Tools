#!/usr/bin/env python3
# freepbx_callflow_graph.py
# Build a call-flow SVG for a DID, expanding Time Conditions, IVRs, Ring Groups, Queues, etc.
# No Python DB drivers needed: we shell out to the mysql CLI.

import argparse, subprocess, shlex, sys, re, textwrap

DB = "asterisk"

def q(sql, socket=None, user="root", password=None):
    """Return rows from mysql -NBe as list of tuples of strings."""
    cmd = ["mysql", "-NBe", sql, DB, "-u", user]
    if password: cmd += ["-p"+password]
    if socket:   cmd += ["--socket", socket]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        return []
    out = p.stdout.strip()
    if not out:
        return []
    rows = []
    for line in out.splitlines():
        rows.append(tuple(line.split("\t")))
    return rows

def human_time_rules(rows):
    """rows: [(timegroupid, time_string), ...]; return pretty multiline string."""
    def pretty(rule):
        # FreePBX stores "HH:MM-HH:MM|mday|mon|dow"
        parts = rule.split("|")
        # be defensive if format varies
        time    = parts[0] if len(parts)>0 else "*"
        mday    = parts[1] if len(parts)>1 else "*"
        mon     = parts[2] if len(parts)>2 else "*"
        dow     = parts[3] if len(parts)>3 else "*"
        def star2any(x): return "any" if (x.strip()=="*" or x.strip()=="") else x
        time = time.replace(":", "h", 1).replace(":", "m", 1).replace("h","h",1)  # keep as given
        return f"{time} | day:{star2any(mday)} | mon:{star2any(mon)} | dow:{star2any(dow)}"
    rules = [pretty(r[1]) for r in rows]
    return "\\n".join(rules) if rules else "no rules"

def fetch_users_map(socket, user, password):
    rows = q("SELECT extension,name FROM users;", socket, user, password)
    return {ext:name for (ext,name) in rows}

def fetch_ringgroup(grpnum, socket, user, password):
    rg = q(f"SELECT grpnum,description,grplist,strategy,grptime,COALESCE(postdest,'') FROM ringgroups WHERE grpnum='{grpnum}'",
           socket, user, password)
    return rg[0] if rg else None

def fetch_queue_details(queue_id, socket, user, password):
    rows = q(f"""
        SELECT id,
               MAX(CASE WHEN keyword='strategy' THEN data END),
               MAX(CASE WHEN keyword='timeout'  THEN data END)
        FROM queues_details WHERE id='{queue_id}';""", socket, user, password)
    strategy, timeout = (rows[0][1], rows[0][2]) if rows else ("","")
    mem = q(f"""
        SELECT GROUP_CONCAT(
                 TRIM(BOTH ',' FROM SUBSTRING_INDEX(SUBSTRING_INDEX(data,'@',1),'/',-1))
                 ORDER BY data SEPARATOR ',')
        FROM queues_details WHERE id='{queue_id}' AND keyword='member';""", socket, user, password)
    members = mem[0][0] if mem and mem[0][0] else ""
    qc = q(f"SELECT extension,descr FROM queues_config WHERE extension='{queue_id}'", socket, user, password)
    name = qc[0][1] if qc else ""
    return name, strategy, timeout, members

def fetch_ivr(ivr_id, socket, user, password):
    head = q(f"SELECT id,name,announcement FROM ivr_details WHERE id='{ivr_id}'", socket, user, password)
    if not head: return None, []
    name = head[0][1]
    entries = q(f"SELECT ivr_id, selection, dest FROM ivr_entries WHERE ivr_id='{ivr_id}' ORDER BY selection",
                socket, user, password)
    return name, [(sel, dest) for (_ivr, sel, dest) in entries]

def fetch_timecondition(tc_id, socket, user, password):
    rows = q(f"SELECT timeconditions_id,displayname,`time`,COALESCE(truegoto,''),COALESCE(falsegoto,'') "
             f"FROM timeconditions WHERE timeconditions_id='{tc_id}'",
             socket, user, password)
    if not rows: return None
    _id, display, tg_id, truegoto, falsegoto = rows[0]
    # timegroups_details rows for this timegroupid
    tg_rows = q(f"SELECT timegroupid, `time` FROM timegroups_details WHERE timegroupid='{tg_id}' ORDER BY id",
                socket, user, password)
    rules = human_time_rules(tg_rows)
    return {"display":display, "tg_id":tg_id, "rules":rules,
            "true":truegoto, "false":falsegoto}

def parse_dest(dest):
    # Examples: "timeconditions,12,1", "ext-group,3004,1", "ivr-3,s,1",
    #           "from-did-direct,312,1", "ext-local,vmu312,1", "directory,1,1"
    parts = dest.split(",")
    if not parts: return ("raw", dest, [])
    ctx = parts[0]
    return (ctx, parts[1:] , dest)

# ----- Graph builder ---------------------------------------------------------

class Graph:
    def __init__(self):
        self.lines = [
            'digraph G {',
            '  rankdir=LR;',
            '  node [shape=box, style="rounded,filled", fillcolor="#f7f7f7", fontname="Helvetica"];',
            '  edge [fontname="Helvetica"];'
        ]
        self.ids = 0
        self.node_ids = {}   # key -> node_id
        self.visited = set()

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

def resolve_recursive(graph, key, dest, users_map, socket, user, password, depth=0, max_depth=25):
    if depth > max_depth:
        return graph.add_node(key, f"Max depth reached at {dest}")

    ctx, rest, raw = parse_dest(dest)

    # Simple terminal labels for common destinations
    def add_terminal(lbl):
        return graph.add_node(key, lbl)

    if ctx == "timeconditions":
        tc_id = rest[0]
        info = fetch_timecondition(tc_id, socket, user, password)
        if not info:
            return add_terminal(f"Time Condition {tc_id} (not found)")
        lbl = f"Time Condition: {info['display']}\\nTime Group {info['tg_id']}\\n{info['rules']}"
        nid = graph.add_node(key, lbl)

        # TRUE branch
        tkey = f"{raw}#T"
        tchild = resolve_recursive(graph, tkey, info["true"], users_map, socket, user, password, depth+1, max_depth)
        graph.add_edge(nid, tchild, "TRUE")

        # FALSE branch
        fkey = f"{raw}#F"
        fchild = resolve_recursive(graph, fkey, info["false"], users_map, socket, user, password, depth+1, max_depth)
        graph.add_edge(nid, fchild, "FALSE")
        return nid

    elif ctx == "ivr-2" or ctx == "ivr-3" or ctx.startswith("ivr-"):
        ivr_id = ctx.split("-")[1]
        name, options = fetch_ivr(ivr_id, socket, user, password)
        if name is None:
            return add_terminal(f"IVR {ivr_id} (not found)")
        nid = graph.add_node(key, f"IVR {ivr_id}: {name}")
        for sel, d in options:
            child = resolve_recursive(graph, f"{raw}#{sel}", d, users_map, socket, user, password, depth+1, max_depth)
            graph.add_edge(nid, child, sel)
        return nid

    elif ctx == "ext-group":
        grp = rest[0]
        rg = fetch_ringgroup(grp, socket, user, password)
        if not rg:
            return add_terminal(f"Ring Group {grp} (not found)")
        _grpnum, desc, grplist, strategy, grptime, postdest = rg
        members = []
        for token in (grplist or "").split("-"):
            token = token.strip()
            if token.endswith("#"):
                members.append(token)  # external number
            else:
                members.append(f"{token} {users_map.get(token,'')}".strip())
        label = f"Ring Group {grp}: {desc}\\nstrategy={strategy} ring={grptime}s\\n" \
                f"members: {', '.join(members) if members else '-'}"
        nid = graph.add_node(key, label)
        if postdest:
            child = resolve_recursive(graph, f"{raw}#post", postdest, users_map, socket, user, password, depth+1, max_depth)
            graph.add_edge(nid, child, "post")
        return nid

    elif ctx == "from-did-direct":
        ext = rest[0]
        name = users_map.get(ext, "")
        return add_terminal(f"Extension {ext}{(' — '+name) if name else ''}")

    elif ctx == "ext-local":
        # voicemail patterns: vmu<ext> (unavail), vms<mailbox> (busy), vmi<ext> (immediate)
        target = rest[0]
        m = re.match(r"(vm[usi])(\d+)", target)
        if m:
            vmtype, ext = m.groups()
            suffix = {"vmu":"unavailable", "vms":"busy", "vmi":"immediate"}.get(vmtype, vmtype)
            name = users_map.get(ext, "")
            return add_terminal(f"Voicemail {ext}{(' — '+name) if name else ''} ({suffix})")
        return add_terminal(f"ext-local → {target}")

    elif ctx == "directory":
        return add_terminal("Directory")

    elif ctx == "ext-meetme":
        room = rest[0]
        return add_terminal(f"Conference {room}")

    elif ctx == "app-blackhole":
        return add_terminal("Terminate Call (blackhole)")

    else:
        # unknown/rare module: just display raw
        return add_terminal(f"{raw}")

def main():
    ap = argparse.ArgumentParser(description="Render FreePBX callflow for a DID to SVG (expands Time Conditions)")
    ap.add_argument("--did", required=True, help="DID to render (incoming.extension)")
    ap.add_argument("--out", required=True, help="Output SVG path")
    ap.add_argument("--db-user", default="root")
    ap.add_argument("--db-pass", default=None)
    ap.add_argument("--socket", default=None, help="MySQL socket path (e.g., /var/lib/mysql/mysql.sock)")
    args = ap.parse_args()

    # Find inbound route for this DID
    rows = q(f"SELECT extension, COALESCE(description,''), destination FROM incoming WHERE extension='{args.did}';",
             args.socket, args.db_user, args.db_pass)
    if not rows:
        sys.stderr.write(f"No inbound route for DID {args.did}\n")
        sys.exit(2)
    did, label, dest = rows[0]

    users_map = fetch_users_map(args.socket, args.db_user, args.db_pass)

    g = Graph()
    root = g.add_node(("root", did), f"DID: {did}\\n{label or '(no label)'}")
    child = resolve_recursive(g, ("dest", dest), dest, users_map, args.socket, args.db_user, args.db_pass)
    g.add_edge(root, child)

    dot = g.render()
    # Render to SVG using dot
    p = subprocess.run(["dot", "-Tsvg", "-o", args.out], input=dot.encode("utf-8"))
    if p.returncode != 0:
        sys.stderr.write("graphviz dot failed\n")
        sys.exit(3)

if __name__ == "__main__":
    main()
