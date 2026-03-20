"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";
import styles from "./OrchestrationDashboard.module.css";

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

type JobEvent = {
  id: number;
  ts_utc: string;
  level: string;
  event: string;
  message: string;
  data?: Record<string, unknown> | null;
};

export default function OrchestrationDashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [steps, setSteps] = useState<StepResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [seleniumJob, setSeleniumJob] = useState<SeleniumFallbackJob | null>(null);
  const [seleniumEvents, setSeleniumEvents] = useState<JobEvent[]>([]);
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
    setSeleniumEvents([]);
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
        const [next, eventsResp] = await Promise.all([
          apiGet<SeleniumFallbackJob>(`/api/jobs/status/${start.job_id}`),
          apiGet<{ events: JobEvent[] }>(`/api/jobs/${start.job_id}/events?limit=30`).catch(() => ({ events: [] })),
        ]);
        setSeleniumJob(next);
        setSeleniumEvents(eventsResp.events);
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
    <section className={styles.section}>
      <h2>Orchestration Dashboard</h2>
      {error ? <p className={styles.error}>{error}</p> : null}
      <div className={styles.statusGrid}>
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
      <div className={styles.actionRow}>
        <button type="button" onClick={() => runAction("detect", "/api/browser/detect", { browser: "chrome", cdp_port: 9222 })} disabled={!!busy}>Detect Browser</button>
        <button type="button" onClick={() => runAction("seed", "/api/auth/seed")} disabled={!!busy}>Seed Auth</button>
        <button type="button" onClick={() => runAction("validate", "/api/auth/validate")} disabled={!!busy}>Validate Auth</button>
        <button type="button" onClick={() => runAction("scrape", "/api/scrape/run")} disabled={!!busy}>Run Scrape</button>
        <button type="button" onClick={runSeleniumFallback} disabled={!!busy}>Run Selenium Fallback Scrape</button>
        <button type="button" onClick={runE2E} disabled={!!busy}>Run End-to-End</button>
      </div>
      {seleniumJob ? (
        <div className={styles.seleniumJobStatus}>
          <strong>Selenium fallback job</strong>
          <div className={styles.seleniumJobSummary}>
            <span>job_id={seleniumJob.job_id}</span>
            <span>status={seleniumJob.status}</span>
            {typeof seleniumJob.result?.completed_handles === "number" && typeof seleniumJob.result?.total_handles === "number" && (
              <span>progress={seleniumJob.result.completed_handles}/{seleniumJob.result.total_handles}</span>
            )}
            {typeof seleniumJob.result?.ticket_count === "number" && (
              <span>tickets={seleniumJob.result.ticket_count}</span>
            )}
            {seleniumJob.result?.current_handle && (
              <span>handle={seleniumJob.result.current_handle}</span>
            )}
            {seleniumJob.result?.status_message && (
              <span className={styles.seleniumJobMessage}>{seleniumJob.result.status_message}</span>
            )}
            {(seleniumJob.error_message || seleniumJob.result?.error) && (
              <span className={styles.seleniumJobError}>{seleniumJob.error_message || seleniumJob.result?.error}</span>
            )}
          </div>
          {seleniumEvents.length > 0 && (
            <div className={styles.seleniumEventLog}>
              <strong>Live events (last {seleniumEvents.length})</strong>
              <ol className={styles.seleniumEventList}>
                {seleniumEvents.map((ev) => {
                  const firstTickets = (ev.data?.first_ticket_ids as string[] | undefined) ?? [];
                  const count = ev.data?.count as number | undefined;
                  return (
                    <li key={ev.id} className={ev.level === "error" ? styles.seleniumEventError : styles.seleniumEventItem}>
                      <span className={styles.seleniumEventTs}>{ev.ts_utc.replace("T", " ").slice(0, 19)}</span>
                      {" "}{ev.message}
                      {typeof count === "number" && ` · count=${count}`}
                      {firstTickets.length > 0 && (
                        <span className={styles.seleniumTicketIds}> [{firstTickets.join(", ")}]</span>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </div>
      ) : null}
      {!!steps.length && (
        <div className={styles.e2eSteps}>
          <strong>E2E steps</strong>
          <ul>
            {steps.map((step, idx) => (
              <li key={`${step.state}-${idx}`}>{step.state}: {step.detail} ({step.ok ? "ok" : "failed"})</li>
            ))}
          </ul>
        </div>
      )}
      <div className={styles.recentJobs}>
        <strong>Recent jobs</strong>
        <ul>
          {jobs.slice(0, 5).map((job) => (
            <li key={job.job_id}>
              <button type="button" onClick={() => toggleJobDetails(job.job_id)} className={styles.jobToggleBtn}>
                {job.job_id}
              </button>{" "}
              · {job.current_state} · step={job.current_step} · found={job.records_found} · written={job.records_written}
              {expandedJobId === job.job_id ? (
                <div className={styles.jobDetails}>
                  {expandedJobError ? (
                    <div className={styles.jobDetailsError}>Failed to load job details: {expandedJobError}</div>
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
