#!/usr/bin/env python3
"""
Convert Selenium scraper outputs into per-handle SQLite knowledge bases.

Inputs (from webscraper/output/<run>):
- scrape_results_<HANDLE>.json (preferred)
- debug_post_search_pageN_<HANDLE>.html (fallback)
- ticket_<HANDLE>_<ID>.html (optional details)

Outputs:
- knowledge_base/<HANDLE>_tickets.db
- knowledge_base/<HANDLE>_tickets.json (summary)

Notes:
- Python 3.6+ compatible, uses BeautifulSoup if available.
- Minimal extraction when only HTML is present: Ticket table rows with headers containing 'Ticket ID'.
"""

import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None

# Reuse DB builder from ticket_scraper for consistent schema
from ticket_scraper import KnowledgeBaseBuilder


def parse_ticket_table_html(html_text: str) -> List[Dict[str, Any]]:
    """Parse an HTML page to extract ticket rows from a table whose header contains 'Ticket ID'."""
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    tickets = []
    tables = soup.find_all('table')
    target = None
    for table in tables:
        header_row = table.find('tr')
        if header_row and 'Ticket ID' in header_row.get_text():
            target = table
            break
    if not target:
        return tickets
    rows = target.find_all('tr')[1:]  # skip header
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 2:
            continue
        # ticket id and url from first col
        link = cols[0].find('a')
        ticket_id = (link.text.strip() if link else cols[0].get_text(strip=True))
        subject = cols[1].get_text(strip=True) if len(cols) > 1 else ''
        status = cols[2].get_text(strip=True) if len(cols) > 2 else ''
        priority = cols[3].get_text(strip=True) if len(cols) > 3 else ''
        created = cols[4].get_text(strip=True) if len(cols) > 4 else ''
        tickets.append({
            'ticket_id': ticket_id,
            'subject': subject,
            'status': status,
            'priority': priority,
            'created_date': created,
            'messages': [],
            'resolution': '',
            'categories': [],
            'keywords': [],
        })
    return tickets


def parse_ticket_detail_html(html_text: str) -> Dict[str, Any]:
    """Parse a ticket detail page to extract a best-effort resolution and messages."""
    data = {'messages': [], 'resolution': ''}
    if BeautifulSoup is None:
        return data
    soup = BeautifulSoup(html_text, 'html.parser')
    # Collect rows from tables as messages
    for table in soup.find_all('table'):
        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if not tds:
                continue
            text = ' '.join(td.get_text(' ', strip=True) for td in tds)
            if text:
                data['messages'].append({'author': '', 'date': '', 'content': text})
    # Heuristic resolution: last message content
    if data['messages']:
        data['resolution'] = data['messages'][-1]['content']
    return data


def ingest_handle(run_dir: Path, out_dir: Path, handle: str) -> bool:
    """Ingest one handle's Selenium artifacts into SQLite and JSON."""
    # Preferred JSON result
    json_path = run_dir / f"scrape_results_{handle}.json"
    tickets: List[Dict[str, Any]] = []
    if json_path.exists():
        try:
            with open(str(json_path), 'r', encoding='utf-8') as f:
                result = json.load(f)
            tickets = result.get('ticket_details') or result.get('tickets') or []
            # Normalize fields
            norm = []
            for t in tickets:
                norm.append({
                    'ticket_id': str(t.get('id') or t.get('ticket_id') or '').strip(),
                    'subject': t.get('subject') or t.get('title') or '',
                    'status': t.get('status') or '',
                    'priority': t.get('priority') or '',
                    'created_date': t.get('created_date') or '',
                    'resolution': t.get('resolution') or '',
                    'messages': t.get('messages') or [],
                    'categories': t.get('categories') or [],
                    'keywords': t.get('keywords') or [],
                })
            tickets = norm
        except Exception:
            tickets = []
    # Fallback: parse post-search pages
    if not tickets:
        pages = sorted(run_dir.glob(f"debug_post_search_page*_" + handle + ".html"))
        for pg in pages:
            try:
                html = pg.read_text(encoding='utf-8', errors='ignore')
                tickets.extend(parse_ticket_table_html(html))
            except Exception:
                continue
    if not tickets:
        return False
    # Build DB
    db_path = out_dir / f"{handle}_tickets.db"
    kb = KnowledgeBaseBuilder(str(db_path))
    for t in tickets:
        # If ticket detail HTML exists, supplement
        safe_id = (t.get('ticket_id') or '').replace('/', '_').replace(' ', '_')
        t_path = run_dir / f"ticket_{handle}_{safe_id}.html"
        if t_path.exists():
            try:
                detail_html = t_path.read_text(encoding='utf-8', errors='ignore')
                d = parse_ticket_detail_html(detail_html)
                if d.get('messages'):
                    t['messages'] = d['messages']
                if d.get('resolution'):
                    t['resolution'] = d['resolution']
            except Exception:
                pass
        kb.add_ticket(t, handle)
    # Export summary JSON
    summary = kb.generate_knowledge_base_report(handle)
    out_json = out_dir / f"{handle}_tickets.json"
    with open(str(out_json), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    return True


def main():
    ap = argparse.ArgumentParser(description='Convert Selenium outputs to per-handle SQLite DBs')
    ap.add_argument('--input-dir', default=str(Path('webscraper')/ 'output' / 'kb-run'), help='Selenium output run directory')
    ap.add_argument('--out-dir', default='knowledge_base', help='Destination for per-handle DBs')
    ap.add_argument('--limit', type=int, help='Process only first N handles discovered')
    args = ap.parse_args()

    run_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)

    # Discover handles from files present
    handles = set()
    for p in run_dir.glob('debug_html_*.html'):
        base = p.stem[len('debug_html_'):]
        if base:
            handles.add(base)
    for p in run_dir.glob('debug_post_search_page1_*.html'):
        base = p.stem[len('debug_post_search_page1_'):]
        if base:
            handles.add(base)
    for p in run_dir.glob('scrape_results_*.json'):
        base = p.stem[len('scrape_results_'):]
        if base:
            handles.add(base)
    handles = sorted(handles)
    if args.limit:
        handles = handles[:args.limit]
    if not handles:
        print('[ERROR] No handles discovered in input directory')
        return 1
    print(f'[INFO] Discovered {len(handles)} handles to ingest from {run_dir}')
    processed = 0
    for h in handles:
        ok = ingest_handle(run_dir, out_dir, h)
        if ok:
            processed += 1
            print(f'[OK] Ingested {h}')
        else:
            print(f'[WARN] No ticket artifacts found for {h}')
    print(f'[SUMMARY] processed={processed} handles; out_dir={out_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
