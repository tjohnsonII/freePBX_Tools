"use client";

import { useEffect, useState } from "react";
import { plan as initialPlan, type DayPlan } from "../../data/plan";

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
    <main className="min-h-screen bg-black p-6 text-white">
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-6 text-3xl font-bold">CCNA Lab Tracker</h1>

        <div className="mb-6 text-sm text-gray-300">Total Days Loaded: {plan.length}</div>

        <div className="space-y-4">
          {plan.map((item, index) => (
            <div key={item.day} className="rounded-lg border border-gray-700 p-4">
              <h2 className="mb-2 text-xl font-semibold">
                Day {item.day}: {item.title}
              </h2>

              <ul className="mb-3 ml-6 list-disc">
                {item.tasks.map((task: string, i: number) => (
                  <li key={i}>{task}</li>
                ))}
              </ul>

              <div className="mb-3 flex flex-wrap gap-2">
                <button
                  onClick={() => updateStatus(index, "not_started")}
                  className="rounded bg-gray-700 px-3 py-1"
                >
                  Not Started
                </button>
                <button
                  onClick={() => updateStatus(index, "in_progress")}
                  className="rounded bg-blue-700 px-3 py-1"
                >
                  In Progress
                </button>
                <button
                  onClick={() => updateStatus(index, "done")}
                  className="rounded bg-green-700 px-3 py-1"
                >
                  Done
                </button>
                <button
                  onClick={() => updateStatus(index, "blocked")}
                  className="rounded bg-red-700 px-3 py-1"
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
                className="min-h-24 w-full rounded border border-gray-700 bg-gray-900 p-3"
              />
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
