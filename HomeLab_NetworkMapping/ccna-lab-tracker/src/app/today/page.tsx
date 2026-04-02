"use client";

import { useEffect, useMemo, useState } from "react";
import DayCard from "@/components/DayCard";
import { loadPlanFromDb, savePlanToDb } from "@/lib/plan-storage";
import type { DayPlan, DayStatus } from "@/lib/types";

export default function TodayPage() {
  const [plan, setPlan] = useState<DayPlan[]>([]);

  useEffect(() => {
    loadPlanFromDb().then(setPlan);
  }, []);

  useEffect(() => {
    if (plan.length > 0) savePlanToDb(plan);
  }, [plan]);

  const todayItem = useMemo(() => {
    return plan.find((item) => item.status !== "done") ?? plan[0];
  }, [plan]);

  if (plan.length === 0) {
    return (
      <main className="min-h-screen p-6">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold">Today</h1>
          <p className="text-gray-400 mt-4">Loading...</p>
        </div>
      </main>
    );
  }

  if (!todayItem) {
    return (
      <main className="min-h-screen p-6">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold">Today</h1>
          <p className="text-gray-400 mt-4">No plan items found.</p>
        </div>
      </main>
    );
  }

  const updateStatus = (status: DayStatus) => {
    setPlan((current) =>
      current.map((item) =>
        item.day === todayItem.day ? { ...item, status } : item
      )
    );
  };

  const updateNotes = (notes: string) => {
    setPlan((current) =>
      current.map((item) =>
        item.day === todayItem.day ? { ...item, notes } : item
      )
    );
  };

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-4xl mx-auto space-y-4">
        <h1 className="text-3xl font-bold">Today</h1>
        <p className="text-gray-400">Current focus: Day {todayItem.day}</p>

        <DayCard
          item={todayItem}
          onStatusChange={updateStatus}
          onNotesChange={updateNotes}
        />
      </div>
    </main>
  );
}