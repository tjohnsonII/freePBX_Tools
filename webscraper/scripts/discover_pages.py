"""
Page discovery tool for secure.123.net admin CGI pages.

Discovery-first approach: scrape all three pages and catalog every structural
element before any data extraction — forms, tables, links, IDs, classes,
scripts, headers, input names, select options, etc.

Saves per-page:
  var/discovery/<page>_raw.html        — raw HTML response
  var/discovery/<page>_discovery.json  — full structured catalog
  var/discovery/<page>_summary.txt     — human-readable summary

Usage:
  python discover_pages.py            # discover all three pages
  python discover_pages.py orders     # discover only orders_web_admin.cgi
  python discover_pages.py account    # discover only account_edit.cgi
  python discover_pages.py dispatch   # discover only dispatch.cgi

Credentials from env (or .env file in webscraper/ parent):
  ORDERS_123NET_USERNAME
  ORDERS_123NET_PASSWORD
  ORDERS_123NET_PM  (optional, defaults to USERNAME)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

# ── Load .env from the webscraper parent directory ────────────────────────────
_HERE = Path(__file__).resolve().parents[1]  # webscraper/
for _env_path in [_HERE / ".env", _HERE.parent / ".env"]:
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())
        break

import requests
from bs4 import BeautifulSoup, Comment, Tag

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)

BASE_URL     = "https://secure.123.net"
_ADMIN_BASE  = "https://secure.123.net/cgi-bin/web_interface/admin/"
ORDERS_URL   = "https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi"
ACCOUNT_URL  = "https://secure.123.net/cgi-bin/web_interface/admin/account_edit.cgi"
DISPATCH_URL = "https://secure.123.net/cgi-bin/web_interface/admin/dispatch.cgi"

OUT_DIR = _HERE / "var" / "discovery"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _build_session() -> requests.Session:
    user   = os.environ.get("ORDERS_123NET_USERNAME", "").strip()
    passwd = os.environ.get("ORDERS_123NET_PASSWORD", "").strip()
    if not user or not passwd:
        sys.exit("ERROR: Set ORDERS_123NET_USERNAME and ORDERS_123NET_PASSWORD env vars.")
    s = requests.Session()
    s.auth = (user, passwd)
    s.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )
    return s


# ── Core discoverer ───────────────────────────────────────────────────────────

def _resolve(href: str, base: str) -> str:
    if not href:
        return ""
    try:
        return urljoin(base, href)
    except Exception:
        return href


def discover_page(html: str, source_url: str) -> dict[str, Any]:
    """
    Full structural catalog of a page.

    Returns a dict with sections:
      meta         — title, base_url, status
      tag_counts   — every HTML tag and how many times it appears
      ids          — all element IDs
      classes      — all CSS classes (with usage count)
      headings     — h1-h6 text
      forms        — every form: action, method, all fields with types/options
      tables       — every table: headers, column count, row count, sample rows
      links        — all hrefs grouped by pattern (CGI, anchor, external, etc.)
      scripts      — inline script snippets (first 300 chars each)
      comments     — HTML comments
      inputs_flat  — flat list of every input/select/textarea name found anywhere
      select_options — all <select name> → list of option values
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Meta ─────────────────────────────────────────────────────────────────
    title = soup.find("title")
    meta: dict[str, Any] = {
        "source_url": source_url,
        "title":      title.get_text(strip=True) if title else "",
        "html_length": len(html),
    }

    # ── Tag inventory ─────────────────────────────────────────────────────────
    tag_counts = Counter(tag.name for tag in soup.find_all(True))

    # ── IDs and classes ───────────────────────────────────────────────────────
    all_ids: list[str] = []
    class_counter: Counter = Counter()
    for tag in soup.find_all(True):
        if tag.get("id"):
            all_ids.append(f"{tag.name}#{tag['id']}")
        for cls in (tag.get("class") or []):
            class_counter[cls] += 1

    # ── Headings ──────────────────────────────────────────────────────────────
    headings: list[dict[str, str]] = []
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            text = h.get_text(" ", strip=True)
            if text:
                headings.append({"level": f"h{level}", "text": text})

    # ── Forms ─────────────────────────────────────────────────────────────────
    forms: list[dict[str, Any]] = []
    for form in soup.find_all("form"):
        form_info: dict[str, Any] = {
            "action":  _resolve(form.get("action", ""), source_url),
            "method":  (form.get("method") or "GET").upper(),
            "id":      form.get("id", ""),
            "name":    form.get("name", ""),
            "fields":  [],
        }
        for inp in form.find_all(["input", "select", "textarea", "button"]):
            name  = inp.get("name", "")
            itype = inp.get("type", inp.name).lower()
            field: dict[str, Any] = {
                "tag":   inp.name,
                "name":  name,
                "type":  itype,
                "id":    inp.get("id", ""),
                "value": inp.get("value", ""),
                "placeholder": inp.get("placeholder", ""),
            }
            if inp.name == "select":
                field["options"] = [
                    {"value": o.get("value", o.get_text(strip=True)),
                     "text":  o.get_text(strip=True),
                     "selected": o.has_attr("selected")}
                    for o in inp.find_all("option")
                ]
                selected = inp.find("option", selected=True)
                field["selected_value"] = selected.get("value", selected.get_text(strip=True)) if selected else ""
            elif inp.name == "textarea":
                field["value"] = inp.get_text(strip=True)
            form_info["fields"].append(field)
        forms.append(form_info)

    # ── Tables ───────────────────────────────────────────────────────────────
    tables: list[dict[str, Any]] = []
    for t_idx, table in enumerate(soup.find_all("table")):
        all_rows = table.find_all("tr")
        headers: list[str] = []
        # Look for <th> or a header-like first row
        th_row = table.find("tr", recursive=False)
        if th_row:
            ths = th_row.find_all("th")
            if ths:
                headers = [th.get_text(" ", strip=True) for th in ths]
            else:
                # Check if first row looks like a header (bold, class, or no data pattern)
                tds = th_row.find_all("td")
                if tds and all(td.find("b") or td.get("class") or td.find("strong") for td in tds if td.get_text(strip=True)):
                    headers = [td.get_text(" ", strip=True) for td in tds]

        # Sample up to 5 data rows
        data_rows = table.find_all("tr")[len(headers) > 0:]
        sample: list[list[str]] = []
        for tr in data_rows[:5]:
            cells = tr.find_all(["td", "th"])
            row_text = [c.get_text(" ", strip=True) for c in cells]
            if any(row_text):
                sample.append(row_text)

        # All links inside table
        table_links = [
            {"text": a.get_text(strip=True), "href": _resolve(a.get("href", ""), source_url)}
            for a in table.find_all("a", href=True)
        ]

        # Unique classes on cells
        cell_classes: list[str] = list({
            cls
            for td in table.find_all(["td", "th"])
            for cls in (td.get("class") or [])
        })

        tables.append({
            "index":       t_idx,
            "id":          table.get("id", ""),
            "class":       table.get("class", []),
            "row_count":   len(all_rows),
            "col_count":   max((len(tr.find_all(["td", "th"])) for tr in all_rows), default=0),
            "headers":     headers,
            "sample_rows": sample,
            "links":       table_links[:30],
            "cell_classes": cell_classes,
        })

    # ── Links ────────────────────────────────────────────────────────────────
    link_patterns: dict[str, list[str]] = defaultdict(list)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        abs_href = _resolve(href, source_url)
        parsed = urlparse(abs_href)
        if ".cgi" in parsed.path:
            bucket = "cgi:" + parsed.path.split("/")[-1]
        elif href.startswith("#"):
            bucket = "anchor"
        elif href.startswith("javascript"):
            bucket = "javascript"
        elif parsed.netloc and parsed.netloc != urlparse(source_url).netloc:
            bucket = "external"
        elif href.startswith("mailto:"):
            bucket = "mailto"
        else:
            bucket = "relative"
        entry = f"{a.get_text(strip=True)[:40]} → {abs_href}"
        if entry not in link_patterns[bucket]:
            link_patterns[bucket].append(entry)

    # ── Inline scripts ───────────────────────────────────────────────────────
    scripts: list[str] = []
    for script in soup.find_all("script"):
        src = script.get("src")
        content = script.string or ""
        if content.strip():
            scripts.append(content.strip()[:500])
        elif src:
            scripts.append(f"[external src={src}]")

    # ── HTML comments ────────────────────────────────────────────────────────
    comments = [str(c).strip()[:200] for c in soup.find_all(string=lambda t: isinstance(t, Comment)) if str(c).strip()]

    # ── Flat input/select inventory (outside forms too) ──────────────────────
    inputs_flat: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for inp in soup.find_all(["input", "select", "textarea"]):
        name = inp.get("name", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        inputs_flat.append({
            "tag":  inp.name,
            "name": name,
            "type": inp.get("type", inp.name),
            "id":   inp.get("id", ""),
        })

    select_options: dict[str, list[str]] = {}
    for sel in soup.find_all("select"):
        name = sel.get("name", "")
        if name:
            select_options[name] = [
                o.get("value", o.get_text(strip=True))
                for o in sel.find_all("option")
            ]

    return {
        "meta":           meta,
        "tag_counts":     dict(tag_counts.most_common()),
        "ids":            all_ids,
        "classes":        dict(class_counter.most_common(40)),
        "headings":       headings,
        "forms":          forms,
        "tables":         tables,
        "links":          dict(link_patterns),
        "scripts":        scripts,
        "comments":       comments,
        "inputs_flat":    inputs_flat,
        "select_options": select_options,
    }


# ── Pretty summary printer ────────────────────────────────────────────────────

def _fmt_summary(name: str, d: dict[str, Any]) -> str:
    lines: list[str] = []

    def ln(s: str = "") -> None:
        lines.append(s)

    def banner(s: str) -> None:
        ln()
        ln("=" * 70)
        ln(f"  {s}")
        ln("=" * 70)

    def section(s: str) -> None:
        ln()
        ln(f"── {s} " + "─" * max(0, 66 - len(s)))

    banner(f"DISCOVERY: {name}")
    m = d["meta"]
    ln(f"  URL    : {m['source_url']}")
    ln(f"  Title  : {m['title']}")
    ln(f"  HTML   : {m['html_length']:,} bytes")

    section("TAG COUNTS")
    for tag, count in list(d["tag_counts"].items())[:25]:
        ln(f"  {tag:<20} {count}")

    section(f"HEADINGS ({len(d['headings'])})")
    for h in d["headings"]:
        ln(f"  [{h['level']}] {h['text']}")

    section(f"IDs ({len(d['ids'])})")
    for eid in d["ids"]:
        ln(f"  {eid}")

    section(f"CSS CLASSES (top 20)")
    for cls, cnt in list(d["classes"].items())[:20]:
        ln(f"  .{cls:<30} ×{cnt}")

    section(f"FORMS ({len(d['forms'])})")
    for i, form in enumerate(d["forms"]):
        ln(f"  Form {i}: action={form['action']}  method={form['method']}")
        for f in form["fields"]:
            if f["name"]:
                opts = ""
                if f["tag"] == "select":
                    opt_vals = [o["value"] for o in f.get("options", [])]
                    opts = f"  options=[{', '.join(opt_vals[:10])}{'...' if len(opt_vals)>10 else ''}]"
                ln(f"    [{f['type']:<12}] name={f['name']:<35} value={f['value']!r}{opts}")

    section(f"TABLES ({len(d['tables'])})")
    for t in d["tables"]:
        ln(f"  Table {t['index']}  id={t['id']!r}  rows={t['row_count']}  cols={t['col_count']}")
        if t["headers"]:
            ln(f"    Headers : {t['headers']}")
        for r in t["sample_rows"][:3]:
            ln(f"    Row     : {r}")
        if t["links"]:
            ln(f"    Links   : {t['links'][:5]}")
        if t["cell_classes"]:
            ln(f"    Cell CSS: {t['cell_classes']}")

    section(f"LINKS")
    for bucket, hrefs in d["links"].items():
        ln(f"  [{bucket}]")
        for h in hrefs[:10]:
            ln(f"    {h}")

    section(f"FLAT INPUT/SELECT INVENTORY ({len(d['inputs_flat'])})")
    for inp in d["inputs_flat"]:
        ln(f"  [{inp['tag']:<8}] name={inp['name']:<35} type={inp['type']}")

    section(f"SELECT OPTIONS")
    for sel_name, opts in d["select_options"].items():
        ln(f"  {sel_name}: {opts[:15]}{'...' if len(opts)>15 else ''}")

    if d["scripts"]:
        section(f"INLINE SCRIPTS ({len(d['scripts'])})")
        for s in d["scripts"][:5]:
            for line in textwrap.wrap(s[:300], 66):
                ln(f"  {line}")

    if d["comments"]:
        section(f"HTML COMMENTS ({len(d['comments'])})")
        for c in d["comments"][:10]:
            ln(f"  {c[:120]}")

    return "\n".join(lines)


# ── Per-page fetch strategies ─────────────────────────────────────────────────

def discover_orders(session: requests.Session, pm: str) -> dict[str, Any]:
    """GET + POST the orders page (both responses cataloged)."""
    LOGGER.info("Discovering orders_web_admin.cgi ...")

    LOGGER.info("  GET (session init) ...")
    get_resp = session.get(ORDERS_URL, timeout=20, allow_redirects=True)
    get_resp.raise_for_status()
    LOGGER.info("  GET status=%d  url=%s", get_resp.status_code, get_resp.url)

    # Save GET response
    (OUT_DIR / "orders_get_raw.html").write_text(get_resp.text, encoding="utf-8")
    get_discovery = discover_page(get_resp.text, get_resp.url)

    # POST with PM filter
    payload = {
        "web_show_bill":      "y",
        "web_search_order_id": "",
        "web_request_type":   "",
        "web_fac_type":       "",
        "web_bucket":         "",
        "web_pm":             "",
        "web_netopsengineer": pm,
        "web_tech":           "",
        "web_cft":            "",
        "web_calendar":       "",
        "web_order_type":     "",
        "web_status":         "",
        "web_company_type":   "",
        "web_priority":       "",
        "web_exp":            "",
        "web_neteng":         "All",
        "web_core":           "All",
        "web_bill":           "All",
        "web_last_note":      "summary",
        "web_sort":           "standard",
    }
    LOGGER.info("  POST (pm=%s) ...", pm)
    post_resp = session.post(ORDERS_URL, data=payload, timeout=30)
    post_resp.raise_for_status()
    LOGGER.info("  POST status=%d  bytes=%d", post_resp.status_code, len(post_resp.text))

    (OUT_DIR / "orders_post_raw.html").write_text(post_resp.text, encoding="utf-8")
    post_discovery = discover_page(post_resp.text, post_resp.url)

    # Combined result
    result = {
        "page": "orders_web_admin.cgi",
        "get":  get_discovery,
        "post": post_discovery,
    }
    return result


def discover_account(session: requests.Session, handle: str | None = None) -> dict[str, Any]:
    """
    GET account_edit.cgi.
    If handle is provided, fetches that specific account.
    Also tries a bare GET with no params to see the default/search page.
    """
    LOGGER.info("Discovering account_edit.cgi ...")

    responses: list[dict[str, Any]] = []

    # Bare GET — see the default page
    LOGGER.info("  GET (bare, no params) ...")
    resp = session.get(ACCOUNT_URL, timeout=20, allow_redirects=True)
    LOGGER.info("  GET status=%d  bytes=%d", resp.status_code, len(resp.text))
    (OUT_DIR / "account_bare_raw.html").write_text(resp.text, encoding="utf-8")
    responses.append({"variant": "bare_get", **discover_page(resp.text, resp.url)})

    # If handle provided, fetch that specific account
    if handle:
        url = f"{ACCOUNT_URL}?handle={handle}"
        LOGGER.info("  GET handle=%s ...", handle)
        resp2 = session.get(url, timeout=20, allow_redirects=True)
        LOGGER.info("  GET status=%d  bytes=%d", resp2.status_code, len(resp2.text))
        (OUT_DIR / "account_handle_raw.html").write_text(resp2.text, encoding="utf-8")
        responses.append({"variant": f"handle={handle}", **discover_page(resp2.text, resp2.url)})

    return {"page": "account_edit.cgi", "responses": responses}


def discover_dispatch(session: requests.Session, pm: str) -> dict[str, Any]:
    """GET + POST dispatch.cgi, discovering form params dynamically."""
    LOGGER.info("Discovering dispatch.cgi ...")

    LOGGER.info("  GET (bare) ...")
    get_resp = session.get(DISPATCH_URL, timeout=20, allow_redirects=True)
    LOGGER.info("  GET status=%d  bytes=%d", get_resp.status_code, len(get_resp.text))
    (OUT_DIR / "dispatch_get_raw.html").write_text(get_resp.text, encoding="utf-8")
    get_discovery = discover_page(get_resp.text, get_resp.url)

    # Discover form params from the GET response
    soup = BeautifulSoup(get_resp.text, "html.parser")
    base_payload: dict[str, str] = {}
    form = soup.find("form")
    if form:
        for inp in form.find_all(["input", "select", "textarea"]):
            name  = (inp.get("name") or "").strip()
            itype = (inp.get("type") or "text").lower()
            if not name or itype in ("submit", "button", "image", "reset"):
                continue
            if inp.name == "select":
                selected = inp.find("option", selected=True)
                base_payload[name] = selected.get_text(strip=True) if selected else ""
            else:
                base_payload[name] = (inp.get("value") or "").strip()

    # Override with our filter
    override = {
        "web_netopsengineer": pm,
        "web_pm":             "",
        "web_tech":           "",
        "web_status":         "",
        "web_sort":           "standard",
        "web_show_bill":      "y",
    }
    payload = {**base_payload, **override}
    LOGGER.info("  POST (pm=%s, %d params: %s) ...", pm, len(payload), list(payload.keys()))

    post_resp = session.post(DISPATCH_URL, data=payload, timeout=30)
    LOGGER.info("  POST status=%d  bytes=%d", post_resp.status_code, len(post_resp.text))
    (OUT_DIR / "dispatch_post_raw.html").write_text(post_resp.text, encoding="utf-8")
    post_discovery = discover_page(post_resp.text, post_resp.url)

    return {
        "page":          "dispatch.cgi",
        "form_params":   list(payload.keys()),
        "get":           get_discovery,
        "post":          post_discovery,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Force UTF-8 on Windows console so non-ASCII page content doesn't crash print()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pm = os.environ.get("ORDERS_123NET_PM", os.environ.get("ORDERS_123NET_USERNAME", "")).strip()
    if not pm:
        sys.exit("ERROR: Set ORDERS_123NET_USERNAME or ORDERS_123NET_PM")

    target = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    session = _build_session()

    results: dict[str, Any] = {}

    # ── Orders ───────────────────────────────────────────────────────────────
    if target in ("all", "orders"):
        try:
            r = discover_orders(session, pm)
            results["orders"] = r
            for variant, key in [("GET response", "get"), ("POST response (filtered)", "post")]:
                summary = _fmt_summary(f"orders_web_admin.cgi — {variant}", r[key])
                slug = "get" if key == "get" else "post"
                (OUT_DIR / f"orders_{slug}_summary.txt").write_text(summary, encoding="utf-8")
                print(summary)
            (OUT_DIR / "orders_discovery.json").write_text(
                json.dumps(r, indent=2, default=str), encoding="utf-8"
            )
            LOGGER.info("Saved orders discovery → %s", OUT_DIR / "orders_discovery.json")
        except Exception as exc:
            LOGGER.error("orders discovery failed: %s", exc)
            raise

    # ── Account ──────────────────────────────────────────────────────────────
    if target in ("all", "account"):
        # Try to pick a handle from orders discovery if available
        handle: str | None = None
        if "orders" in results:
            for t in results["orders"]["post"].get("tables", []):
                for lnk in t.get("links", []):
                    href = lnk.get("href", "")
                    from urllib.parse import parse_qs, urlparse as _up
                    qs = parse_qs(_up(href).query)
                    for k in ("handle", "account", "acct"):
                        if k in qs:
                            handle = qs[k][0]
                            break
                    if handle:
                        break
                if handle:
                    break
        if handle:
            LOGGER.info("Using handle=%s from orders discovery for account page", handle)
        try:
            r = discover_account(session, handle)
            results["account"] = r
            for resp_d in r["responses"]:
                variant = resp_d["variant"]
                summary = _fmt_summary(f"account_edit.cgi — {variant}", resp_d)
                slug = variant.replace("=", "_").replace("/", "_")
                (OUT_DIR / f"account_{slug}_summary.txt").write_text(summary, encoding="utf-8")
                print(summary)
            (OUT_DIR / "account_discovery.json").write_text(
                json.dumps(r, indent=2, default=str), encoding="utf-8"
            )
            LOGGER.info("Saved account discovery → %s", OUT_DIR / "account_discovery.json")
        except Exception as exc:
            LOGGER.error("account discovery failed: %s", exc)
            raise

    # ── Dispatch ─────────────────────────────────────────────────────────────
    if target in ("all", "dispatch"):
        try:
            r = discover_dispatch(session, pm)
            results["dispatch"] = r
            for variant, key in [("GET response", "get"), ("POST response (filtered)", "post")]:
                summary = _fmt_summary(f"dispatch.cgi — {variant}", r[key])
                slug = "get" if key == "get" else "post"
                (OUT_DIR / f"dispatch_{slug}_summary.txt").write_text(summary, encoding="utf-8")
                print(summary)
            (OUT_DIR / "dispatch_discovery.json").write_text(
                json.dumps(r, indent=2, default=str), encoding="utf-8"
            )
            LOGGER.info("Saved dispatch discovery → %s", OUT_DIR / "dispatch_discovery.json")
        except Exception as exc:
            LOGGER.error("dispatch discovery failed: %s", exc)
            raise

    # ── Master index ──────────────────────────────────────────────────────────
    index = {
        "pages_discovered": list(results.keys()),
        "output_dir": str(OUT_DIR),
        "files": [str(f.name) for f in sorted(OUT_DIR.iterdir()) if f.is_file()],
    }
    (OUT_DIR / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    print()
    print("=" * 70)
    print("DISCOVERY COMPLETE")
    print(f"  Output dir : {OUT_DIR}")
    print(f"  Pages      : {', '.join(results.keys())}")
    print(f"  Files      : {len(index['files'])}")
    print("=" * 70)


if __name__ == "__main__":
    main()
