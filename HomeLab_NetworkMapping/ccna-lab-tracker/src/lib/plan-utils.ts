import type { DayPlan } from "@/lib/types";

export function groupPlanByWeek(plan: DayPlan[]): [number, DayPlan[]][] {
  const map = new Map<number, DayPlan[]>();

  for (const item of plan) {
    if (!map.has(item.week)) {
      map.set(item.week, []);
    }
    map.get(item.week)!.push(item);
  }

  return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
}

export function getPlanProgress(plan: DayPlan[]) {
  const total = plan.length;
  const done = plan.filter((item) => item.status === "done").length;
  const inProgress = plan.filter((item) => item.status === "in_progress").length;
  const blocked = plan.filter((item) => item.status === "blocked").length;
  const notStarted = plan.filter((item) => item.status === "not_started").length;
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);

  return {
    total,
    done,
    inProgress,
    blocked,
    notStarted,
    percent,
  };
}