#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# freepbx_callflow_graphV3.py
# Build a call-flow SVG for a DID, expanding Time Conditions, IVRs, Ring Groups, Queues, etc.
# No Python DB drivers needed: we shell out to the mysql CLI.

import argparse
import subprocess
import sys
import re
import os

# ANSI Color codes for professional output in the terminal.
# These are purely for CLI aesthetics and don't affect the SVG.
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header():
    """
    Print a banner at the start of the program to make the script
    feel more like a "tool" than a random Python file.
    """
    print(Colors.BLUE + Colors.BOLD + """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║           🌊  FreePBX Call Flow Diagram Generator             ║
║                                                               ║
║              Visual SVG Graphs with Graphviz                  ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """ + Colors.ENDC)


# Default database name for a standard FreePBX install
DB = "asterisk"

# ---------- Debugging Utilities ----------

DEBUG_MODE = False  # global flag toggled by --debug


def dbg(msg: str) -> None:
    """Safe debug print that only outputs when --debug is passed."""
    if DEBUG_MODE:
        print(Colors.YELLOW + "[DEBUG] " + Colors.ENDC + msg)


# ---------- DB helper ---------------------------------------------------------

def q(sql, socket=None, user="root", password=None):
    """
    Execute a SQL query using the mysql CLI and return results as a list of tuples.

    Parameters:
        sql (str)       : The SQL query to run.
        socket (str)    : Optional path to the MySQL socket (e.g., /var/lib/mysql/mysql.sock).
        user (str)      : MySQL username (default: root).
        password (str)  : MySQL password (default: None).

    Returns:
        list[tuple]: Each row is represented as a tuple of column values (strings).
                     Returns [] on error or no output.
    """
    dbg(f"DB QUERY: {sql}")

    # Base mysql command with DB and user
    cmd = ["mysql", "-NBe", sql, DB, "-u", user]

    # Add password if provided
    if password:
        cmd += ["-p" + password]

    # Add socket if provided
    if socket:
        cmd += ["--socket", socket]

    # Execute the command; capture stdout and stderr
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True  # Python 3.6 compatible 'text' mode
    )

    # If mysql returned a non-zero exit code, treat it as an error
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        dbg("DB QUERY FAILED")
        return []

    out = p.stdout.strip()
    if not out:
        dbg("DB QUERY returned no rows")
        return []

    rows = [tuple(line.split("\t")) for line in out.splitlines()]
    dbg(f"DB QUERY returned {len(rows)} row(s)")
    return rows


# ---------- Friendly labels / lookups ----------------------------------------

def human_time_rules(rows):
    """
    Convert FreePBX timegroup rules to a readable multiline string.

    Input:
        rows: list of tuples, each row representing (timegroupid, time_string)
              where time_string looks like "HH:MM-HH:MM|mday|mon|dow"

    Output:
        A human-readable multi-line string summarizing the rules.
    """
    def pretty(rule):
        # FreePBX stores "HH:MM-HH:MM|mday|mon|dow"
        parts = rule.split("|")
        time = parts[0] if len(parts) > 0 else "*"
        mday = parts[1] if len(parts) > 1 else "*"
        mon = parts[2] if len(parts) > 2 else "*"
        dow = parts[3] if len(parts) > 3 else "*"

        # Turn "*" into "any" to avoid leaking raw asterisk syntax to the SVG label
        def anyify(x):
            return "any" if (x.strip() == "*" or x.strip() == "") else x

        # Cosmetic change: 09:00-17:00 -> 09h00-17h00 (just makes it slightly more readable)
        time = time.replace(":", "h", 1).replace(":", "m", 1)
        return f"{time} | day:{anyify(mday)} | mon:{anyify(mon)} | dow:{anyify(dow)}"

    # r[1] is the `time` field from timegroups_details
    rules = [pretty(r[1]) for r in rows]
    return "\n".join(rules) if rules else "no rules"


def fetch_users_map(socket, user, password):
    """
    Fetch all user extensions and names from FreePBX 'users' table and
    return them as a dict: { extension: name }.

    This is used to turn numeric extensions into "101 — Alice Smith" in labels.
    """
    dbg("Fetching users map")
    rows = q("SELECT extension,name FROM users;", socket, user, password)
    m = {ext: name for (ext, name) in rows}
    dbg(f"Users map size: {len(m)}")
    return m


