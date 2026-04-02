"use client";

import { useEffect, useState } from "react";
import { plan as initialPlan, DayPlan } from "@/data/plan";

const STORAGE_KEY = "ccna-plan";

function normalizePlan(candidate: unknown): DayPlan[] {
  if (!Array.isArray(candidate)) {
    return initialPlan;
  }

  return candidate
    .filter(
      (item): item is Partial<DayPlan> & Pick<DayPlan, "day" | "title" | "tasks"> =>
        typeof item === "object" &&
        item !== null &&
        typeof item.day === "number" &&
        typeof item.title === "string" &&
        Array.isArray(item.tasks) &&
        item.tasks.every((task: unknown): task is string => typeof task === "string")
    )
    .map((item, index) => ({
      day: item.day,
      title: item.title,
      tasks: item.tasks,
      status: item.status ?? initialPlan[index]?.status ?? "not_started",
      notes: item.notes ?? initialPlan[index]?.notes ?? "",
    }));
}

function loadPlan(): DayPlan[] {
  if (typeof window === "undefined") {
    return initialPlan;
  }

  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (!saved) {
    return initialPlan;
  }

  try {
    return normalizePlan(JSON.parse(saved));
  } catch {
    return initialPlan;
  }
}

export default function TrackerPage() {
  const [plan, setPlan] = useState<DayPlan[]>(loadPlan);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(plan));
  }, [plan]);

  const updateStatus = (index: number, status: DayPlan["status"]) => {
    const updated = [...plan];
    updated[index] = { ...updated[index], status };
    setPlan(updated);
  };

  const updateNotes = (index: number, notes: string) => {
    const updated = [...plan];
    updated[index] = { ...updated[index], notes };
    setPlan(updated);
  };

  return (
    <main className="min-h-screen bg-black text-white p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">CCNA Lab Tracker</h1>

        <div className="mb-6 text-sm text-gray-300">
          Total Days Loaded: {plan.length}
        </div>

        <div className="space-y-4">
          {plan.map((item, index) => (
            <div key={item.day} className="border border-gray-700 rounded-lg p-4">
              <h2 className="text-xl font-semibold mb-2">
                Day {item.day}: {item.title}
              </h2>

              <ul className="list-disc ml-6 mb-3">
                {item.tasks.map((task, i) => (
                  <li key={i}>{task}</li>
                ))}
              </ul>

              <div className="flex flex-wrap gap-2 mb-3">
                <button
                  onClick={() => updateStatus(index, "not_started")}
                  className="px-3 py-1 rounded bg-gray-700"
                >
                  Not Started
                </button>
                <button
                  onClick={() => updateStatus(index, "in_progress")}
                  className="px-3 py-1 rounded bg-blue-700"
                >
                  In Progress
                </button>
                <button
                  onClick={() => updateStatus(index, "done")}
                  className="px-3 py-1 rounded bg-green-700"
                >
                  Done
                </button>
                <button
                  onClick={() => updateStatus(index, "blocked")}
                  className="px-3 py-1 rounded bg-red-700"
                >
                  Blocked
                </button>
              </div>

              <div className="mb-3">
                <span className="font-medium">Status:</span> {item.status}
              </div>

              <textarea
                value={item.notes}
                onChange={(e) => updateNotes(index, e.target.value)}
                placeholder="Add notes for this day..."
                className="w-full min-h-24 rounded bg-gray-900 border border-gray-700 p-3"
              />
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}