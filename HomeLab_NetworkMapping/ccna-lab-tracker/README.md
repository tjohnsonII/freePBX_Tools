# CCNA Lab Tracker

Next.js 15 app for tracking a 90-day CCNA homelab study plan. Persists progress to a local SQLite database via `better-sqlite3` — no external database required.

---

## Quick Start

```bash
cd HomeLab_NetworkMapping/ccna-lab-tracker
npm install
npm run dev
```

Opens at **<http://localhost:3011>**.

---

## Pages

| Route | Purpose |
| ----- | ------- |
| `/` | Home — intro and navigation links |
| `/tracker` | Full 90-day lab plan — topic list, completion toggles |
| `/today` | Today's scheduled labs based on the current day number |
| `/dashboard` | Progress summary — completion rate, streaks, topic breakdown |

---

## Data Storage

Uses `better-sqlite3` directly in Next.js API route handlers (server-side only, no external DB process). The database file is created automatically at first run.

| Table | Purpose |
| ----- | ------- |
| `labs` | Lab topic definitions — title, day, category, estimated time |
| `progress` | Per-day completion records — lab ID, completed flag, date |

---

## API Routes

All routes live under `src/app/api/` and run server-side:

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/labs` | Fetch all lab definitions |
| `GET` | `/api/progress` | Fetch completion records |
| `POST` | `/api/progress` | Mark a lab complete or incomplete |

---

## Project Structure

```text
src/app/
  page.tsx              # Home
  layout.tsx            # Root layout and global styles
  tracker/page.tsx      # 90-day tracker with completion toggles
  today/page.tsx        # Today's lab assignments
  dashboard/page.tsx    # Progress dashboard
  api/                  # Server-side SQLite API handlers
  globals.css
```

---

## Build

```bash
npm run build
npm run start           # production server on port 3011
npm run typecheck       # TypeScript check without building
npm run lint            # ESLint
```
