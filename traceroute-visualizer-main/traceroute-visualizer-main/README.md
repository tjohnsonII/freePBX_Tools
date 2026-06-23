# Traceroute Visualizer

Next.js 15 app that runs traceroutes and displays the path as an interactive Leaflet map. Supports multi-probe comparisons, scenario-based policy detection, and evidence export for NOC tickets.

---

## Quick Start

```bash
cd traceroute-visualizer-main/traceroute-visualizer-main
npm install
npm run dev
```

Opens at **<http://localhost:3000>** (Next.js default, Turbopack enabled).

---

## What It Does

- Enter a destination hostname or IP — the app runs a traceroute via `POST /api/traceroute`
- Hops are plotted on an interactive Leaflet map with IP ownership annotations
- **Multi-probe**: run from multiple vantage points and compare merged hop views
- **Scenario picker**: select a predefined policy scenario (OTT, On-Net DIA, etc.) — the app applies policy detection rules to classify the result
- **Findings panel**: detected anomalies, routing assertions, and policy violations
- **Evidence export**: copy or download findings formatted for NOC ticket notes

---

## API Routes

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/api/traceroute` | Run traceroute to `{target}`, returns hop list |

The traceroute executes server-side. Source address is `192.168.50.1` by default (local router gateway).

---

## Pages and Components

| File | Purpose |
| ---- | ------- |
| `app/page.tsx` | Entry point — hosts the TracerouteVisualizer client component |
| `app/traceroute_visualizer.tsx` | Main UI — target input, probe controls, results |
| `app/components/TraceMap.tsx` | Leaflet map (dynamic import, SSR disabled) |
| `app/components/ScenarioPicker.tsx` | Policy scenario selector |
| `app/components/FindingsPanel.tsx` | Findings and policy violation display |
| `app/components/EvidenceActions.tsx` | Copy / download evidence buttons |

---

## Key Utilities

| Module | Purpose |
| ------ | ------- |
| `utils/tracerouteClassification.ts` | Classify each hop (private, ISP, CDN, etc.) |
| `utils/tracerouteInsights.ts` | Analyse a full trace for patterns and anomalies |
| `utils/tracerouteComparison.ts` | Compare two traces hop-by-hop |
| `utils/multiProbe.ts` | Run and merge results from multiple probe sources |
| `utils/policyDetection.ts` | Apply scenario rules, derive findings, format ticket summaries |
| `utils/targetValidation.ts` | Validate hostname/IP before sending |
| `app/data/` | Static IP ownership lookup tables |

---

## Build

```bash
# Optional: rebuild IP ownership table from source data
npm run build:ownership

npm run build
npm run start
```

---

## Dependencies

| Package | Purpose |
| ------- | ------- |
| `leaflet` + `react-leaflet` | Interactive hop map |
| `lucide-react` | Icons |
| `@radix-ui/react-slot` | Headless UI primitives |
| `tailwindcss` | Styling |
| `xlsx` | Evidence export to spreadsheet |
