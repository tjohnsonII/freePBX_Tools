from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class VpbxConfig:
    base_url: str
    username: str
    password: str


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_header(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    aliases = {
        "name": "name",
        "status": "account_status",
        "account status": "account_status",
        "web order": "web_order",
        "deployment id": "deployment_id",
        "switch": "switch",
        "devices": "devices",
        "ip": "ip",
        "handle": "handle",
    }
    return aliases.get(text, text.replace(" ", "_"))


def _extract_form_fields(form: Any) -> tuple[str | None, str | None, dict[str, str]]:
    fields: dict[str, str] = {}
    username_field: str | None = None
    password_field: str | None = None
    for element in form.find_all("input"):
        name = (element.get("name") or "").strip()
        if not name:
            continue
        input_type = (element.get("type") or "text").strip().lower()
        fields[name] = element.get("value") or ""
        lowered = name.lower()
        if input_type == "password" or "password" in lowered or lowered in {"pass", "pwd"}:
            password_field = name
        if lowered in {"username", "user", "login", "email"}:
            username_field = name
    return username_field, password_field, fields


def _login(session: requests.Session, config: VpbxConfig, target_url: str) -> None:
    first = session.get(target_url, timeout=30)
    first.raise_for_status()
    soup = BeautifulSoup(first.text, "lxml")
    form = soup.find("form")
    if form is None:
        return

    username_field, password_field, fields = _extract_form_fields(form)
    if not password_field:
        return
    action = form.get("action") or target_url
    login_url = urljoin(target_url, action)
    fields[username_field or "username"] = config.username
    fields[password_field] = config.password
    response = session.post(login_url, data=fields, timeout=30)
    response.raise_for_status()


def fetch_handles(config: VpbxConfig) -> list[dict[str, str]]:
    session = requests.Session()
    target_url = urljoin(config.base_url.rstrip("/") + "/", "cgi-bin/web_interface/admin/vpbx.cgi")
    _login(session, config, target_url)
    page = session.get(target_url, timeout=30)
    page.raise_for_status()

    soup = BeautifulSoup(page.text, "lxml")
    table = None
    for candidate in soup.find_all("table"):
        headers = [_normalize_header(th.get_text(" ", strip=True)) for th in candidate.find_all("th")]
        if "handle" in headers:
            table = candidate
            break
    if table is None:
        raise RuntimeError("Unable to find VPBX handles table on vpbx.cgi")

    headers = [_normalize_header(th.get_text(" ", strip=True)) for th in table.find_all("th")]
    discovered: dict[str, dict[str, str]] = {}
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        values = [cell.get_text(" ", strip=True) for cell in cells]
        payload = {headers[idx]: values[idx] for idx in range(min(len(headers), len(values)))}
        handle = (payload.get("handle") or "").strip()
        if not handle:
            continue
        discovered[handle] = {
            "handle": handle,
            "name": payload.get("name") or "",
            "account_status": payload.get("account_status") or payload.get("status") or "",
            "ip": payload.get("ip") or "",
            "web_order": payload.get("web_order") or "",
            "deployment_id": payload.get("deployment_id") or "",
            "switch": payload.get("switch") or "",
            "devices": payload.get("devices") or "",
            "last_seen_utc": _iso_now(),
        }
    return list(discovered.values())

