# MikroTik Template Filler

This folder contains a helper script to fill the MikroTik OTT template (`OTT.txt`) with customer-specific details like handle, address, gateway, and subnet.

## Files
- `OTT.txt`: Base template to customize.
- `fill_mikrotik_template.py`: Script that fills placeholders.
- `90F_Tik.txt` (example): Output generated for a specific customer.

## Requirements
- Python 3.8+
- Run from the repository root or provide absolute paths.

## Quick Start
1. Open PowerShell in the repo root: `C:\Users\tjohnson\freepbx-tools`.
2. Run with defaults (template next to the script):
   ```powershell
   python mikrotik/fill_mikrotik_template.py --handle 90F --address "41060 HAYES" --gateway 96.70.96.254 --subnet 255.255.255.248 --out mikrotik/90F_Tik.txt
   ```
3. If you see a template read error, pass the full template path:
   ```powershell
   python mikrotik/fill_mikrotik_template.py --template C:\Users\tjohnson\freepbx-tools\mikrotik\OTT.txt --handle 90F --address "41060 HAYES" --gateway 96.70.96.254 --subnet 255.255.255.248 --out mikrotik\90F_Tik.txt
   ```
4. To use a specific usable IP (instead of first usable):
   ```powershell
   python mikrotik/fill_mikrotik_template.py --template C:\Users\tjohnson\freepbx-tools\mikrotik\OTT.txt --handle 90F --address "41060 HAYES" --gateway 96.70.96.254 --subnet 255.255.255.248 --usable 96.70.96.253 --out mikrotik\90F_Tik.txt
   ```

## What Gets Updated
- Ether10 assignment:
  - `add address=<usable>/<prefix> interface=ether10 network=<network>`
- MGMT off-net entry:
  - `add address=<network>/<prefix> list=MGMT`
- Default route:
  - `add distance=1 gateway=<gateway>`
- Identity and SNMP location strings:
  - Replace `HANDLE-CUSTOMERADDRESS` and customer location text.

## Notes
- Subnet mask converts to CIDR prefix automatically (e.g., `255.255.255.248` → `/29`).
- First usable is computed from the gateway + subnet unless `--usable` is provided.
- Output directory is created if missing.
- The script prints debug diagnostics if the template appears empty (size, path, content snippet).

## Troubleshooting
- Verify the template exists and is non-empty:
  ```powershell
  Get-Item C:\Users\tjohnson\freepbx-tools\mikrotik\OTT.txt | Format-List Length,FullName
  ```
- If running from a different working directory, always pass `--template` with an absolute path.

## Example
Resulting line for ether10 with first usable in `/29`:
```
add address=96.70.96.249/29 interface=ether10 network=96.70.96.248
```

Second example using a specific usable IP (instead of first usable):
```powershell
python mikrotik/fill_mikrotik_template.py --template C:\Users\tjohnson\freepbx-tools\mikrotik\OTT.txt --handle 90F --address "41060 HAYES" --gateway 96.70.96.254 --subnet 255.255.255.248 --usable 96.70.96.253 --out mikrotik\90F_Tik.txt
```
This sets the ether10 line to:
```
add address=96.70.96.253/29 interface=ether10 network=96.70.96.248
```
