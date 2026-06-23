# Polycom / Yealink / Mikrotik Config Generator

React + Vite web app for generating configuration code for Polycom/Yealink phones, Mikrotik routers, and switches — plus bulk FreePBX import/export tools.

Served as a **static site** by Apache on the server. No backend required at runtime.

---

## Quick Start (Server)

The app is built and served automatically by `FULL_START.sh`. To rebuild manually:

```bash
cd /var/www/freePBX_Tools/PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main
npm ci
npm run build
# dist/ is served by Apache
```

## Quick Start (Local Dev — Windows)

```powershell
Push-Location "E:\DevTools\freepbx-tools\PolycomYealinkMikrotikSwitchConfig-main\PolycomYealinkMikrotikSwitchConfig-main"
npm.cmd install
npm.cmd run dev
```

Open **<http://localhost:3002>** in your browser.

Port 3002 is hardcoded in `vite.config.ts` (`strictPort: true`) to avoid conflicts with other apps in the suite.

The Vite dev server proxies all `/api` requests to the freepbx-deploy-backend on **<http://127.0.0.1:8002>**. Start the backend first if you need any API-backed tabs (Phone Config Generator, Config Audit, Diagnostics).

---

## Tabs

| Tab | Key | Description |
| --- | --- | --- |
| Phone Configs | `phone` | Form-based config generator for Polycom/Yealink models; generates extension, IP, label, and feature key blocks |
| Expansion Modules | `expansion` | Graphical preview and config for Yealink/Polycom sidecar/expansion modules |
| Full Config | `fullconfig` | Full device config view |
| Reference | `reference` | Legend for Polycom and Yealink config keys and feature settings |
| Diagnostics | `diagnostics` | Connect to a FreePBX server, run diagnostic tools, view call-flow graphs and terminal output |
| copyUserExtensions | `copyusers` | CSV-driven user/extension import table; exports populate FBPX fields |
| FBPX Import | `fbpx` | FBPX provisioning data import/export (CSV) |
| VPBX Import | `vpbx` | VPBX site and device data import/export (CSV) |
| Stretto Import | `streeto` | Stretto device data import/export (CSV) |
| DIDs | `dids` | DID routing table import/export (15-column CSV: cidnum, extension, destination, etc.) |
| Phone Config Generator | `phonegen` | API-backed generator — pulls live device configs from the scraper backend and generates Yealink/Polycom config blocks with BLF, park lines, and speed dials |
| Config Audit | `audit` | Audits live device configs from the backend against expected values (SIP server, time zone, etc.) |
| Mikrotik Templates | `mikrotik` | Editable Mikrotik router config templates (OTT, On-Net, Standalone ATA, 5009 Bridge/Passthrough) |
| Switch Templates | `switch` | Editable switch config templates (8-port and 24-port) |
| Order Tracker | `ordertracker` | Hosted order tracker — per-customer checklist spreadsheet with CSV import/export |

---

## API dependency (backend-connected tabs)

The **Phone Config Generator**, **Config Audit**, and **Diagnostics** tabs call the freepbx-deploy-backend. Set `VITE_SCRAPER_BASE` if the backend is not on the default port:

```powershell
$env:VITE_SCRAPER_BASE = 'http://localhost:8788'
npm.cmd run dev
```

The Vite proxy (`/api → http://127.0.0.1:8002`) handles all other API calls automatically in dev.

---

## Project structure

```text
src/
├── App.tsx                        # Tab router and top-level state
├── App.css                        # Global styles, CSS variables
├── main.tsx                       # React entry point
├── data/
│   ├── importStore.ts             # Row types, field lists, empty row factories,
│   │                              #   localStorage helpers, CSV export, cross-tab population
│   ├── modelRules.ts              # Phone model definitions and rules
│   └── phoneTemplates.ts          # Config block generators (BLF, park, speed dial)
├── tabs/
│   ├── ImportTable.tsx            # Shared react-data-grid table component
│   ├── ImportTable.module.css     # Shared table CSS (RDG theme, dark mode, resize)
│   ├── PhoneConfigGeneratorTab.tsx  # API-backed phone config generator
│   ├── ConfigAuditTab.tsx         # Live config audit
│   ├── DiagnosticsTab.tsx         # Diagnostics + call-flow graph + terminal
│   ├── ExpansionModuleTab.tsx     # Expansion module preview
│   ├── MikrotikTab.tsx            # Mikrotik template tab
│   ├── FbpxImportTab.tsx          # FBPX CSV import/export
│   ├── VpbxImportTab.tsx          # VPBX CSV import/export
│   ├── CopyUserExtensionsTab.tsx  # User/extension import
│   ├── DidsTab.tsx                # DID routing import/export
│   ├── CallFlowGraph.tsx          # ReactFlow call-flow diagram
│   └── TerminalPanel.tsx          # xterm.js terminal panel
├── MikrotikDynamicTemplate.tsx    # Mikrotik editable template component
├── Switch8DynamicTemplate.tsx     # 8-port switch template component
├── Switch24DynamicTemplate.tsx    # 24-port switch template component
├── SwitchDynamicTemplate.tsx      # Generic switch template component
├── StrettoImportExportTab.tsx     # Stretto CSV import/export tab
└── HostedOrderTrackerTab.tsx      # Order tracker tab
```

### ImportTable — Key Design Decisions

`ImportTable.tsx` is the shared grid component used by all import tabs.

- **ResizeObserver** measures the outer container width and computes proportional pixel column widths (wide fields = 2× weight, normal = 1×, delete button = 0.38×). Falls back to minimum widths with horizontal scroll on narrow screens.
- **rowClass prop** (not CSS nth-child) applies alternating row colors — required for virtual scrolling to work correctly.
- **Always-visible dropdowns** use `renderCell` (not `renderEditCell`) so selects are always visible without entering edit mode. `editable: false` prevents the text editor from opening on those cells.
- **Drag-to-resize** uses CSS `resize: vertical; overflow: hidden` on the wrapper div with DataGrid `height: 100%`. Default height shows 20 rows.
- **Dark mode** via `[data-theme="dark"]` attribute on root, with CSS variable overrides for all RDG colors.

---

## Development

```powershell
npm.cmd install        # Install dependencies
npm.cmd run dev        # Start dev server (<http://localhost:3002>)
npm.cmd run build      # Type-check and build for production
npm.cmd run preview    # Preview production build
npm.cmd run lint       # Run ESLint
```

---

## Build Notes

`FULL_START.sh` tracks source changes with an MD5 hash stored in `.src_hash`. It only rebuilds if source changed or `.src_hash` is missing.

Force rebuild:

```bash
rm PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/.src_hash
sudo ./FULL_START.sh
```

The built `dist/` is served by Apache as a static site. No node process runs in production.

---

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for guidelines. Key conventions:

- New tab → create `src/tabs/MyTab.tsx`, register in the `TABS` array in `App.tsx`
- Shared UI → `src/` root or a new `src/components/` file
- Shared config logic → `src/data/`
- Use TypeScript, Prettier, and ESLint before submitting a PR

---

## License

MIT
