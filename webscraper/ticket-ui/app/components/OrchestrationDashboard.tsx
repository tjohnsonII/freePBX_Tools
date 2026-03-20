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
  secure_tab_status?: string;
  session_status?: string;
  cookies_status?: string;
  validation_status?: string;
  probe_status?: string;
  detection_reason?: string | null;
  current_job?: Job | null;
  last_successful_scrape?: string | null;
  db_counts: { tickets: number; handles: number };
  last_error?: string | null;
  state: StepState;
};

type StepResult = { ok: boolean; state: StepState; detail: string; data?: Record<string, unknown> };
type SeleniumFallbackStart = { queued: boolean; job_id: string; handles_total: number; status: string };
type SeleniumFallbackJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  error_message?: string | null;
  result?: {
    status_message?: string;
    current_handle?: string | null;
    completed_handles?: number;
    total_handles?: number;
    ticket_count?: number;
    error?: string;
  } | null;
};

export default function OrchestrationDashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [steps, setSteps] = useState<StepResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [seleniumJob, setSeleniumJob] = useState<SeleniumFallbackJob | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [expandedJob, setExpandedJob] = useState<Job | null>(null);
  const [expandedJobError, setExpandedJobError] = useState<string | null>(null);

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

  const runSeleniumFallback = async () => {
    setBusy("selenium-fallback");
    setError(null);
    try {
      const start = await apiPost<SeleniumFallbackStart>("/api/scrape/selenium_fallback", {});
      const startedJob: SeleniumFallbackJob = {
        job_id: start.job_id,
        status: "queued",
        result: { status_message: "queued", completed_handles: 0, total_handles: start.handles_total, ticket_count: 0 },
      };
      setSeleniumJob(startedJob);
      let done = false;
      while (!done) {
        const next = await apiGet<SeleniumFallbackJob>(`/api/jobs/status/${start.job_id}`);
        setSeleniumJob(next);
        done = next.status === "completed" || next.status === "failed";
        if (!done) {
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const toggleJobDetails = async (jobId: string) => {
    if (expandedJobId === jobId) {
      setExpandedJobId(null);
      setExpandedJob(null);
      setExpandedJobError(null);
      return;
    }
    setExpandedJobId(jobId);
    setExpandedJob(null);
    setExpandedJobError(null);
    try {
      const details = await apiGet<Job>(`/api/jobs/${jobId}`);
      setExpandedJob(details);
    } catch (e) {
      setExpandedJobError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section style={{ border: "1px solid #333", borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <h2>Orchestration Dashboard</h2>
      {error ? <p style={{ color: "#ff6b6b" }}>{error}</p> : null}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8 }}>
        <div><strong>Backend</strong><div>{status?.backend_health ?? "unknown"}</div></div>
        <div><strong>Browser</strong><div>{status?.browser_status ?? "unknown"}</div></div>
        <div><strong>Auth</strong><div>{status?.auth_status ?? "unknown"}</div></div>
        <div><strong>Secure tab</strong><div>{status?.secure_tab_status ?? "unknown"}</div></div>
        <div><strong>Session</strong><div>{status?.session_status ?? "unknown"}</div></div>
        <div><strong>Cookies</strong><div>{status?.cookies_status ?? "unknown"}</div></div>
        <div><strong>Auth probe</strong><div>{status?.probe_status ?? "unknown"}</div></div>
        <div><strong>Validation</strong><div>{status?.validation_status ?? "unknown"}</div></div>
        <div><strong>Current state</strong><div>{status?.state ?? "idle"}</div></div>
        <div><strong>DB counts</strong><div>tickets={status?.db_counts?.tickets ?? 0}, handles={status?.db_counts?.handles ?? 0}</div></div>
        <div><strong>Last error</strong><div>{status?.last_error || "none"}</div></div>
        <div><strong>Detection reason</strong><div>{status?.detection_reason || "none"}</div></div>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
        <button onClick={() => runAction("detect", "/api/browser/detect", { browser: "chrome", cdp_port: 9222 })} disabled={!!busy}>Detect Browser</button>
        <button onClick={() => runAction("seed", "/api/auth/seed")} disabled={!!busy}>Seed Auth</button>
        <button onClick={() => runAction("validate", "/api/auth/validate")} disabled={!!busy}>Validate Auth</button>
        <button onClick={() => runAction("scrape", "/api/scrape/run")} disabled={!!busy}>Run Scrape</button>
        <button onClick={runSeleniumFallback} disabled={!!busy}>Run Selenium Fallback Scrape</button>
        <button onClick={runE2E} disabled={!!busy}>Run End-to-End</button>
      </div>
      {seleniumJob ? (
        <div style={{ marginTop: 10 }}>
          <strong>Selenium fallback job</strong>
          <div>
            job_id={seleniumJob.job_id} · status={seleniumJob.status}
            {typeof seleniumJob.result?.completed_handles === "number" && typeof seleniumJob.result?.total_handles === "number"
              ? ` · progress=${seleniumJob.result.completed_handles}/${seleniumJob.result.total_handles}`
              : ""}
            {typeof seleniumJob.result?.ticket_count === "number" ? ` · ticket_count=${seleniumJob.result.ticket_count}` : ""}
            {seleniumJob.result?.current_handle ? ` · current_handle=${seleniumJob.result.current_handle}` : ""}
            {seleniumJob.result?.status_message ? ` · message=${seleniumJob.result.status_message}` : ""}
            {seleniumJob.error_message || seleniumJob.result?.error ? ` · error=${seleniumJob.error_message || seleniumJob.result?.error}` : ""}
          </div>
        </div>
      ) : null}
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
            <li key={job.job_id}>
              <button onClick={() => toggleJobDetails(job.job_id)} style={{ background: "transparent", color: "inherit", border: "1px solid #555", borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>
                {job.job_id}
              </button>{" "}
              · {job.current_state} · step={job.current_step} · found={job.records_found} · written={job.records_written}
              {expandedJobId === job.job_id ? (
                <div style={{ marginTop: 6, paddingLeft: 8, borderLeft: "2px solid #555" }}>
                  {expandedJobError ? (
                    <div style={{ color: "#ff6b6b" }}>Failed to load job details: {expandedJobError}</div>
                  ) : expandedJob ? (
                    <div>
                      created_at={expandedJob.created_at} · started_at={expandedJob.started_at || "n/a"} · completed_at={expandedJob.completed_at || "n/a"}
                      {expandedJob.error_message ? ` · error=${expandedJob.error_message}` : ""}
                    </div>
                  ) : (
                    <div>Loading job details…</div>
                  )}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
