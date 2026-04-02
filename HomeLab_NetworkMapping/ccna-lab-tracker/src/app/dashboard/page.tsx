"use client";

import { useMemo } from "react";
import ProgressBar from "@/components/ProgressBar";
import { loadPlan } from "@/lib/plan-storage";
import { getPlanProgress } from "@/lib/plan-utils";

export default function DashboardPage() {
  const stats = useMemo(() => getPlanProgress(loadPlan()), []);

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-3xl font-bold">Dashboard</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-gray-700 rounded-lg p-4">
            <h2 className="font-semibold mb-2">Total Days</h2>
            <p>{stats.total}</p>
          </div>

          <div className="border border-gray-700 rounded-lg p-4">
            <h2 className="font-semibold mb-2">Completed</h2>
            <p>{stats.done}</p>
          </div>

          <div className="border border-gray-700 rounded-lg p-4">
            <h2 className="font-semibold mb-2">In Progress</h2>
            <p>{stats.inProgress}</p>
          </div>

          <div className="border border-gray-700 rounded-lg p-4">
            <h2 className="font-semibold mb-2">Blocked</h2>
            <p>{stats.blocked}</p>
          </div>
        </div>

        <div className="border border-gray-700 rounded-lg p-4">
          <h2 className="font-semibold mb-3">Overall Progress</h2>
          <ProgressBar value={stats.percent} />
          <p className="mt-3">{stats.percent}% complete</p>
        </div>
      </div>
    </main>
  );
}