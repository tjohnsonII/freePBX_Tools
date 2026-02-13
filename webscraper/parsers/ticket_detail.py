import re
from typing import Any, List, Optional


def normalize_label(label: str) -> str:
    cleaned = re.sub(r"[:\s]+$", "", label.strip())
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", cleaned.strip().lower())
    return cleaned.strip("_")


def extract_label_value_pairs(soup: Any) -> dict:
    fields: dict[str, Any] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            raw_label = cells[0].get_text(" ", strip=True)
            raw_value = cells[1].get_text(" ", strip=True)
            if not raw_label or not raw_value:
                continue
            key = normalize_label(raw_label)
            if not key:
                continue
            existing = fields.get(key)
            if existing is None:
                fields[key] = raw_value
            elif isinstance(existing, list):
                if raw_value not in existing:
                    existing.append(raw_value)
            elif raw_value != existing:
                fields[key] = [existing, raw_value]
    return fields


def _value_for_keys(fields: dict, keys: List[str]) -> Optional[str]:
    for key in keys:
        value = fields.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            joined = " ".join(v for v in value if v)
            if joined:
                return joined
        else:
            if str(value).strip():
                return str(value).strip()
    return None


def _extract_contacts(fields: dict, text: str) -> List[dict]:
    contacts: List[dict] = []
    email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    phone_pattern = r"\+?\d[\d\s().-]{6,}"
    for key, value in fields.items():
        if "contact" in key or "phone" in key or "email" in key:
            val_text = " ".join(value) if isinstance(value, list) else str(value)
            contact = {"label": key, "raw": val_text}
            email_match = re.search(email_pattern, val_text)
            phone_match = re.search(phone_pattern, val_text)
            if email_match:
                contact["email"] = email_match.group(0)
            if phone_match:
                contact["phone"] = phone_match.group(0)
            contacts.append(contact)
    for email in sorted(set(re.findall(email_pattern, text))):
        contacts.append({"label": "email", "email": email})
    for phone in sorted(set(re.findall(phone_pattern, text))):
        contacts.append({"label": "phone", "phone": phone})
    return contacts


def _extract_associated_files(soup: Any) -> List[dict]:
    files: List[dict] = []
    for table in soup.find_all("table"):
        headers = [h.get_text(" ", strip=True).lower() for h in table.find_all("th")]
        header_text = " ".join(headers)
        if "file" not in header_text and "attachment" not in header_text:
            continue
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            files.append(
                {
                    "file_name": cells[0] if len(cells) > 0 else None,
                    "size": cells[1] if len(cells) > 1 else None,
                    "distinction": cells[2] if len(cells) > 2 else None,
                    "description": cells[3] if len(cells) > 3 else None,
                }
            )
    return files


def extract_ticket_fields(html: str) -> dict:
    try:
        from bs4 import BeautifulSoup as bs4
    except Exception as exc:
        raise RuntimeError("BeautifulSoup (bs4) is required for HTML parsing. Install with `pip install beautifulsoup4`.") from exc
    soup = bs4(html, "html.parser")
    fields = extract_label_value_pairs(soup)
    raw_text = soup.get_text(" ", strip=True)
    full_text = " ".join(raw_text.split())

    company_value = _value_for_keys(fields, ["company", "company_name", "customer", "company_handle"])
    company_name = None
    company_code = None
    if company_value:
        match = re.match(r"^(.*?)(?:\(([^)]+)\))?$", company_value)
        if match:
            company_name = match.group(1).strip() if match.group(1) else company_value
            company_code = match.group(2).strip() if match.group(2) else None
        else:
            company_name = company_value

    subject = _value_for_keys(fields, ["subject", "issue", "ticket_subject"])
    status = _value_for_keys(fields, ["status", "ticket_status"])
    ticket_type = _value_for_keys(fields, ["type", "ticket_type"])
    circuit_id = _value_for_keys(fields, ["circuit_id", "circuit"])
    external_id = _value_for_keys(fields, ["external_id", "external_ticket_id", "external"])
    born_updated = _value_for_keys(fields, ["born_updated", "born_updated_line", "born_updated_date", "born_updated_time"])
    if not born_updated:
        match = re.search(r"born/updated\s*[:\s]*([^\n]+)", raw_text, flags=re.IGNORECASE)
        if match:
            born_updated = match.group(1).strip()

    contacts = _extract_contacts(fields, full_text)
    associated_files = _extract_associated_files(soup)

    return {
        "company_name": company_name,
        "company_code": company_code,
        "subject": subject,
        "status": status,
        "type": ticket_type,
        "circuit_id": circuit_id,
        "external_id": external_id,
        "born_updated": born_updated,
        "address": _value_for_keys(fields, ["address", "service_address", "location"]),
        "access_hours": _value_for_keys(fields, ["access_hours", "access", "access_hours"]),
        "dispatch": _value_for_keys(fields, ["dispatch", "dispatch_info"]),
        "region": _value_for_keys(fields, ["region", "market"]),
        "work_involved": _value_for_keys(fields, ["work_involved", "work", "work_details"]),
        "quick_links": _value_for_keys(fields, ["quick_links", "quick_link", "links"]),
        "contacts": contacts,
        "associated_files": associated_files,
        "full_page_text": full_text,
        "fields": fields,
    }
