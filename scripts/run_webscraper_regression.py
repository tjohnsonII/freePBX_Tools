#!/usr/bin/env python3
"""Python regression runner for webscraper (PS1 alternative)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cmd(cmd: list[str], cwd: Path | None = None, label: str | None = None) -> None:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = label or "Command failed"
        print(f"FAIL: {message}")
        print(result.stdout)
        raise RuntimeError(message)


def pass_msg(message: str) -> None:
    print(f"PASS: {message}")


def main() -> int:
    try:
        print("Running argparse help checks...")
        run_cmd(
            [sys.executable, "-m", "webscraper.ultimate_scraper", "--help"],
            cwd=REPO_ROOT,
            label="webscraper.ultimate_scraper --help",
        )
        run_cmd(
            [sys.executable, str(REPO_ROOT / "webscraper" / "legacy" / "ticket_scraper.py"), "--help"],
            cwd=REPO_ROOT,
            label="webscraper/legacy/ticket_scraper.py --help",
        )
        pass_msg("Argparse help checks")

        with tempfile.TemporaryDirectory() as temp_root:
            temp_root_path = Path(temp_root)
            cookie_dir = temp_root_path / "cookies"
            cookie_dir.mkdir(parents=True, exist_ok=True)

            cookies_txt = cookie_dir / "cookies.txt"
            cookies_txt.write_text(
                "# Netscape HTTP Cookie File\n.123.net\tTRUE\t/\tFALSE\t0\tPHPSESSID\tDUMMY\n",
                encoding="ascii",
            )

            run_cmd(
                [sys.executable, str(REPO_ROOT / "webscraper" / "legacy" / "convert_cookies.py")],
                cwd=cookie_dir,
                label="convert_cookies.py",
            )

            cookies_json = cookie_dir / "cookies.json"
            if not cookies_json.exists():
                raise RuntimeError("convert_cookies.py did not create cookies.json")
            pass_msg("Cookie conversion test")

            selenium_dir = temp_root_path / "selenium"
            input_dir = selenium_dir / "input"
            output_dir = selenium_dir / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            fixture = {
                "ticket_details": [
                    {
                        "id": "123",
                        "subject": "Test",
                        "status": "Open",
                        "priority": "Low",
                        "created_date": "2024-01-01",
                        "messages": [],
                    }
                ]
            }
            fixture_path = input_dir / "scrape_results_TEST.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            run_cmd(
                [
                    sys.executable,
                    str(REPO_ROOT / "webscraper" / "legacy" / "selenium_to_kb.py"),
                    "--input-dir",
                    str(input_dir),
                    "--out-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                label="selenium_to_kb.py",
            )

            db_path = output_dir / "TEST_tickets.db"
            json_path = output_dir / "TEST_tickets.json"
            if not db_path.exists():
                raise RuntimeError("selenium_to_kb.py did not create TEST_tickets.db")
            if not json_path.exists():
                raise RuntimeError("selenium_to_kb.py did not create TEST_tickets.json")
            pass_msg("Selenium-to-KB parse-only test")

        pass_msg("All regression checks")
        return 0
    except Exception as exc:  # pragma: no cover - keep runner resilient
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