def fetch_ringgroup(grpnum, socket, user, password):
    """
    Fetch a ring group definition from 'ringgroups' by its grpnum.

    Returns:
        tuple (grpnum, description, grplist, strategy, grptime, postdest)
        or None if not found.
    """
    dbg(f"DB: fetch_ringgroup({grpnum})")
    sql = ("SELECT grpnum,description,grplist,strategy,grptime,COALESCE(postdest,'') "
           "FROM ringgroups WHERE grpnum='{g}'").format(g=grpnum)
    rg = q(sql, socket, user, password)
    if not rg:
        dbg(f"Ring group {grpnum} not found")
    return rg[0] if rg else None


def fetch_queue_details(queue_id, socket, user, password):
    """
    Return details about a queue:

    Parameters:
        queue_id (str) : The queue extension (e.g. '600').

    Returns:
        (name, strategy, timeout, members_csv)

        name         : Friendly name/description from queues_config.descr
        strategy     : Queue strategy (e.g. ringall, leastrecent)
        timeout      : Max wait/timeout in seconds
        members_csv  : A comma-separated list of member endpoints (extensions or external numbers)
    """
    dbg(f"DB: fetch_queue_details({queue_id})")

    # Get strategy and timeout
    rows = q("""
        SELECT id,
               MAX(CASE WHEN keyword='strategy' THEN data END),
               MAX(CASE WHEN keyword='timeout'  THEN data END)
        FROM queues_details WHERE id='%s';""" % queue_id, socket, user, password)
    strategy, timeout = (rows[0][1], rows[0][2]) if rows else ("", "")

    # Compress all member entries into one CSV list
    mem = q("""
        SELECT GROUP_CONCAT(
                 TRIM(BOTH ',' FROM SUBSTRING_INDEX(SUBSTRING_INDEX(data,'@',1),'/',-1))
                 ORDER BY data SEPARATOR ',')
        FROM queues_details WHERE id='%s' AND keyword='member';""" % queue_id, socket, user, password)
    members = mem[0][0] if mem and mem[0][0] else ""

    # Get the queue descriptive name
    qc = q("SELECT extension,descr FROM queues_config WHERE extension='%s'" % queue_id,
           socket, user, password)
    name = qc[0][1] if qc else ""
    dbg(f"Queue {queue_id}: name='{name}', strategy='{strategy}', timeout='{timeout}', members='{members}'")
    return name, strategy, timeout, members


def fetch_ivr(ivr_id, socket, user, password):
    """
    Fetch IVR header and entries for a given IVR id.

    Returns:
        (name, options)

        name    : IVR name (string)
        options : list of (selection, dest) pairs.
    """
    dbg(f"DB: fetch_ivr({ivr_id})")

    # IVR basic info: id, name, announcement
    head = q("SELECT id,name,announcement FROM ivr_details WHERE id='%s'" % ivr_id,
             socket, user, password)
    if not head:
        dbg(f"IVR {ivr_id} not found")
        return None, []

    name = head[0][1]

    # IVR entries: selection (key) and dest (where the call goes)
    entries = q(
        "SELECT ivr_id, selection, dest FROM ivr_entries "
        "WHERE ivr_id='%s' ORDER BY selection" % ivr_id,
        socket, user, password
    )
    dbg(f"IVR {ivr_id} has {len(entries)} entries")
    return name, [(sel, dest) for (_ivr, sel, dest) in entries]


