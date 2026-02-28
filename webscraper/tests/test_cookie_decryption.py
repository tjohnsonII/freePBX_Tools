"""Test Utility: Cookie Decryption Verification.

This script verifies that the chrome_cookie_export helper can
successfully decrypt cookies from the local machine.
"""

from __future__ import annotations

import json
import os

from webscraper.auth.chrome_cookie_export import export_cookies


def verify_decryption(target_domain: str = "secure.123.net") -> None:
    print(f"--- Starting Decryption Test for {target_domain} ---")

    try:
        print(f"[1/3] Attempting to export cookies for {target_domain}...")
        json_path = export_cookies(domain=target_domain, browser="chrome")

        if os.path.exists(json_path):
            print(f"SUCCESS: Cookie file generated at: {json_path}")
        else:
            print(f"FAILURE: File was not created at {json_path}")
            return

        print("[2/3] Validating JSON structure...")
        with open(json_path, "r", encoding="utf-8") as handle:
            cookies = json.load(handle)

        if not isinstance(cookies, list):
            print("FAILURE: JSON root is not a list.")
            return

        print(f"Found {len(cookies)} cookies for {target_domain}.")

        if cookies:
            sample = cookies[0]
            required_keys = {"name", "value", "domain", "path", "secure", "expires"}
            missing = required_keys - set(sample.keys())

            if not missing:
                print(f"[3/3] Structure check passed. Sample cookie: {sample['name']}")
                print("\nTEST PASSED: Decryption and export logic are functional.")
            else:
                print(f"FAILURE: Missing keys in JSON objects: {missing}")
        else:
            print("NOTE: No cookies found for this domain. Login to the domain in Chrome and try again.")

    except RuntimeError as exc:
        print(f"PLATFORM ERROR: {exc}")
    except Exception as exc:  # pragma: no cover - local utility script
        print(f"UNEXPECTED ERROR: {exc}")


if __name__ == "__main__":
    verify_decryption()
