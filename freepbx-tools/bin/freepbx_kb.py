#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freepbx_kb.py
-------------
Searchable local knowledge base of PBX/telephony terminology and hardware
provisioning/troubleshooting runbooks, seeded from 123.Net's internal
documentation. Data lives in ../data/knowledge_base.json (title/category/
tags/body per entry) so it can keep growing without touching this script.

Deliberately excludes: org-only info (mission statement, office addresses,
team rosters), external product links, customer-identifying data (names,
specific extensions/directories tied to one real site), and any live
per-site/per-customer credentials. Standard fleet-wide default provisioning
passwords are included where the source docs treat them as such, since
they're routine information this same team already needs day-to-day —
distinct from a unique secret protecting one specific live customer system.

VARIABLE MAP
------------
Colors      : ANSI color codes for CLI output
KB_PATH     : Path to the knowledge_base.json data file
entries     : Loaded list of KB entry dicts

FUNCTION MAP
------------
load_entries        : Load and parse knowledge_base.json
_matches            : Case-insensitive term match against title/tags/body
cmd_search          : Search across all entries, print matching titles+excerpt
cmd_show            : Print one entry in full, by id or exact/best title match
cmd_list            : List all entries, optionally filtered by category
main                : CLI entry point
"""

import argparse, json, os, re, sys

class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

KB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "knowledge_base.json")
)

def load_entries():
    try:
        with open(KB_PATH, "r") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"{Colors.RED}Could not load knowledge base at {KB_PATH}: {e}{Colors.ENDC}")
        return []

def _matches(entry, term):
    term = term.lower()
    haystacks = [entry.get("title", ""), entry.get("category", ""), entry.get("body", "")]
    haystacks += entry.get("tags", [])
    return any(term in h.lower() for h in haystacks)

def _excerpt(body, term, width=100):
    """Return a short excerpt of body centered on the first match of term,
    falling back to the start of body if term isn't found in it directly
    (e.g. the match was in the title/tags instead)."""
    idx = body.lower().find(term.lower())
    if idx == -1:
        text = body[:width]
        return text + ("…" if len(body) > width else "")
    start = max(0, idx - width // 3)
    end = min(len(body), idx + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return prefix + body[start:end].replace("\n", " ") + suffix

def cmd_search(args):
    entries = load_entries()
    term = args.term
    matches = [e for e in entries if _matches(e, term)]

    if not matches:
        print(f"{Colors.YELLOW}No knowledge base entries matched '{term}'.{Colors.ENDC}")
        return 1

    print(f"\n{Colors.MAGENTA}{Colors.BOLD}Found {len(matches)} entr{'y' if len(matches) == 1 else 'ies'} matching '{term}':{Colors.ENDC}\n")
    for e in matches:
        print(f"  {Colors.GREEN}{Colors.BOLD}[{e['category']}]{Colors.ENDC} {Colors.CYAN}{Colors.BOLD}{e['title']}{Colors.ENDC}  {Colors.WHITE}({e['id']}){Colors.ENDC}")
        print(f"    {_excerpt(e.get('body', ''), term)}")
        print()

    print(f"{Colors.YELLOW}Use 'freepbx_kb.py show <id>' to view an entry in full.{Colors.ENDC}\n")
    return 0

def cmd_show(args):
    entries = load_entries()
    key = args.id_or_title.strip().lower()

    entry = next((e for e in entries if e["id"].lower() == key), None)
    if not entry:
        entry = next((e for e in entries if e["title"].lower() == key), None)
    if not entry:
        candidates = [e for e in entries if key in e["title"].lower() or key in e["id"].lower()]
        if len(candidates) == 1:
            entry = candidates[0]
        elif len(candidates) > 1:
            print(f"{Colors.YELLOW}Multiple entries match '{args.id_or_title}':{Colors.ENDC}")
            for e in candidates:
                print(f"  {e['id']}  —  {e['title']}")
            return 1

    if not entry:
        print(f"{Colors.RED}No entry found for '{args.id_or_title}'. Try 'freepbx_kb.py search {args.id_or_title}'.{Colors.ENDC}")
        return 1

    print(f"\n{Colors.MAGENTA}{Colors.BOLD}╔{'═' * 76}╗{Colors.ENDC}")
    title_line = f" [{entry['category']}] {entry['title']}"
    print(f"{Colors.MAGENTA}{Colors.BOLD}║{Colors.ENDC}{Colors.CYAN}{Colors.BOLD}{title_line[:76].ljust(76)}{Colors.ENDC}{Colors.MAGENTA}{Colors.BOLD}║{Colors.ENDC}")
    print(f"{Colors.MAGENTA}{Colors.BOLD}╚{'═' * 76}╝{Colors.ENDC}\n")
    print(entry.get("body", ""))
    tags = entry.get("tags") or []
    if tags:
        print(f"\n{Colors.WHITE}Tags: {', '.join(tags)}{Colors.ENDC}")
    print()
    return 0

def cmd_list(args):
    entries = load_entries()
    if args.category:
        entries = [e for e in entries if e["category"].lower() == args.category.lower()]
        if not entries:
            print(f"{Colors.YELLOW}No entries in category '{args.category}'.{Colors.ENDC}")
            return 1

    by_category = {}
    for e in entries:
        by_category.setdefault(e["category"], []).append(e)

    print(f"\n{Colors.MAGENTA}{Colors.BOLD}Knowledge Base ({len(entries)} entries){Colors.ENDC}\n")
    for category in sorted(by_category):
        print(f"  {Colors.GREEN}{Colors.BOLD}{category}{Colors.ENDC}")
        for e in sorted(by_category[category], key=lambda x: x["title"]):
            print(f"    {Colors.CYAN}{e['id']:<40}{Colors.ENDC} {e['title']}")
        print()
    return 0

def main():
    parser = argparse.ArgumentParser(
        description="Search 123.Net's internal PBX/telephony knowledge base (terminology + hardware runbooks)"
    )
    sub = parser.add_subparsers(dest="cmd")

    sp = sub.add_parser("search", help="Search across all entries")
    sp.add_argument("term", help="Search term")

    sp = sub.add_parser("show", help="Show one entry in full")
    sp.add_argument("id_or_title", help="Entry id or (partial) title")

    sp = sub.add_parser("list", help="List all entries, grouped by category")
    sp.add_argument("--category", help="Filter to one category (e.g. Runbook, Glossary, 'Feature Code')")

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    dispatch = {"search": cmd_search, "show": cmd_show, "list": cmd_list}
    sys.exit(dispatch[args.cmd](args))

if __name__ == "__main__":
    main()
