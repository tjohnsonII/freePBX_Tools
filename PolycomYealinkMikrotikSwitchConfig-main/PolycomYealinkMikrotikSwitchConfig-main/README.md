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

## Quick Start (Local Dev)

```bash
cd PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main
npm install
npm run dev
# open http://localhost:3002
```

---

## Tabs

### Phone Configs
Generate device-specific config code for:
- **Polycom** — VVX 250, 350, 450, 500, 600, 601; expansion modules (EX5000 — 2 columns × 14 rows = 28 keys)
- **Yealink** — T46S, T48S, T54W, T57W, T58A, T31P, CP960; expansion modules

Enter extension, IP, display name, and feature key labels → app generates the config snippet.

### VPBX Import
Bulk import/export for Virtual PBX extensions. Features:
- react-data-grid with 200 default rows
- Always-visible inline dropdowns (tech, voicemail options, etc.)
- Smart CSV export — trims trailing empty rows
- Proportional column widths that fill the screen
- Drag-to-resize grip on the table corner
- Toolbar: Load from FPBX, Generate Secrets, Generate MACs, Clean MACs, populate fields

### FPBX Import
Bulk import/export for FreePBX extensions:
- Same react-data-grid setup as VPBX
- Toolbar: Populate from Copy Users, Fill Fields, Generate Secrets, Clean Caller IDs

### Stretto Import
Import/export for Stretto softphone provisioning. Populated from FPBX tab data.

### DIDs Import
Bulk DID import for FreePBX inbound routes.

### Copy User Extensions
Import user list from 123.net portal export. Source data for populating FPBX/VPBX/Stretto tabs.

### Mikrotik
Editable Mikrotik router config templates.

### Switch
8-port and 24-port switch config templates.

### Reference
Polycom and Yealink config field reference / legend.

---

## Data Persistence

All tab data is saved to `localStorage` automatically. Data survives page reloads but is browser-local. Export to CSV to save permanently.

---

## CSV Import / Export

Each import tab (VPBX, FPBX, Stretto, DIDs, Copy Users) supports:
- **Import:** drop or select a CSV file — parsed and loaded into the table
- **Export:** downloads a CSV with only rows that have data (trailing empty rows trimmed)

The export logic finds the last row with any non-empty field value and exports rows 1 through that row only. A table with 200 rows but only 5 filled exports a 5-row CSV.

---

## Tech Stack

| Package | Version | Purpose |
|---------|---------|---------|
| React | 19.x | UI library |
| TypeScript | 5.x | Type safety |
| Vite | 6.x | Build tool, dev server |
| react-data-grid | 7.0.0-beta.59 | Excel-like editable tables |
| papaparse | — | CSV parsing |

---

## Source Structure

```
src/
├── App.tsx                  Main app — tab router, theme toggle
├── App.css                  Global styles, CSS variables
├── data/
│   └── importStore.ts       Row types, field lists, empty row factories,
│                            localStorage helpers, CSV export, cross-tab population
├── tabs/
│   ├── ImportTable.tsx      Shared react-data-grid table component
│   ├── ImportTable.module.css   Shared table CSS (RDG theme, dark mode, resize)
│   ├── VpbxImportTab.tsx    VPBX tab
│   ├── VpbxImportTab.module.css
│   ├── FbpxImportTab.tsx    FPBX tab
│   ├── DidsTab.tsx          DIDs tab
│   └── CopyUserExtensionsTab.tsx  Copy Users tab
└── StrettoImportExportTab.tsx   Stretto tab
```

### ImportTable — Key Design Decisions

`ImportTable.tsx` is the shared grid component used by all import tabs.

- **ResizeObserver** measures the outer container width and computes proportional pixel column widths (wide fields = 2× weight, normal = 1×, delete button = 0.38×). Falls back to minimum widths with horizontal scroll on narrow screens.
- **rowClass prop** (not CSS nth-child) applies alternating row colors — required for virtual scrolling to work correctly.
- **Always-visible dropdowns** use `renderCell` (not `renderEditCell`) so selects are always visible without entering edit mode. `editable: false` prevents the text editor from opening on those cells.
- **Drag-to-resize** uses CSS `resize: vertical; overflow: hidden` on the wrapper div with DataGrid `height: 100%`. Default height shows 20 rows.
- **Dark mode** via `[data-theme="dark"]` attribute on root, with CSS variable overrides for all RDG colors.

---

## Build Notes

`FULL_START.sh` tracks source changes with an MD5 hash stored in `.src_hash`. It only rebuilds if source changed or `.src_hash` is missing.

Force rebuild:
```bash
rm PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/.src_hash
sudo ./FULL_START.sh
```

The built `dist/` is served by Apache as a static site. No node process runs in production.
