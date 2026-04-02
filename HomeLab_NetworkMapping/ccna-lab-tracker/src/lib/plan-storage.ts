import { plan as seedPlan } from "@/data/plan";
import type { DayPlan, DayStatus } from "@/lib/types";

const STORAGE_KEY = "ccna-plan:v1";

// ── Validation ───────────────────────────────────────────────────────────────

function isValidStatus(value: unknown): value is DayStatus {
  return (
    value === "not_started" ||
    value === "in_progress" ||
    value === "done" ||
    value === "blocked"
  );
}

// ── Normalize ────────────────────────────────────────────────────────────────
// Merges saved progress rows (from DB or localStorage) with the canonical
// seed plan so structural changes (new days, renamed titles) are always safe.

export function normalizePlan(raw: unknown): DayPlan[] {
  if (!Array.isArray(raw)) return seedPlan;

  const savedMap = new Map<number, { status: unknown; notes: unknown }>();
  for (const item of raw) {
    if (typeof item === "object" && item !== null && typeof (item as Record<string, unknown>).day === "number") {
      const r = item as Record<string, unknown>;
      savedMap.set(r.day as number, { status: r.status, notes: r.notes });
    }
  }

  return seedPlan.map((seed) => {
    const saved = savedMap.get(seed.day);
    return {
      ...seed,
      status: saved && isValidStatus(saved.status) ? saved.status : seed.status,
      notes: saved && typeof saved.notes === "string" ? saved.notes : seed.notes,
    };
  });
}

// ── API (server-backed SQLite) ───────────────────────────────────────────────

export async function loadPlanFromDb(): Promise<DayPlan[]> {
  try {
    const res = await fetch("/api/plan");
    if (!res.ok) return seedPlan;
    const rows = await res.json();
    return normalizePlan(rows);
  } catch {
    return seedPlan;
  }
}

export async function savePlanToDb(plan: DayPlan[]): Promise<void> {
  try {
    await fetch("/api/plan", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        plan.map(({ day, status, notes }) => ({ day, status, notes }))
      ),
    });
  } catch {
    // fail silently — data is still in React state
  }
}

// ── localStorage (fallback cache) ────────────────────────────────────────────

export function loadPlan(): DayPlan[] {
  if (typeof window === "undefined") return seedPlan;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return seedPlan;
    return normalizePlan(JSON.parse(raw));
  } catch {
    return seedPlan;
  }
}

export function savePlan(plan: DayPlan[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(plan));
  } catch {
    // quota exceeded — fail silently
  }
}

export function resetPlan(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}