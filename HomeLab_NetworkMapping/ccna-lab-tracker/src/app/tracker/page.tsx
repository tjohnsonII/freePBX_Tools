"use client";

import { useEffect, useMemo, useState } from "react";
import WeekSection from "@/components/WeekSection";
import { loadPlan, savePlan } from "@/lib/plan-storage";
import { groupPlanByWeek } from "@/lib/plan-utils";
import type { DayPlan, DayStatus } from "@/lib/types";

export default function TrackerPage() {
  const [plan, setPlan] = useState<DayPlan[]>(() => loadPlan());

  useEffect(() => {
    savePlan(plan);
  }, [plan]);

  const grouped = useMemo(() => groupPlanByWeek(plan), [plan]);

  const updateStatus = (day: number, status: DayStatus) => {
    setPlan((current) =>
      current.map((item) =>
        item.day === day ? { ...item, status } : item
      )
    );
  };

  const updateNotes = (day: number, notes: string) => {
    setPlan((current) =>
      current.map((item) =>
        item.day === day ? { ...item, notes } : item
      )
    );
  };

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">CCNA Lab Tracker</h1>
        <p className="text-gray-400 mb-8">Total Days Loaded: {plan.length}</p>

        <div className="space-y-8">
          {grouped.map(([week, days]) => (
            <WeekSection
              key={week}
              week={week}
              days={days}
              onStatusChange={updateStatus}
              onNotesChange={updateNotes}
            />
          ))}
        </div>
      </div>
    </main>
  );
}