def fetch_timecondition(tc_id, socket, user, password):
    """
    Fetch a Time Condition configuration and its associated Time Group rules.
    """
    dbg(f"DB: fetch_timecondition({tc_id})")

    rows = q(
        "SELECT timeconditions_id,displayname,`time`,"
        "COALESCE(truegoto,''),COALESCE(falsegoto,'') "
        "FROM timeconditions WHERE timeconditions_id='%s'" % tc_id,
        socket, user, password
    )
    if not rows:
        dbg(f"Time condition {tc_id} not found")
        return None

    _id, display, tg_id, truegoto, falsegoto = rows[0]

    # Grab all rows belonging to the time group referenced by this time condition
    tg_rows = q(
        "SELECT timegroupid, `time` FROM timegroups_details "
        "WHERE timegroupid='%s' ORDER BY id" % tg_id,
        socket, user, password
    )

    dbg(f"Time condition {tc_id}: display='{display}', tg_id={tg_id}, rules={len(tg_rows)} row(s)")
    return {
        "display": display,
        "tg_id": tg_id,
        "rules": human_time_rules(tg_rows),
        "true": truegoto,
        "false": falsegoto
    }


def fetch_announcement(ann_id, socket, user, password):
    """
    Fetch an announcement by id.

    Returns:
        (description, post_dest) or (None, None) if not found.
    """
    dbg(f"DB: fetch_announcement({ann_id})")

    rows = q(
        "SELECT description, COALESCE(post_dest,'') "
        "FROM announcement WHERE announcement_id='%s'" % ann_id,
        socket, user, password
    )
    if not rows:
        dbg(f"Announcement {ann_id} not found")
        return None, None
    desc, post = rows[0]
    dbg(f"Announcement {ann_id}: desc='{desc}', post_dest='{post}'")
    return desc, post


def fetch_system_recording(rec_id, socket, user, password):
    """
    Return display name of a system recording id, or None.
    """
    dbg(f"DB: fetch_system_recording({rec_id})")

    # Try modern table first
    rows = q("SELECT displayname FROM recordings WHERE id='%s'" % rec_id,
             socket, user, password)
    if rows:
        dbg(f"Recording {rec_id} found in 'recordings'")
        return rows[0][0]

    # Fallback to legacy table
    rows = q("SELECT displayname FROM systemrecordings WHERE id='%s'" % rec_id,
             socket, user, password)
    if rows:
        dbg(f"Recording {rec_id} found in 'systemrecordings'")
        return rows[0][0]

    dbg(f"Recording {rec_id} not found in any table")
    return None


# ---------- Graph helper ------------------------------------------------------

class Graph:
    """
    Lightweight wrapper around a Graphviz 'dot' graph.
    """

    def __init__(self):
        # Seed with global graph attributes: left-to-right layout, node style, fonts, etc.
        self.lines = [
            'digraph G {',
            '  rankdir=LR;',  # Left-to-Right flow, more natural for call flows
            '  node [shape=box, style="rounded,filled", fillcolor="#f7f7f7", fontname="Helvetica"];',
            '  edge [fontname="Helvetica"];'
        ]
        self.ids = 0              # Counter used to generate unique node IDs
        self.node_ids = {}        # Maps logical 'key' -> 'n<number>'

    def new_id(self):
        """
        Allocate a new unique node ID (like n1, n2, ...).
        """
        self.ids += 1
        return f"n{self.ids}"

    def add_node(self, key, label):
        """
        Create a new node in the graph, or return an existing one if this key
        was already used.
        """
        if key in self.node_ids:
            nid = self.node_ids[key]
            dbg(f"Reusing node {nid} for key={key}")
            return nid

        nid = self.new_id()
        safe = label.replace('"', r"\"")
        self.lines.append(f'  {nid} [label="{safe}"];')
        self.node_ids[key] = nid
        dbg(f"Created node {nid} for key={key} with label='{label}'")
        return nid

    def add_edge(self, a, b, label=None):
        """
        Add a directed edge from node 'a' to node 'b'.
        """
        if label:
            self.lines.append(f'  {a} -> {b} [label="{label}"];')
            dbg(f"Created edge {a} -> {b} [label='{label}']")
        else:
            self.lines.append(f'  {a} -> {b};')
            dbg(f"Created edge {a} -> {b}")

    def render(self):
        """
        Finalize and return the entire DOT graph as a single string.
        """
        self.lines.append('}')
        dot = "\n".join(self.lines)
        dbg("Rendered DOT graph")
        return dot


# ---------- Resolver ----------------------------------------------------------

