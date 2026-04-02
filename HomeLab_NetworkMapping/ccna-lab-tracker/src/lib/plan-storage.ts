import { plan as seedPlan } from "@/data/plan";
import type { DayPlan, DayStatus } from "@/lib/types";

const STORAGE_KEY = "ccna-plan:v1";

function isValidStatus(value: unknown): value is DayStatus {
  return (
    value === "not_started" ||
    value === "in_progress" ||
    value === "done" ||
    value === "blocked"
  );
}

function isValidPlanItem(value: unknown): value is DayPlan {
  if (!value || typeof value !== "object") return false;

  const item = value as Record<string, unknown>;

  return (
    typeof item.day === "number" &&
    typeof item.week === "number" &&
    typeof item.title === "string" &&
    Array.isArray(item.tasks) &&
    item.tasks.every((task) => typeof task === "string") &&
    isValidStatus(item.status) &&
    typeof item.notes === "string"
  );
}

export function normalizePlan(raw: unknown): DayPlan[] {
  if (!Array.isArray(raw)) return seedPlan;

  const saved = raw.filter(isValidPlanItem);

  if (saved.length === 0) return seedPlan;

  const savedMap = new Map<number, DayPlan>();
  for (const item of saved) {
    savedMap.set(item.day, item);
  }

  return seedPlan.map((seedItem) => {
    const savedItem = savedMap.get(seedItem.day);
    if (!savedItem) return seedItem;

    return {
      ...seedItem,
      status: savedItem.status,
      notes: savedItem.notes,
    };
  });
}

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

export function savePlan(plan: DayPlan[]) {
  if (typeof window === "undefined") return;

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(plan));
}

export function resetPlan() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}