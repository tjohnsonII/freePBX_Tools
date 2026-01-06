"""
Cisco 3750X 8-Port Standard Template Filler
------------------------------------------

Purpose:
- Fill the 3750X standard template with company-specific values:
  - Company handle for hostname
  - Local credentials (username/enable secret)
  - Asset tag in banner

Inputs:
- --template: Path to the base template (default: next to this script)
- --handle: Company handle (e.g., 90F)
- --newpass: Password to set for both `username i123 secret` and `enable secret`
- --asset: Asset tag string (e.g., 18969)
- --out: Output file path

Behavior:
- Performs targeted string replacements; preserves all other content unchanged.
"""

import argparse
import os
import re


BASE_DIR = os.path.dirname(__file__)
DEFAULT_TEMPLATE = os.path.join(BASE_DIR, "3750x Standard Template 8 port.txt")


def sanitize_address(addr: str) -> str:
    """Sanitize address for hostname: remove spaces and non-alphanumerics."""
    return re.sub(r"[^A-Za-z0-9]", "", addr.replace(" ", ""))


def fill_template(template_path: str, out_path: str, handle: str, newpass: str, asset_tag: str, address: str | None = None) -> None:
    # Read template text
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

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
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser(description="Fill Cisco 3750X template with provided details")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="Path to the 3750x template text file")
    parser.add_argument("--handle", required=True, help="Company handle (e.g., 90F)")
    parser.add_argument("--newpass", required=True, help="Password for username i123 secret and enable secret")
    parser.add_argument("--address", help="Site address to include in hostname (e.g., 41060 HAYES)")
    parser.add_argument("--asset", required=True, help="Asset tag (e.g., 18969)")
    parser.add_argument("--out", default=os.path.join(BASE_DIR, "3750x_filled.txt"), help="Output file path")
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