def parse_dest(dest):
    """
    Parse a FreePBX destination string into its components.
    """
    parts = dest.split(",")
    if not parts:
        return ("raw", dest, [])
    return (parts[0], parts[1:], dest)


def resolve_recursive(graph,
                      key,
                      dest,
                      users_map,
                      socket,
                      user,
                      password,
                      depth=0,
                      max_depth=25,
                      path=None):
    """
    Core engine: recursively "expand" a FreePBX destination into graph nodes.

    `path` is a list of dest strings seen so far on the current call path.
    It is used for loop detection (IVR <-> IVR, IVR <-> TC, etc.).
    """

    # Initialize path for the first call
    if path is None:
        path = []

    # Loop detection: if this destination already exists in the current path,
    # we have a cycle in the dialplan (e.g., IVR -> TC -> IVR).
    if dest in path:
        dbg(f"Loop detected at dest='{dest}' (already in path: {path})")
        loop_label = f"Loop detected\n{dest}"
        return graph.add_node(key, loop_label)

    # Hard safety brake in case something goes insane
    if depth > max_depth:
        dbg(f"Max depth exceeded at dest='{dest}'")
        return graph.add_node(key, f"Max depth reached at {dest}")

    # Build new path including this dest for child calls
    new_path = path + [dest]

    ctx, rest, raw = parse_dest(dest)
    dbg(f"Resolving dest='{dest}' depth={depth} ctx='{ctx}' rest={rest}")

    def add_terminal(lbl):
        """
        Helper: create a leaf node that does not expand further.
        """
        dbg(f"Creating terminal node for dest='{dest}' with label='{lbl}'")
        return graph.add_node(key, lbl)

    # ---- Time Conditions -----------------------------------------------------
    if ctx == "timeconditions":
        dbg(f"Handling Time Condition ID={rest[0] if rest else '<?> '}")
        tc_id = rest[0]
        info = fetch_timecondition(tc_id, socket, user, password)
        if not info:
            return add_terminal(f"Time Condition {tc_id} (not found)")

        lbl = (f"Time Condition: {info['display']}\n"
               f"Time Group {info['tg_id']}\n"
               f"{info['rules']}")
        nid = graph.add_node(key, lbl)

        tchild = resolve_recursive(
            graph,
            f"{raw}#T",
            info["true"],
            users_map,
            socket,
            user,
            password,
            depth + 1,
            max_depth,
            new_path
        )

        fchild = resolve_recursive(
            graph,
            f"{raw}#F",
            info["false"],
            users_map,
            socket,
            user,
            password,
            depth + 1,
            max_depth,
            new_path
        )

        graph.add_edge(nid, tchild, "TRUE")
        graph.add_edge(nid, fchild, "FALSE")
        return nid

    # ---- IVR -----------------------------------------------------------------
    elif ctx.startswith("ivr-"):
        dbg(f"Handling IVR block: ctx={ctx}")
        ivr_id = ctx.split("-")[1]
        name, options = fetch_ivr(ivr_id, socket, user, password)

        if name is None:
            return add_terminal(f"IVR {ivr_id} (not found)")

        nid = graph.add_node(key, f"IVR {ivr_id}: {name}")

        for sel, d in options:
            dbg(f"IVR {ivr_id}: option '{sel}' -> dest='{d}'")
            child = resolve_recursive(
                graph,
                f"{raw}#{sel}",
                d,
                users_map,
                socket,
                user,
                password,
                depth + 1,
                max_depth,
                new_path
            )
            graph.add_edge(nid, child, sel)
        return nid

    # ---- Announcement --------------------------------------------------------
    elif ctx.startswith("app-announcement-"):
        dbg(f"Handling Announcement context: {ctx}")
        ann_id = ctx.split("-")[-1]
        desc, post = fetch_announcement(ann_id, socket, user, password)

        lbl = f"Announcement {ann_id}: {desc or '(no description)'}"
        nid = graph.add_node(key, lbl)

        if post:
            dbg(f"Announcement {ann_id}: post-destination='{post}'")
            child = resolve_recursive(
                graph,
                f"{raw}#post",
                post,
                users_map,
                socket,
                user,
                password,
                depth + 1,
                max_depth,
                new_path
            )
            graph.add_edge(nid, child, "after")
        else:
            dbg(f"Announcement {ann_id}: no post-destination configured")
        return nid

    # ---- Play System Recording ----------------------------------------------
    elif ctx == "play-system-recording":
        dbg(f"Handling play-system-recording ctx; rest={rest}")
        rec_id = rest[0] if rest else ""
        name = fetch_system_recording(rec_id, socket, user, password) if rec_id else None
        return add_terminal(f"Play System Recording: {name or rec_id or '(unknown)'}")

    # ---- Queues --------------------------------------------------------------
    elif ctx == "ext-queues":
        dbg(f"Handling Queue ctx; rest={rest}")
        qid = rest[0]
        name, strategy, timeout, members = fetch_queue_details(qid, socket, user, password)

        pretty_members = []
        for m in (members.split(",") if members else []):
            m = m.strip()
            if not m:
                continue
            if m.endswith("#"):
                pretty_members.append(m)
            else:
                pretty_members.append(f"{m} {users_map.get(m, '')}".strip())

        label = (
            f"Queue {qid}: {name or '[no name]'}\n"
            f"strategy={strategy or '-'} timeout={timeout or '-'}\n"
            f"members: {', '.join(pretty_members) if pretty_members else '-'}"
        )
        return add_terminal(label)

    # ---- Ring Group ----------------------------------------------------------
    elif ctx == "ext-group":
        dbg(f"Handling Ring Group ctx; rest={rest}")
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
                members.append(token)
            else:
                members.append(f"{token} {users_map.get(token, '')}".strip())

        label = (
            f"Ring Group {grp}: {desc}\n"
            f"strategy={strategy} ring={grptime}s\n"
            f"members: {', '.join(members) if members else '-'}"
        )

        nid = graph.add_node(key, label)

        if postdest:
            dbg(f"Ring Group {grp}: post-destination='{postdest}'")
            child = resolve_recursive(
                graph,
                f"{raw}#post",
                postdest,
                users_map,
                socket,
                user,
                password,
                depth + 1,
                max_depth,
                new_path
            )
            graph.add_edge(nid, child, "post")
        else:
            dbg(f"Ring Group {grp}: no post-destination configured")
        return nid

    # ---- Direct to extension -------------------------------------------------
    elif ctx == "from-did-direct":
        dbg(f"Handling direct-to-extension ctx; rest={rest}")
        ext = rest[0]
        name = users_map.get(ext, "")
        return add_terminal(f"Extension {ext}{(' — ' + name) if name else ''}")

    # ---- Voicemail -----------------------------------------------------------
    elif ctx == "ext-local":
        dbg(f"Handling voicemail/local ctx; rest={rest}")
        target = rest[0] if rest else ""
        m = re.match(r"vm([ubsi])(\d+)", target)
        if m:
            code, ext = m.groups()
            suffix = {
                "u": "unavailable",
                "b": "busy",
                "s": "no message",
                "i": "immediate"
            }[code]
            name = users_map.get(ext, "")
            return add_terminal(f"Voicemail {ext}{(' — ' + name) if name else ''} ({suffix})")

    # ---- Directory -----------------------------------------------------------
    elif ctx == "directory":
        dbg("Handling directory ctx")
        return add_terminal("Directory")

    # ---- Conference ----------------------------------------------------------
    elif ctx == "ext-meetme":
        dbg(f"Handling conference ctx; rest={rest}")
        room = rest[0] if rest else ""
        return add_terminal(f"Conference {room}")

    # ---- Blackhole / Terminate ----------------------------------------------
    elif ctx == "app-blackhole":
        dbg("Handling app-blackhole ctx")
        return add_terminal("Terminate Call (blackhole)")

    # ---- Fallback / Unknown / Raw -------------------------------------------
    else:
        dbg(f"Unknown context '{ctx}', producing raw terminal node")
        return add_terminal(raw)


