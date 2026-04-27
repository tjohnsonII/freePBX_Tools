# freePBX_Tools — `client` branch

This branch contains **only the client-side web app**: the Hosted Config Generator React/Vite application deployed at [polycom.123hostedtools.com](https://polycom.123hostedtools.com).

---

## Branch Structure

| Branch | Contents |
| ------ | -------- |
| `main` | Everything — source of truth for the full monorepo |
| `client` | **This branch** — React/Vite client app only (`PolycomYealinkMikrotikSwitchConfig-main/`) |
| `Server` | All server-side code — webscraper, manager API, deploy backend, HomeLab app, proxy configs, systemd, scripts |

The `client` branch is maintained separately so the React SPA can be cloned, run, and developed without pulling down the full server stack.

---

## App Overview

The Hosted Config Generator is a tabbed React UI for managing telecom provisioning workflows. It runs as a standalone SPA and optionally connects to the `webscraper_manager` FastAPI server (Server branch) for live data.

**Live URL:** <https://polycom.123hostedtools.com>

---

## Quick Start

```powershell
cd PolycomYealinkMikrotikSwitchConfig-main\PolycomYealinkMikrotikSwitchConfig-main
npm install
npm run dev
```

Dev server starts at <http://localhost:3002> (configured in `vite.config.ts`, `strictPort: true`).

---

## Environment Variables

Create a `.env.local` file in the app directory:

```env
# Base URL for the webscraper_manager FastAPI server (Server branch)
VITE_MANAGER_BASE=http://localhost:8000

# Base URL for the ticket/VPBX scraper API
VITE_SCRAPER_BASE=http://localhost:8788
```

Both default to `localhost` if not set — the app works offline, live-load buttons are simply disabled when the server is unreachable.

---

## Tabs

### Config Generators (standalone — no server required)

| Tab | Key | Purpose |
| --- | --- | ------- |
| Phone Configs | `phone` | Form-based config generator for Polycom / Yealink models; generates extension, IP, label, and feature key blocks |
| Expansion Modules | `expansion` | Graphical preview and config for Yealink / Polycom sidecar / expansion modules |
| Full Config | `fullconfig` | Full device config view |
| Mikrotik Templates | `mikrotik` | Editable Mikrotik router config templates (OTT, On-Net, Standalone ATA, 5009 Bridge/Passthrough) |
| Switch Templates | `switch` | Editable switch config templates (8-port and 24-port) |
| Reference | `reference` | Legend for Polycom and Yealink config keys and feature settings |

### API-backed (require `VITE_SCRAPER_BASE` server)

| Tab | Key | Purpose |
| --- | --- | ------- |
| Phone Config Generator | `phonegen` | Pulls live device configs from the scraper backend and generates Yealink/Polycom config blocks with BLF, park lines, and speed dials |
| Config Audit | `audit` | Audits live device configs against expected values (SIP server, time zone, etc.) |
| Diagnostics | `diagnostics` | Connect to a FreePBX server, run diagnostic tools, view call-flow graphs and terminal output |

### Import / Export Workflows (standalone CSV)

| Tab | Key | Purpose |
| --- | --- | ------- |
| FBPX Import | `fbpx` | FreePBX extension bulk import / export (CSV) |
| VPBX Import | `vpbx` | VPBX device bulk import / export — optionally pulls live from `VITE_SCRAPER_BASE` |
| Stretto Import | `streeto` | Stretto device import / export (CSV) |
| DIDs | `dids` | DID routing table import / export (15-column CSV) |
| Copy User Extensions | `copyusers` | CSV-driven user/extension import table; exports populate FreePBX fields |

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

## Server Connection

The app talks to two backend endpoints (both served from the `Server` branch):

| Env Var | Default | Used By |
| ------- | ------- | ------- |
| `VITE_MANAGER_BASE` | `http://localhost:8000` | Order Tracker — Load from 123NET Orders |
| `VITE_SCRAPER_BASE` | `http://localhost:8788` | VPBX Import — Load Devices, Config Audit, Phone Config Generator |

Status badges in each panel show **● Online / ● Offline** based on a connectivity probe at mount. Load buttons are disabled when the server is unreachable.

---

## Project Structure

```text
PolycomYealinkMikrotikSwitchConfig-main/
└── PolycomYealinkMikrotikSwitchConfig-main/
    ├── src/
    │   ├── App.tsx                           # Tab routing, theme toggle
    │   ├── data/
    │   │   └── importStore.ts                # Shared types, field arrays, localStorage helpers
    │   ├── tabs/
    │   │   ├── ImportTable.tsx               # Shared react-data-grid table (all import tabs)
    │   │   ├── ImportTable.module.css
    │   │   ├── PhoneConfigGeneratorTab.tsx   # API-backed phone config generator
    │   │   ├── ConfigAuditTab.tsx            # Live config audit
    │   │   ├── DiagnosticsTab.tsx            # Diagnostics + call-flow graph + terminal
    │   │   ├── ExpansionModuleTab.tsx        # Expansion module graphical preview
    │   │   ├── MikrotikTab.tsx               # Mikrotik template tab
    │   │   ├── FbpxImportTab.tsx             # FBPX CSV import/export
    │   │   ├── VpbxImportTab.tsx             # VPBX CSV import/export
    │   │   ├── CopyUserExtensionsTab.tsx     # User/extension import
    │   │   ├── DidsTab.tsx                   # DID routing import/export
    │   │   ├── IntermediaPhoneTab.tsx        # Ascend phone number import
    │   │   ├── IntermediaUserTab.tsx         # Ascend user import
    │   │   ├── IntermediaDeviceTab.tsx       # Ascend device import
    │   │   ├── CallFlowGraph.tsx             # ReactFlow call-flow diagram
    │   │   └── TerminalPanel.tsx             # xterm.js terminal panel
    │   ├── HostedOrderTrackerTab.tsx         # Order tracker with 123NET live load
    │   ├── HostedOrderTrackerTab.module.css
    │   ├── StrettoImportExportTab.tsx        # Stretto CSV import/export
    │   ├── MikrotikDynamicTemplate.tsx       # Mikrotik editable template
    │   ├── Switch8DynamicTemplate.tsx        # 8-port switch template
    │   ├── Switch24DynamicTemplate.tsx       # 24-port switch template
    │   └── SwitchDynamicTemplate.tsx         # Generic switch template
    ├── package.json
    └── vite.config.ts
```

---

## Build for Production

```bash
npm run build     # outputs to dist/
npm run preview   # preview the production build locally
```

The production build is a static SPA. Vite inlines `VITE_*` env vars at build time — set them in your CI/CD environment or `.env.production` before building.

---

## Server Branch

All backend code lives in the `Server` branch:

- `webscraper/` — Selenium scraper, cookie-based auth, SQLite storage
- `webscraper_manager/` — FastAPI server (`/api/orders`, `/api/vpbx/*`, `/api/tickets`)
- `freepbx-deploy-backend/` — FreePBX deploy API
- `manager-ui/` — Internal manager React UI
- `HomeLab/` — HomeLab web app
- `traceroute-visualizer-main/` — Traceroute visualizer
- `scripts/`, `systemd/`, `nginx/` — Deployment and proxy config

To run the full stack, switch to the `Server` branch and follow its README.
