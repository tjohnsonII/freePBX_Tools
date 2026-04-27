# Hosted Config Generator

React/Vite web app for managing telecom provisioning workflows. Deployed at [polycom.123hostedtools.com](https://polycom.123hostedtools.com).

This app lives in the **`client` branch** of `freePBX_Tools`. The backend server code is in the **`Server` branch**.

---

## Quick Start

```powershell
npm install
npm run dev
```

Dev server: <http://localhost:3002>

---

## Environment Variables

Create `.env.local` in this directory:

```env
# webscraper_manager FastAPI server (Server branch)
VITE_MANAGER_BASE=http://localhost:8000

# Ticket / VPBX scraper API
VITE_SCRAPER_BASE=http://localhost:8788
```

The app works fully offline — live-load buttons show **● Offline** and disable themselves when the server is unreachable.

---

## Tabs

### Config Generators (standalone — no server required)

| Tab | Key | Purpose |
| --- | --- | ------- |
| Phone Configs | `phone` | Form-based generator for Polycom / Yealink models; extension, IP, label, feature key blocks |
| Expansion Modules | `expansion` | Graphical preview and config for Yealink / Polycom sidecar / expansion modules |
| Full Config | `fullconfig` | Full device config view |
| Mikrotik Templates | `mikrotik` | Editable Mikrotik config templates (OTT, On-Net, Standalone ATA, 5009 Bridge/Passthrough) |
| Switch Templates | `switch` | Editable switch config templates (8-port and 24-port) |
| Reference | `reference` | Legend for Polycom and Yealink config keys and feature settings |

### API-backed (require `VITE_SCRAPER_BASE` server)

| Tab | Key | Purpose |
| --- | --- | ------- |
| Phone Config Generator | `phonegen` | Pulls live device configs from backend; generates Yealink/Polycom blocks with BLF, park, speed dials |
| Config Audit | `audit` | Audits live device configs against expected values (SIP server, time zone, etc.) |
| Diagnostics | `diagnostics` | SSH into a FreePBX server, run diagnostic tools, view call-flow graphs and terminal output |

### Import / Export Workflows (standalone CSV)

| Tab | Key | Purpose |
| --- | --- | ------- |
| FBPX Import | `fbpx` | FreePBX extension bulk import / export (CSV) |
| VPBX Import | `vpbx` | VPBX device bulk import / export — optionally pulls live from `VITE_SCRAPER_BASE` |
| Stretto Import | `streeto` | Stretto device import / export (CSV) |
| DIDs | `dids` | DID routing table import / export (15-column CSV) |
| Copy User Extensions | `copyusers` | CSV-driven user/extension import; exports populate FreePBX fields |

### Intermedia Ascend (Import / Export)

Column names in all three tabs match Ascend's import CSV exactly — no remapping needed.

| Tab | Key | Ascend CSV fields |
| --- | --- | ----------------- |
| Phone Input | `intermedia_phone` | Phone Number, Location, Type, Description, Assigned To, Caller ID, E911 Address |
| User Input | `intermedia_user` | First Name, Last Name, Email, Extension, Direct Number, Caller ID, Department, Title, Location, Seat Type, Voicemail PIN, Call Recording |
| Device Input | `intermedia_device` | MAC Address, Model, Assigned User, Extension, Location, Template, Line 1–Line 6 |

Each tab has **Clean** actions: phone tabs normalize to E.164 (`+1XXXXXXXXXX`), device tab normalizes MACs to `XX:XX:XX:XX:XX:XX`.

### Order Tracking

| Tab | Key | Purpose |
| --- | --- | ------- |
| Hosted Order Tracker | `ordertracker` | Transposed spreadsheet — fields as rows, customers as columns. **Load from 123NET Orders** fetches `VITE_MANAGER_BASE/api/orders?pm=tjohnson` and auto-populates CUSTOMER ABBREV, CUSTOMER NAME, INSTALL DATE, ORDER ID, PROJECT MANAGER, LOCATION. |

---

## Project Structure

```text
src/
├── App.tsx                           # Tab routing, theme toggle
├── data/
│   └── importStore.ts                # Shared types, field arrays, empty row factories,
│                                     #   localStorage helpers, clean utilities
├── tabs/
│   ├── ImportTable.tsx               # Shared react-data-grid table (all import tabs)
│   ├── ImportTable.module.css
│   ├── PhoneConfigGeneratorTab.tsx   # API-backed phone config generator
│   ├── ConfigAuditTab.tsx            # Live config audit
│   ├── DiagnosticsTab.tsx            # Diagnostics + call-flow graph + terminal
│   ├── ExpansionModuleTab.tsx        # Expansion module graphical preview
│   ├── MikrotikTab.tsx               # Mikrotik template tab
│   ├── FbpxImportTab.tsx             # FBPX CSV import/export
│   ├── VpbxImportTab.tsx             # VPBX CSV import/export
│   ├── CopyUserExtensionsTab.tsx     # User/extension import
│   ├── DidsTab.tsx                   # DID routing import/export
│   ├── IntermediaPhoneTab.tsx        # Ascend phone number import
│   ├── IntermediaUserTab.tsx         # Ascend user import
│   ├── IntermediaDeviceTab.tsx       # Ascend device import
│   ├── CallFlowGraph.tsx             # ReactFlow call-flow diagram
│   └── TerminalPanel.tsx             # xterm.js terminal panel
├── HostedOrderTrackerTab.tsx         # Order tracker with 123NET live load
├── HostedOrderTrackerTab.module.css
├── StrettoImportExportTab.tsx        # Stretto CSV import/export
├── MikrotikDynamicTemplate.tsx       # Mikrotik editable template
├── Switch8DynamicTemplate.tsx        # 8-port switch template
├── Switch24DynamicTemplate.tsx       # 24-port switch template
└── SwitchDynamicTemplate.tsx         # Generic switch template
```

---

## localStorage Keys

Each tab persists its data independently:

| Key | Tab |
| --- | --- |
| `import_store_fpbx` | FBPX Import |
| `import_store_vpbx` | VPBX Import |
| `import_store_stretto` | Stretto Import |
| `import_store_intermedia_phone` | Phone Input |
| `import_store_intermedia_user` | User Input |
| `import_store_intermedia_device` | Device Input |

---

## Build

```bash
npm run build     # static output → dist/
npm run preview   # preview production build
```

Set `VITE_MANAGER_BASE` and `VITE_SCRAPER_BASE` in `.env.production` (or your CI environment) before building — Vite inlines them at compile time.
