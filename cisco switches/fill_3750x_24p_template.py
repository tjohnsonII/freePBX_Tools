"""
Cisco 3750X 24-Port Standard Template Filler
-------------------------------------------

Purpose:
- Fill the 3750X (24-port) standard template with site-specific values:
  - Company handle + site address in hostname
  - Local credentials (username/enable secret)
  - Asset tag in banner

Usage examples:
    PowerShell (Windows) using backtick line continuations:
        python "cisco switches/fill_3750x_24p_template.py" `
            --handle KPM `
            --address "1584 Clarendon" `
            --newpass "sdxczv@Y2023" `
            --asset 18971 `
            --out "cisco switches/3750x_24p_KPM.txt"

    Bash (Linux/macOS) using backslash line continuations:
        python "cisco switches/fill_3750x_24p_template.py" \
            --handle KPM \
            --address "1584 Clarendon" \
            --newpass "sdxczv@Y2023" \
            --asset 18971 \
            --out "cisco switches/3750x_24p_KPM.txt"
"""

import argparse
import os
import re


BASE_DIR = os.path.dirname(__file__) or "."
BASE_DIR = os.path.abspath(BASE_DIR)
DEFAULT_TEMPLATE = os.path.join(BASE_DIR, "3750X Standard Template 24 Port.txt")


def sanitize_address(addr: str) -> str:
    """Sanitize address for hostname: remove spaces and non-alphanumerics."""
    return re.sub(r"[^A-Za-z0-9]", "", addr.replace(" ", ""))


def fill_template(template_path: str, out_path: str, handle: str, newpass: str, asset_tag: str, address: str | None = None) -> None:
    # Diagnostics for template
    tpath = os.path.abspath(template_path)
    exists = os.path.exists(tpath)
    size = os.path.getsize(tpath) if exists else -1
    print(f"Template: {tpath} exists={exists} size={size}")

    # Read template text with encoding fallback
    content = ""
    if exists:
        try:
            with open(tpath, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(tpath, "r", encoding="latin-1") as f:
                content = f.read()
    if not content:
        print("Warning: Template content is empty. Aborting write.")
        # Still create an empty file only if explicitly requested, but here we abort to prevent confusion
        return

    # Hostname: replace HANDLE-ADDRESS-SW1 with <HANDLE>-<ADDRESS>-SW1 if provided, else <HANDLE>-SW1
    if address:
        addr_token = sanitize_address(address)
        hostname = f"hostname {handle}-{addr_token}-SW1"
    else:
        hostname = f"hostname {handle}-SW1"
    content = re.sub(r"hostname\s+HANDLE-ADDRESS-SW1", hostname, content)

    # Credentials: set username i123 secret and enable secret to newpass
    content = re.sub(r"username\s+i123\s+secret\s+\S+", f"username i123 secret {newpass}", content)
    content = re.sub(r"enable\s+secret\s+\S+", f"enable secret {newpass}", content)

    # Banner: replace ASSET TAG XXXX -> ASSET TAG <asset_tag>
    content = re.sub(r"ASSET TAG\s+XXXX", f"ASSET TAG {asset_tag}", content)

    # Ensure output directory exists and write result
    out_abs = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(out_abs, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"Wrote {len(content)} bytes to {out_abs}")


def main():
    parser = argparse.ArgumentParser(description="Fill Cisco 3750X 24-port template with provided details")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="Path to the 3750X 24-port template text file")
    parser.add_argument("--handle", required=True, help="Company handle (e.g., KPM)")
    parser.add_argument("--address", help="Site address to include in hostname (e.g., 1584 Clarendon)")
    parser.add_argument("--newpass", required=True, help="Password for username i123 secret and enable secret")
    parser.add_argument("--asset", required=True, help="Asset tag (e.g., 18971)")
    parser.add_argument("--out", default=os.path.join(BASE_DIR, "3750x_24p_filled.txt"), help="Output file path")
    args = parser.parse_args()

    fill_template(
        template_path=args.template,
        out_path=args.out,
        handle=args.handle,
        newpass=args.newpass,
        asset_tag=args.asset,
        address=args.address,
    )
    print(f"Filled template written to: {args.out}")


if __name__ == "__main__":
    main()
