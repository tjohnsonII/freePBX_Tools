# 123NET FreePBX Tools

A collection of helper scripts for documenting and troubleshooting FreePBX / Asterisk systems.

This package provides:

- **Call-flow generator**: Extracts routes, time conditions, queues, etc. from the FreePBX database and renders them into Graphviz diagrams (`.svg`).
- **Snapshot utilities**: Exports a JSON snapshot of FreePBX configuration for offline use.
- **Full diagnostic script**: Collects system and Asterisk status into a plain-text report.
- **Version checker**: Verifies Asterisk and FreePBX major versions against a local policy.

---

## Installation

Clone or copy the files to a host, then run:

```bash
sudo ./install.sh

This will:

Install dependencies (Python 3, jq, Graphviz dot, MySQL client).

Normalize scripts (fix shebangs, CRLF, exec bits).

Place the toolset under /usr/local/123net/freepbx-tools/.

Create symlinks in /usr/local/bin/ for easy access.

Create /home/123net/callflows/ for diagram output.

Key Commands

After install, the following entrypoints are available globally:

Interactive Call-Flow Menu
freepbx-callflows


Options include:

Refresh DB snapshot

Show inventory (counts + DID list)

Generate call-flow for selected DID(s)

Generate call-flows for all DIDs

Generate call-flows for all DIDs (skipping “OPEN” labels)

Run full Asterisk diagnostic

Quit

Output diagrams are saved under:

/home/123net/callflows/

Non-interactive Helpers

Take a fresh FreePBX DB snapshot

freepbx-dump


→ Writes freepbx_dump.json in /home/123net/callflows/.

Render diagrams from the last dump

freepbx-render


→ Creates callflow_<DID>.svg files in /home/123net/callflows/.

Run diagnostics

freepbx-diagnostic


or

asterisk-full-diagnostic.sh


→ Produces full_diagnostic_<timestamp>.txt with system, Asterisk, and CDR details.

Check versions

freepbx-version-check

Requirements

CentOS / Sangoma 7+ or Debian/Ubuntu host running FreePBX

Python 3 (3.6+; installer patches Python <3.7 automatically)

Graphviz (dot)

jq

MySQL/MariaDB client

Access to /etc/freepbx.conf and the Asterisk DB (usually as freepbxuser)

Outputs

Call-flows: callflow_<DID>.svg diagrams under /home/123net/callflows/

Diagnostic reports: full_diagnostic_<timestamp>.txt under the same directory

Snapshot: freepbx_dump.json

You can open SVGs in any browser or convert to PNG/PDF with dot -Tpng or dot -Tpdf.

Example Workflow

Run the menu:

freepbx-callflows


Select 4 to generate call-flows for all DIDs.

Retrieve diagrams:

ls /home/123net/callflows/callflow_*.svg


Run full diagnostics:

freepbx-diagnostic


(Optional) Convert diagrams to PDF:

dot -Tpdf /home/123net/callflows/callflow_2696729277.svg \
    -o /home/123net/callflows/callflow_2696729277.pdf

Troubleshooting

If you see Exec format error, ensure scripts have UNIX line endings:

dos2unix /usr/local/123net/freepbx-tools/bin/*.sh


If Python errors mention text=True, run the installer again to patch for Python <3.7.

Check /home/123net/callflows/ for outputs.