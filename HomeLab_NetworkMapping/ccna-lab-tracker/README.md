# CCNA Lab Tracker

Next.js + TypeScript app for tracking CCNA homelab study progress.

## Project layout

```text
ccna-lab-tracker/
├─ public/
├─ src/
│  ├─ app/
│  │  ├─ tracker/
│  │  │  └─ page.tsx
│  │  ├─ globals.css
│  │  ├─ layout.tsx
│  │  └─ page.tsx
│  └─ data/
│     └─ plan.ts
├─ next.config.ts
├─ package.json
└─ tsconfig.json
```

## Scripts

- `npm run dev` — start dev server on `http://localhost:3011`
- `npm run build` — production build
- `npm run start` — run production server on port `3011`
- `npm run lint` — ESLint via Next.js config
- `npm run typecheck` — TypeScript check (`tsc --noEmit`)

## Notes

- This project uses the App Router under `src/app`.
- Import alias `@/*` resolves to `src/*`.
- Turbopack root is pinned to this app directory in `next.config.ts` for monorepo-style stability.
