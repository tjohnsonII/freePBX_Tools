"""
MikroTik OTT Template Filler
---------------------------------

Purpose:
- Fill a RouterOS OTT template (OTT.txt) with customer-specific values for
    company handle, address, WAN gateway, subnet mask, and optionally a chosen
    usable IP. Produces a CLI-ready config by stripping the header paragraph and
    converting inline markers to proper RouterOS comments.

Variable Map:
- BASE_DIR: Absolute directory where this script resides; used for stable paths.
- TEMPLATE_DEFAULT: Default absolute path to `OTT.txt` next to this script.
- TEMPLATE_PATH (runtime): The template file provided via `--template` or default.
- OUT_PATH (runtime): Output file path provided via `--out` or default.
- handle: Company handle string (e.g., "90F").
- customer_addr: Customer/site address string (e.g., "41060 HAYES").
- gateway: WAN gateway IPv4 address (e.g., "96.70.96.254").
- subnet_mask: IPv4 subnet mask (e.g., "255.255.255.248").
- usable_hint: Optional usable IPv4 address to prefer over computed first usable.
- network: Computed network address derived from gateway+mask (e.g., "96.70.96.248").
- first_usable: Computed first usable host in the network (e.g., "96.70.96.249").
- prefix: CIDR prefix length derived from mask (e.g., 29 for 255.255.255.248).
- content: Entire template text after robust read and transformations.

Function Map:
- mask_to_prefix(mask: str) -> int
    - Convert dotted-decimal subnet mask to CIDR prefix length using ipaddress.

- compute_network_and_hosts(gateway: str, subnet_mask: str) -> (network, first_usable, last_usable, prefix)
    - Build a network from gateway/mask; return network address, first and last usable hosts, and prefix.

- fill_template(template_path, out_path, handle, customer_addr, gateway, subnet_mask, usable_hint=None) -> None
    - Robustly read the template (handles encoding), strip header paragraph,
        perform targeted substitutions (identity/SNMP, gateway, MGMT list with comment,
        ether10 address/network, placeholder /29 occurrences), ensure output directory,
        and write the result.

- main():
    - CLI entrypoint; parses arguments and invokes fill_template, printing a success line.
"""

import argparse
import ipaddress
import os
import re
from typing import Tuple, Optional

BASE_DIR = os.path.dirname(__file__)  # Stable absolute path to this script's folder
TEMPLATE_DEFAULT = os.path.join(BASE_DIR, "OTT.txt")


def mask_to_prefix(mask: str) -> int:
    """Convert dotted-decimal subnet mask to CIDR prefix length.

    Example: "255.255.255.248" -> 29
    """
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except Exception as e:
        raise ValueError(f"Invalid subnet mask '{mask}': {e}")


def compute_network_and_hosts(gateway: str, subnet_mask: str) -> Tuple[str, str, str, int]:
    """Compute network address and first/last usable hosts from gateway + mask.

    - strict=False allows gateway anywhere within the network range.
    """
    prefix = mask_to_prefix(subnet_mask)
    net = ipaddress.IPv4Network(f"{gateway}/{prefix}", strict=False)
    first_usable = str(net.network_address + 1)
    last_usable = str(net.broadcast_address - 1)
    return str(net.network_address), first_usable, last_usable, prefix


