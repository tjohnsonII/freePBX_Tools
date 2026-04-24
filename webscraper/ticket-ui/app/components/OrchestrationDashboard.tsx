"use client";

import { useEffect, useState } from "react";
import { apiGet } from "../../lib/api";
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
  db_counts: { tickets: number; handles: number };
  last_error?: string | null;
  state: StepState;
};

type ScrapeState = {
  last_completed_handle: string | null;
  updated_utc: string | null;
};

export default function OrchestrationDashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scrapeState, setScrapeState] = useState<ScrapeState | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [expandedJob, setExpandedJob] = useState<Job | null>(null);
  const [expandedJobError, setExpandedJobError] = useState<string | null>(null);

  const reload = async () => {
    const [system, jobList, state] = await Promise.all([
      apiGet<SystemStatus>("/api/system/status").catch(() => null),
      apiGet<{ items: Job[] }>("/api/jobs").catch(() => null),
      apiGet<ScrapeState>("/api/scrape/state").catch(() => ({ last_completed_handle: null, updated_utc: null })),
    ]);
    if (system) { setStatus(system); setError(null); }
    if (jobList) setJobs(jobList.items || []);
    setScrapeState(state);
  };

  useEffect(() => {
    reload().catch(() => undefined);
    const timer = setInterval(() => reload().catch(() => undefined), 5000);
    return () => clearInterval(timer);
  }, []);

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
