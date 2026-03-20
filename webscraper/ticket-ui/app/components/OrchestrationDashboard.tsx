"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";

type JobState = "queued" | "running" | "completed" | "failed";
type StepState = "idle" | "detecting_browser" | "seeding_auth" | "validating_auth" | "scraping" | "persisting" | "exposing_results" | "error";

type Job = {
  job_id: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  current_state: JobState;
  current_step: StepState;
  records_found: number;
  records_written: number;
  error_message?: string | null;
};

type SystemStatus = {
  backend_health: string;
  browser_status: string;
  auth_status: string;
  current_job?: Job | null;
  last_successful_scrape?: string | null;
  db_counts: { tickets: number; handles: number };
  last_error?: string | null;
  state: StepState;
};

type StepResult = { ok: boolean; state: StepState; detail: string; data?: Record<string, unknown> };

export default function OrchestrationDashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [steps, setSteps] = useState<StepResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reload = async () => {
    try {
      const [system, jobList] = await Promise.all([
        apiGet<SystemStatus>("/api/system/status"),
        apiGet<{ items: Job[] }>("/api/jobs"),
      ]);
      setStatus(system);
      setJobs(jobList.items || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    reload().catch(() => undefined);
    const timer = setInterval(() => reload().catch(() => undefined), 3000);
    return () => clearInterval(timer);
  }, []);

  const runAction = async (label: string, path: string, body: Record<string, unknown> = {}) => {
    setBusy(label);
    setError(null);
    try {
      await apiPost(path, body);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const runE2E = async () => {
    setBusy("e2e");
    setError(null);
    try {
      const result = await apiPost<{ steps: StepResult[] }>("/api/scrape/run-e2e", {});
      setSteps(Array.isArray(result.steps) ? result.steps : []);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section style={{ border: "1px solid #333", borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <h2>Orchestration Dashboard</h2>
      {error ? <p style={{ color: "#ff6b6b" }}>{error}</p> : null}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 8 }}>
        <div><strong>Backend</strong><div>{status?.backend_health ?? "unknown"}</div></div>
        <div><strong>Browser</strong><div>{status?.browser_status ?? "unknown"}</div></div>
        <div><strong>Auth</strong><div>{status?.auth_status ?? "unknown"}</div></div>
        <div><strong>Current state</strong><div>{status?.state ?? "idle"}</div></div>
        <div><strong>DB counts</strong><div>tickets={status?.db_counts?.tickets ?? 0}, handles={status?.db_counts?.handles ?? 0}</div></div>
        <div><strong>Last error</strong><div>{status?.last_error || "none"}</div></div>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
        <button onClick={() => runAction("detect", "/api/browser/detect", { browser: "chrome", cdp_port: 9222 })} disabled={!!busy}>Detect Browser</button>
        <button onClick={() => runAction("seed", "/api/auth/seed")} disabled={!!busy}>Seed Auth</button>
        <button onClick={() => runAction("validate", "/api/auth/validate")} disabled={!!busy}>Validate Auth</button>
        <button onClick={() => runAction("scrape", "/api/scrape/run")} disabled={!!busy}>Run Scrape</button>
        <button onClick={runE2E} disabled={!!busy}>Run End-to-End</button>
      </div>
      {!!steps.length && (
        <div style={{ marginTop: 10 }}>
          <strong>E2E steps</strong>
          <ul>
            {steps.map((step, idx) => (
              <li key={`${step.state}-${idx}`}>{step.state}: {step.detail} ({step.ok ? "ok" : "failed"})</li>
            ))}
          </ul>
        </div>
      )}
      <div style={{ marginTop: 10 }}>
        <strong>Recent jobs</strong>
        <ul>
          {jobs.slice(0, 5).map((job) => (
            <li key={job.job_id}>{job.job_id} · {job.current_state} · step={job.current_step} · found={job.records_found} · written={job.records_written}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
