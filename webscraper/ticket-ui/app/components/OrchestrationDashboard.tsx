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

type ScrapeStart = { queued: boolean; job_id: string; handles_total: number; status: string; resume_from_handle?: string | null };
type ScrapeJob = {
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

type ScrapeState = {
  last_completed_handle: string | null;
  updated_utc: string | null;
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
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [scrapeJob, setScrapeJob] = useState<ScrapeJob | null>(null);
  const [scrapeEvents, setScrapeEvents] = useState<JobEvent[]>([]);
  const [scrapeState, setScrapeState] = useState<ScrapeState | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [expandedJob, setExpandedJob] = useState<Job | null>(null);
  const [expandedJobError, setExpandedJobError] = useState<string | null>(null);

  const reload = async () => {
    try {
      const [system, jobList, state] = await Promise.all([
        apiGet<SystemStatus>("/api/system/status"),
        apiGet<{ items: Job[] }>("/api/jobs"),
        apiGet<ScrapeState>("/api/scrape/state").catch(() => ({ last_completed_handle: null, updated_utc: null })),
      ]);
      setStatus(system);
      setJobs(jobList.items || []);
      setScrapeState(state);
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

  const startScrape = async (resumeFromHandle?: string | null) => {
    const label = resumeFromHandle ? "resume" : "start";
    setBusy(label);
    setError(null);
    setScrapeEvents([]);
    try {
      const start = await apiPost<ScrapeStart>("/api/scrape/start", resumeFromHandle ? { resume_from_handle: resumeFromHandle } : {});
      const startedJob: ScrapeJob = {
        job_id: start.job_id,
        status: "queued",
        result: { status_message: "queued", completed_handles: 0, total_handles: start.handles_total, ticket_count: 0 },
      };
      setScrapeJob(startedJob);
      let done = false;
      while (!done) {
        const [next, eventsResp] = await Promise.all([
          apiGet<ScrapeJob>(`/api/jobs/status/${start.job_id}`),
          apiGet<{ events: JobEvent[] }>(`/api/jobs/${start.job_id}/events?limit=30`).catch(() => ({ events: [] })),
        ]);
        setScrapeJob(next);
        setScrapeEvents(eventsResp.events);
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
      <h2>Scrape Dashboard</h2>
      {error ? <p className={styles.error}>{error}</p> : null}
      <div className={styles.statusGrid}>
        <div><strong>Backend</strong><div>{status?.backend_health ?? "unknown"}</div></div>
        <div><strong>Current state</strong><div>{status?.state ?? "idle"}</div></div>
        <div><strong>DB tickets</strong><div>{status?.db_counts?.tickets ?? 0}</div></div>
        <div><strong>DB handles</strong><div>{status?.db_counts?.handles ?? 0}</div></div>
        <div><strong>Last error</strong><div>{status?.last_error || "none"}</div></div>
        {scrapeState?.last_completed_handle && (
          <div><strong>Last scraped handle</strong><div>{scrapeState.last_completed_handle}</div></div>
        )}
      </div>
      <div className={styles.actionRow}>
        <button type="button" onClick={() => startScrape()} disabled={!!busy}>
          {busy === "start" ? "Starting…" : "Start Scrape"}
        </button>
        {scrapeState?.last_completed_handle && (
          <button type="button" onClick={() => startScrape(scrapeState.last_completed_handle)} disabled={!!busy}>
            {busy === "resume" ? "Resuming…" : `Resume from ${scrapeState.last_completed_handle}`}
          </button>
        )}
      </div>
      {scrapeJob ? (
        <div className={styles.seleniumJobStatus}>
          <strong>Scrape job</strong>
          <div className={styles.seleniumJobSummary}>
            <span>job_id={scrapeJob.job_id}</span>
            <span>status={scrapeJob.status}</span>
            {typeof scrapeJob.result?.completed_handles === "number" && typeof scrapeJob.result?.total_handles === "number" && (
              <span>progress={scrapeJob.result.completed_handles}/{scrapeJob.result.total_handles}</span>
            )}
            {typeof scrapeJob.result?.ticket_count === "number" && (
              <span>tickets={scrapeJob.result.ticket_count}</span>
            )}
            {scrapeJob.result?.current_handle && (
              <span>handle={scrapeJob.result.current_handle}</span>
            )}
            {scrapeJob.result?.status_message && (
              <span className={styles.seleniumJobMessage}>{scrapeJob.result.status_message}</span>
            )}
            {(scrapeJob.error_message || scrapeJob.result?.error) && (
              <span className={styles.seleniumJobError}>{scrapeJob.error_message || scrapeJob.result?.error}</span>
            )}
          </div>
          {scrapeEvents.length > 0 && (
            <div className={styles.seleniumEventLog}>
              <strong>Live events (last {scrapeEvents.length})</strong>
              <ol className={styles.seleniumEventList}>
                {scrapeEvents.map((ev) => {
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