def fill_template(template_path: str, out_path: str, handle: str, customer_addr: str, gateway: str, subnet_mask: str, usable_hint: Optional[str] = None) -> None:
    """Fill the MikroTik OTT template with provided details and write output.

    Steps:
    1. Compute network and usable hosts from gateway/mask.
    2. Robustly read template (UTF-8, fallback to binary decode), with diagnostics.
    3. Strip header paragraph (keep content starting at first '/' command).
    4. Replace identity and SNMP location strings.
    5. Replace default route gateway.
    6. Replace MGMT list block with CIDR and add RouterOS comment.
    7. Replace ether10 assignment with usable/prefix and network.
    8. Replace remaining placeholder occurrences.
    9. Ensure output directory; write normalized newlines.
    """
    network, first_usable, last_usable, prefix = compute_network_and_hosts(gateway, subnet_mask)
    # If a usable IP hint is provided, prefer it; otherwise use last usable
    usable_ip = usable_hint or last_usable

    # Read template robustly; handle non-UTF encodings, and emit diagnostics
    content = ""
    # Diagnostics
    try:
        exists = os.path.exists(template_path)
        size = os.path.getsize(template_path) if exists else -1
        print(f"[DEBUG] Template path: {template_path} exists={exists} size={size}")
    except Exception as e:
        print(f"[DEBUG] Template stat error: {e}")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        content = ""
    if not content:
        try:
            # Fallback: read binary and decode permissively
            with open(template_path, "rb") as fb:
                raw = fb.read()
            # Try utf-8 with replacement; then latin-1
            try:
                content = raw.decode("utf-8", errors="replace")
            except Exception:
                content = raw.decode("latin-1", errors="replace")
            snippet = content[:200]
            print(f"[DEBUG] Read fallback content snippet: {snippet!r}")
        except Exception as e:
            raise RuntimeError(f"Failed to read template '{template_path}': {e}")
    if not content or content.strip() == "":
        raise RuntimeError(f"Template read returned empty content: {template_path}")

    # Replace identity and SNMP location (best-effort; keep city/zip if unknown)
    # RouterOS supports inline comment parameters like comment="..."
    content = content.replace("HANDLE-CUSTOMERADDRESS", f"{handle}-{customer_addr}")
    content = content.replace("CUSTOMER NAME, CUSTOMER ADDRESS, CITY MI ZIP", f"{handle}, {customer_addr}")

    # Diagnostics: placeholders present before replacement steps
    try:
        print("[DEBUG] Placeholders present before replacement:", {
            'gateway_placeholder': 'gateway=XXX.XXX.XXX.XXX' in content,
            'mgmt_placeholder': 'add address=XXX.XXX.XXX.XXX/29 list=MGMT' in content,
            'ether10_placeholder': 'add address=XXX.XXX.XXX.XXX/29 interface=ether10 network=XXX.XXX.XXX.XXX' in content,
            'identity_placeholder': 'HANDLE-CUSTOMERADDRESS' in content,
        })
    except Exception:
        pass

    # Remove leading informational paragraph/comments before first config section
    # Drop everything before the first line that starts with a slash command (e.g., /interface)
    lines = content.splitlines()
    cut_index = 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith('/'):
            cut_index = i
            break
    if cut_index > 0:
        content = "\n".join(lines[cut_index:])

    # Replace gateway in /ip route (avoid backref ambiguity)
    content = re.sub(r"gateway=XXX\.XXX\.XXX\.XXX", f"gateway={gateway}", content)

    # Replace MGMT off-net block (expects CIDR /29) and convert inline marker to proper comment
    # Handle both with or without the marker text
    content = re.sub(
        r"add address=XXX\.XXX\.XXX\.XXX/\d+\s+list=MGMT(?:\s*<--Customer Off-Net IP)?",
        f"add address={network}/{prefix} list=MGMT comment=\"Customer Off-Net IP\"",
        content,
    )

    # Replace ether10 assignment line with first usable and network
    content = re.sub(
        r"add address=XXX\.XXX\.XXX\.XXX/\d+\s+interface=ether10\s+network=XXX\.XXX\.XXX\.XXX",
        f"add address={usable_ip}/{prefix} interface=ether10 network={network}",
        content,
    )

    # Also update any plain /29 occurrences tied to placeholders
    content = content.replace("XXX.XXX.XXX.XXX/29", f"{network}/{prefix}")
    content = content.replace("network=XXX.XXX.XXX.XXX", f"network={network}")

    # Fallback: if any placeholders remain, perform broad replacements to ensure output is usable
    # Replace any remaining generic placeholder IPs with the computed network
    if "XXX.XXX.XXX.XXX" in content:
        content = content.replace("XXX.XXX.XXX.XXX", network)

    # Ensure ether10 line uses the chosen usable host
    content = re.sub(
        r"(add address=)(\d+\.\d+\.\d+\.\d+/\d+)(\s+interface=ether10)",
        rf"\g<1>{usable_ip}/{prefix}\g<3>",
        content,
    )

    # Ensure MGMT off-net block reflects the network/prefix and preserves any comment text
    content = re.sub(
        r"(add address=)(\d+\.\d+\.\d+\.\d+/\d+)(\s+list=MGMT(?:[^\n]*)?)",
        rf"\g<1>{network}/{prefix}\g<3>",
        content,
    )

    # Do not broadly replace 'gateway=' values; only placeholder replacements above should apply.

    # Diagnostics: check whether replacements took effect
    try:
        print("[DEBUG] Replacement check:", {
            'has_gateway_final': f"gateway={gateway}" in content,
            'has_mgmt_final': f"add address={network}/{prefix} list=MGMT" in content,
            'has_ether10_final': f"add address={usable_ip}/{prefix} interface=ether10 network={network}" in content,
            'has_identity_final': f"{handle}-{customer_addr}" in content,
        })
    except Exception:
        pass

    # Final line-by-line fallback to catch any variations not matched above
    lines = content.splitlines()
    fixed_lines = []
    for ln in lines:
        # ether10 address assignment
        if "interface=ether10" in ln and "address=XXX.XXX.XXX.XXX" in ln:
            ln = re.sub(r"address=XXX\.XXX\.XXX\.XXX/\d+", f"address={usable_ip}/{prefix}", ln)
            ln = re.sub(r"network=XXX\.XXX\.XXX\.XXX", f"network={network}", ln)
        # MGMT off-net list placeholder
        elif "list=MGMT" in ln and "XXX.XXX.XXX.XXX" in ln:
            ln = re.sub(r"address=XXX\.XXX\.XXX\.XXX/\d+", f"address={network}/{prefix}", ln)
            # normalize comment style
            ln = re.sub(r"<--Customer Off-Net IP", "", ln).strip()
            if "comment=" not in ln:
                ln += f" comment=\"Customer Off-Net IP\""
        # default route gateway placeholder line
        elif ln.strip().startswith("add distance=1") and "gateway=XXX.XXX.XXX.XXX" in ln:
            ln = re.sub(r"gateway=XXX\.XXX\.XXX\.XXX", f"gateway={gateway}", ln)
        fixed_lines.append(ln)
    content = "\n".join(fixed_lines)

    # Save filled file
    # Ensure directory exists and write with normalized newlines
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def main():
    """CLI entrypoint for the template filler."""
    parser = argparse.ArgumentParser(description="Fill MikroTik OTT template with customer details")
    parser.add_argument("--handle", required=True, help="Company handle (e.g., 90F)")
    parser.add_argument("--address", required=True, help="Customer address (e.g., 41060 HAYES)")
    parser.add_argument("--gateway", required=True, help="Gateway IPv4 (e.g., 96.70.96.254)")
    parser.add_argument("--subnet", required=True, help="Subnet mask (e.g., 255.255.255.248)")
    parser.add_argument("--usable", help="Optional usable IP hint (defaults to first usable)")
    parser.add_argument("--template", default=TEMPLATE_DEFAULT, help="Path to OTT template")
    parser.add_argument("--out", default=os.path.join(BASE_DIR, "OTT_filled.txt"), help="Output file path")
    args = parser.parse_args()

    fill_template(
        template_path=args.template,
        out_path=args.out,
        handle=args.handle,
        customer_addr=args.address,
        gateway=args.gateway,
        subnet_mask=args.subnet,
        usable_hint=args.usable,
    )
    print(f"Filled template written to: {args.out}")


if __name__ == "__main__":
    main()
