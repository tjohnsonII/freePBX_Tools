#!/usr/bin/env python3
# Manual / integration script; not run by pytest.
"""Manually validate remote dashboard access over SSH."""

from __future__ import annotations

import os
import sys


def _load_credentials() -> tuple[str | None, str | None]:
    username = os.getenv("FREEPBX_USER")
    password = os.getenv("FREEPBX_PASSWORD")
    if username and password:
        return username, password

    try:
        from config import FREEPBX_PASSWORD, FREEPBX_USER  # type: ignore

        return FREEPBX_USER, FREEPBX_PASSWORD
    except Exception:
        return None, None


def main() -> int:
    try:
        import paramiko
    except ModuleNotFoundError:
        print("paramiko is required for dashboard_manual.py. Install it with: pip install paramiko")
        return 1

    host = os.getenv("FREEPBX_HOST", "69.39.69.102")
    username, password = _load_credentials()
    if not username or not password:
        print("Missing FreePBX credentials. Set FREEPBX_USER and FREEPBX_PASSWORD (or provide config.py).")
        return 1

    print(f"Testing dashboard on {host}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(host, username=username, password=password, timeout=10)
        _, stdout, stderr = ssh.exec_command('echo "" | freepbx-callflows 2>&1 | head -100', timeout=30)

        output = stdout.read().decode("utf-8")
        errors = stderr.read().decode("utf-8")

        print("\n" + "=" * 70)
        print("Dashboard Output:")
        print("=" * 70)
        print(output)

        if errors:
            print("\n" + "=" * 70)
            print("Errors:")
            print("=" * 70)
            print(errors)

        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    finally:
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())