# ---------- CLI ---------------------------------------------------------------

def main():
    """
    Entrypoint for the CLI.
    """
    print_header()

    # Argument parser setup
    ap = argparse.ArgumentParser(
        description="Render FreePBX callflow for a DID to SVG "
                    "(expands Time Conditions, IVR, Queues, Ring Groups, Announcements)"
    )
    ap.add_argument("--did", required=True, help="DID to render (incoming.extension)")
    ap.add_argument("--out", required=True, help="Output SVG path")
    ap.add_argument("--db-user", default="root")
    ap.add_argument("--db-pass", default=None)
    ap.add_argument("--socket", default=None, help="MySQL socket path (e.g., /var/lib/mysql/mysql.sock)")
    ap.add_argument("--debug", action="store_true",
                    help="Enable verbose debug output")
    ap.add_argument("--debug-dot", action="store_true",
                    help="Dump the raw DOT graph to stdout and a .dot file next to the SVG")
    args = ap.parse_args()

    # Set global debug flag
    global DEBUG_MODE
    DEBUG_MODE = args.debug
    if DEBUG_MODE:
        print(Colors.YELLOW + "🔧 Debug mode enabled" + Colors.ENDC)

    print(Colors.CYAN + "📞 Analyzing DID: " + Colors.BOLD + args.did + Colors.ENDC)

    # Find inbound route for this DID
    dbg(f"Looking up inbound route for DID={args.did}")
    rows = q(
        "SELECT extension, COALESCE(description,''), destination "
        "FROM incoming WHERE extension='%s';" % args.did,
        args.socket,
        args.db_user,
        args.db_pass
    )

    if not rows:
        print(
            Colors.RED + "❌ No inbound route found for DID: " + args.did + Colors.ENDC,
            file=sys.stderr
        )
        sys.exit(2)

    did, label, dest = rows[0]

    print(Colors.GREEN + "✓ Found route: " + Colors.ENDC + (label or "(no label)"))
    print(Colors.YELLOW + "🔍 Tracing call flow..." + Colors.ENDC)
    dbg(f"Inbound route dest='{dest}'")

    # Build extension -> name mapping for prettier labels
    users_map = fetch_users_map(args.socket, args.db_user, args.db_pass)

    # Create graph and root node
    g = Graph()
    root_key = ("root", did)
    root_label = f"DID: {did}\n{label or '(no label)'}"
    dbg(f"Creating root node for DID={did}")
    root = g.add_node(root_key, root_label)

    # Resolve first hop with an empty path for loop detection
    dbg(f"Starting recursive resolution from dest='{dest}'")
    child = resolve_recursive(
        g,
        ("dest", dest),
        dest,
        users_map,
        args.socket,
        args.db_user,
        args.db_pass,
        depth=0,
        max_depth=25,
        path=[]
    )
    g.add_edge(root, child)

    print(Colors.CYAN + "🎨 Generating SVG diagram..." + Colors.ENDC)

    # Render DOT
    dot = g.render()

    # Optionally dump DOT for debugging
    if args.debug_dot:
        dot_file = args.out + ".dot"
        dbg(f"Writing DOT file to: {dot_file}")
        with open(dot_file, "w") as f:
            f.write(dot)
        print(Colors.CYAN + "\n📄 Raw DOT graph:" + Colors.ENDC)
        print(dot)
        print(Colors.GREEN + f"\nDOT saved to {dot_file}" + Colors.ENDC)

    # Call Graphviz
    dbg(f"Invoking 'dot' to render SVG: {args.out}")
    p = subprocess.run(["dot", "-Tsvg", "-o", args.out], input=dot.encode("utf-8"))
    if p.returncode != 0:
        print(Colors.RED + "❌ Graphviz dot command failed" + Colors.ENDC, file=sys.stderr)
        sys.exit(3)

    # Summary
    size_kb = os.path.getsize(args.out) / 1024
    print(
        Colors.GREEN + Colors.BOLD + "\n✓ Success! " + Colors.ENDC +
        "Diagram saved to: " + Colors.CYAN + args.out + Colors.ENDC
    )
    print(
        Colors.BOLD + "  File size: " + Colors.ENDC +
        "{:.1f} KB".format(size_kb)
    )
    print(
        Colors.BOLD + "  Nodes:     " + Colors.ENDC +
        str(len(g.node_ids))
    )
    print("")


if __name__ == "__main__":
    main()
