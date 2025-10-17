123NET FreePBX Tools

A suite of helper scripts for documenting and troubleshooting FreePBX / Asterisk systems.

⚡ Quick Reference
Command	Purpose	Output Location
freepbx-callflows	Interactive menu: snapshot, diagrams, TC status, diagnostics	/home/123net/callflows/
freepbx-dump	Take a JSON snapshot of FreePBX DB	freepbx_dump.json
freepbx-render	Render call-flow diagrams from last snapshot	callflow_<DID>.svg
freepbx-tc-status	Show Time Condition override state + last feature code use	Console output
freepbx-module-analyzer	Analyze all FreePBX modules and their configurations	Console output / JSON
freepbx-module-status	Quick FreePBX module status overview (enabled/disabled)	Console output
freepbx-diagnostic	Full system + Asterisk diagnostic	full_diagnostic_<timestamp>.txt
freepbx-version-check	Compare FreePBX/Asterisk versions to policy	Console output
asterisk-full-diagnostic.sh	Same as freepbx-diagnostic (legacy)	Same as above
📈 Features

Call-Flow Generator – renders inbound routes, IVRs, time conditions, queues, etc. into .svg diagrams.

Snapshot Utility – exports FreePBX config to normalized JSON.

Time Condition Status Tool – shows overrides + last feature code dial from CDRs.

Module Analyzer – comprehensive analysis of all FreePBX modules and their configurations.

Full Diagnostics – collects system and PBX state into text report.

Version Checker – validates PBX against policy.

123NET FreePBX Tools

A suite of helper scripts for documenting and troubleshooting FreePBX / Asterisk systems.

This toolkit provides:

📈 Call-Flow Generator
Extracts inbound routes, time conditions, IVRs, queues, ring groups, and more from the FreePBX database, then renders them into clean Graphviz diagrams (.svg).

📦 Snapshot Utility
Exports a normalized JSON snapshot of FreePBX configuration for offline review and consistency across versions.

🩺 Full Diagnostic Script
Collects system, Asterisk, and FreePBX runtime data into a text report.

📊 Time Condition Status Tool
Shows the current override state of each Time Condition and the last time its feature code (*xxx) was dialed (from CDRs).

📦 Module Analyzer
Comprehensive analysis of all FreePBX modules, their status, versions, and configurations. Evaluates core components like extensions, trunks, queues, and provides detailed configuration insights.

✅ Version Checker
Verifies Asterisk and FreePBX major versions against a local version policy.

🚀 Installation

Copy the freepbx-tools directory to your FreePBX server.

**Quick Setup:**
```bash
# 🚀 Ultimate lazy one-liner (avoids the chmod chicken-and-egg problem):
bash bootstrap.sh

# Or the traditional approach:
chmod +x make_executable.sh && ./make_executable.sh

# Or do it all manually:
chmod +x *.sh bin/*.sh *.py bin/*.py

# Then install
sudo ./install.sh
```

**Even Lazier One-Liner:**
```bash
# Copy-paste this single command to make everything executable:
chmod +x *.sh bin/*.sh *.py bin/*.py 2>/dev/null && echo "✅ Ready for installation: sudo ./install.sh"
```

**Typical Deployment Workflow:**
1. Develop/modify on Windows using VS Code
2. Copy to FreePBX server: `scp -r freepbx-tools/ user@freepbx-server:/tmp/`
3. SSH to server: `ssh user@freepbx-server`
4. Navigate: `cd /tmp/freepbx-tools/`
5. Make executable: `./make_executable.sh`
6. Install: `sudo ./install.sh`


This will:

Install dependencies (python3, jq, graphviz/dot, mysql/mariadb client).

Normalize scripts (shebangs, CRLF line endings, exec bits).

Place all tools under:

/usr/local/123net/freepbx-tools/


Create symlinks in:

/usr/local/bin/


Create the output directory for diagrams/reports:

/home/123net/callflows/

🔑 Key Commands
Interactive Call-Flow Menu
freepbx-callflows


From the menu you can:

Refresh DB snapshot

Show inventory (counts + DID list)

Generate call-flow for selected DID(s)

Generate call-flows for all DIDs

Generate call-flows for all DIDs (skip “OPEN” labels)

Show Time Condition status (+ last feature code use)

Run full Asterisk diagnostic

Quit

Outputs are saved in /home/123net/callflows/.

Non-Interactive Helpers

Take a fresh FreePBX DB snapshot

freepbx-dump


→ Creates freepbx_dump.json in /home/123net/callflows/.

Render diagrams from the last dump

freepbx-render


→ Produces callflow_<DID>.svg files in /home/123net/callflows/.

Run diagnostics

freepbx-diagnostic


or

asterisk-full-diagnostic.sh


→ Generates full_diagnostic_<timestamp>.txt.

*Check Time Condition overrides & last code use

freepbx-tc-status


→ Displays a table of all Time Conditions, showing:

ID, name, and mode (Time Group / Calendar)

Dialable feature code (e.g., *271)

Current override state (MATCHED/UNMATCHED/No Override)

Last time the feature code was dialed (from CDRs)

Check versions

freepbx-version-check


→ Compares current FreePBX & Asterisk major versions against the local policy file.

📂 Outputs

Call-Flows:
/home/123net/callflows/callflow_<DID>.svg

Diagnostics:
/home/123net/callflows/full_diagnostic_<timestamp>.txt

Snapshot:
/home/123net/callflows/freepbx_dump.json

SVGs can be opened in any browser or converted:

dot -Tpdf callflow_2696729277.svg -o callflow_2696729277.pdf

⚙️ Requirements

FreePBX host (CentOS/Sangoma 7+, Debian/Ubuntu, or equivalent)

Python 3.6+ (installer patches text=True for <3.7 automatically)

Graphviz (dot)

jq

MySQL/MariaDB client

Read access to FreePBX DB (via /etc/freepbx.conf or DB creds)

🧩 Example Workflow

Run the menu:

freepbx-callflows


Choose option 4 to generate call-flows for all DIDs.

View results:

ls /home/123net/callflows/callflow_*.svg


Run diagnostics:

freepbx-diagnostic


Check time condition states:

freepbx-tc-status

🛠 Troubleshooting

Exec format error:
Ensure scripts have UNIX line endings:

dos2unix /usr/local/123net/freepbx-tools/bin/*.sh


Python errors mentioning text=True:
Re-run the installer to auto-patch for Python <3.7.

No outputs found:
Check /home/123net/callflows/ for generated files.