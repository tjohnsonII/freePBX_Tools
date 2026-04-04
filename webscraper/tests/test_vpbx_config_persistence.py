from pathlib import Path

from webscraper.ticket_api import db


def test_device_config_upsert_does_not_overwrite_non_empty_with_blank(tmp_path: Path) -> None:
    db_path = str(tmp_path / "tickets.sqlite")
    db.ensure_indexes(db_path)

    db.upsert_vpbx_device_configs(
        db_path,
        [
            {
                "device_id": "d1",
                "vpbx_id": "c1",
                "handle": "abc",
                "bulk_config": "line1=value1",
            }
        ],
        "2026-01-01T00:00:00Z",
    )

    db.upsert_vpbx_device_configs(
        db_path,
        [
            {
                "device_id": "d1",
                "vpbx_id": "c1",
                "handle": "abc",
                "bulk_config": "",
            }
        ],
        "2026-01-01T00:01:00Z",
    )

    rows = db.list_vpbx_device_configs(db_path, handle="ABC")
    assert rows[0]["bulk_config"] == "line1=value1"


def test_site_config_upsert_and_blank_protection(tmp_path: Path) -> None:
    db_path = str(tmp_path / "tickets.sqlite")
    db.ensure_indexes(db_path)

    db.upsert_vpbx_site_configs(
        db_path,
        [
            {
                "company_id": "9001",
                "handle": "xyz",
                "company_name": "XYZ Corp",
                "detail_url": "https://example/vpbx?id=9001",
                "site_config_raw": "<site>ok</site>",
            }
        ],
        "2026-01-01T00:00:00Z",
    )

    db.upsert_vpbx_site_configs(
        db_path,
        [
            {
                "company_id": "9001",
                "handle": "xyz",
                "site_config_raw": "",
            }
        ],
        "2026-01-01T00:01:00Z",
    )

    rows = db.list_vpbx_site_configs(db_path, handle="XYZ")
    assert len(rows) == 1
    assert rows[0]["site_config_raw"] == "<site>ok</site>"
    assert rows[0]["config_length"] == len("<site>ok</site>")
