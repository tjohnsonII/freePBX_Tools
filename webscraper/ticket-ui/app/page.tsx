"use client";

import { useEffect, useMemo, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost } from "../lib/api";

type HandleSummary = {
  handle: string;
  last_scrape_utc?: string;
  ticket_count: number;
  open_count: number;
  updated_latest_utc?: string;
};

type HandleListPayload = { items: string[]; count: number };

type Ticket = {
  ticket_id: string;
  title?: string;
  status?: string;
  updated_utc?: string;
  created_utc?: string;
};

type TicketResponse = {
  items: Ticket[];
  totalCount: number;
  page: number;
  pageSize: number;
};

type ScrapeStatus = {
  jobId: string;
  status: string;
  handle: string;
  mode: "latest" | "full";
  logs: string[];
  progress: { completed: number; total: number };
  error?: string;
  resultSummary?: {
    errorType?: string;
    exitCode?: number | null;
    logTail?: string[];
    command?: string | string[];
  };
};

type ApiHealth = {
  status: string;
  db_path?: string;
  last_updated_utc?: string;
  stats?: {
    total_handles?: number;
    total_tickets?: number;
    total_artifacts?: number;
    last_updated_utc?: string;
  };
};

function formatApiError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.kind === "network") {
      return "Network/proxy error: UI cannot reach API target.";
    }
    if (error.kind === "timeout") {
      return "Request timeout while waiting for API response.";
    }
    if (error.kind === "http") {
      return `API HTTP error: ${error.message}`;
    }
  }
  return error instanceof Error ? error.message : String(error);
}

export default function HandlesPage() {
  const [handleFilter, setHandleFilter] = useState("");
  const [debouncedHandleFilter, setDebouncedHandleFilter] = useState("");
  const [handleOptions, setHandleOptions] = useState<string[]>([]);
  const [selectedHandle, setSelectedHandle] = useState("");
  const [selectedSummary, setSelectedSummary] = useState<HandleSummary | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<ScrapeStatus[]>([]);
  const [jobMode, setJobMode] = useState<"latest" | "full">("latest");
  const [jobLimit, setJobLimit] = useState("20");
  const [apiHealth, setApiHealth] = useState<ApiHealth | null>(null);
  const [apiHealthError, setApiHealthError] = useState<string | null>(null);

  const apiInfo = useMemo(() => apiBaseInfo(), []);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedHandleFilter(handleFilter.trim()), 300);
    return () => clearTimeout(timer);
  }, [handleFilter]);

  useEffect(() => {
    apiGet<ApiHealth>("/api/health")
      .then((payload) => {
        setApiHealth(payload);
        setApiHealthError(null);
      })
      .catch((e) => {
        setApiHealth(null);
        setApiHealthError(formatApiError(e));
      });
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadHandleOptions = async () => {
      try {
        const res = await apiGet<HandleListPayload>(`/api/handles/all?q=${encodeURIComponent(debouncedHandleFilter)}&limit=500`);
        if (cancelled) return;
        setError(null);
        setHandleOptions(res.items);
        if (!selectedHandle && res.items.length) {
          setSelectedHandle(res.items[0]);
        }
        return;
      } catch (primaryError) {
        try {
          const fallback = await apiGet<{ handle: string }[]>(`/api/handles?q=${encodeURIComponent(debouncedHandleFilter)}&limit=500&offset=0`);
          if (cancelled) return;
          const items = fallback.map((item) => item.handle).filter(Boolean);
          setError(null);
          setHandleOptions(items);
          if (!selectedHandle && items.length) {
            setSelectedHandle(items[0]);
          }
          return;
        } catch {
          if (cancelled) return;
          setError(formatApiError(primaryError));
          setHandleOptions((prev) => (prev.length ? prev : []));
        }
      }
    };

    void loadHandleOptions();

    return () => {
      cancelled = true;
    };
  }, [debouncedHandleFilter, selectedHandle]);

  useEffect(() => {
    if (!selectedHandle) {
      setSelectedSummary(null);
      setTickets([]);
      return;
    }

    apiGet<HandleSummary[]>(`/api/handles/summary?q=${encodeURIComponent(selectedHandle)}&limit=10&offset=0`)
      .then((rows) => {
        const exact = rows.find((row) => row.handle === selectedHandle) || null;
        setSelectedSummary(exact);
      })
      .catch(() => setSelectedSummary(null));

    apiGet<TicketResponse>(`/api/tickets?handle=${encodeURIComponent(selectedHandle)}&page=1&pageSize=100&sort=newest`)
      .then((res) => {
        setError(null);
        setTickets(res.items);
      })
      .catch((e) => {
        setError(formatApiError(e));
        setTickets([]);
      });
  }, [selectedHandle]);

  useEffect(() => {
    const activeJobs = jobs.filter((job) => !["completed", "failed"].includes(job.status));
    if (!activeJobs.length) {
      return;
    }

    const timer = setInterval(async () => {
      try {
        const updates = await Promise.all(activeJobs.map((job) => apiGet<ScrapeStatus>(`/api/scrape/${job.jobId}`)));
        setJobs((prev) => prev.map((existing) => updates.find((item) => item.jobId === existing.jobId) || existing));
      } catch (e) {
        setScrapeError(formatApiError(e));
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [jobs]);

  const startSingleScrape = async () => {
    if (!selectedHandle) {
      setScrapeError("Select a handle first.");
      return;
    }

    const parsedLimit = Number(jobLimit);
    const limitPayload = Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : undefined;

    try {
      setScrapeError(null);
      const payload = await apiPost<{ jobId: string; status: string }>("/api/scrape", {
        handle: selectedHandle,
        mode: jobMode,
        limit: limitPayload,
      });
      const status = await apiGet<ScrapeStatus>(`/api/scrape/${payload.jobId}`);
      setJobs((prev) => [status, ...prev]);
    } catch (e) {
      setScrapeError(formatApiError(e));
    }
  };

  return (
    <main>
      <h1>Ticket History</h1>

      <div style={{ border: "1px solid #2a2", padding: 12, marginBottom: 12 }}>
        {apiHealth?.status === "ok" ? (
          <>
            <p>
              API OK. db_path: <code>{apiHealth.db_path || "(unknown)"}</code>
            </p>
            <p>
              Stats: {apiHealth.stats?.total_handles ?? 0} handles, {apiHealth.stats?.total_tickets ?? 0} tickets, {apiHealth.stats?.total_artifacts ?? 0} artifacts.
            </p>
            <p>Last updated: {apiHealth.last_updated_utc || apiHealth.stats?.last_updated_utc || "-"}</p>
          </>
        ) : (
          <>
            <p>API unreachable.</p>
            <p>
              Start API: <code>python -m webscraper.ticket_api.app --reload --port 8787 --db webscraper/output/tickets.sqlite</code>
            </p>
            <p>
              Start UI: <code>cd webscraper/ticket-ui && npm run dev:local-api</code>
            </p>
            <p>
              API Base: <code>{apiInfo.browserBase}</code>
            </p>
            <p>
              Proxy Target: <code>{apiInfo.proxyTarget}</code>
            </p>
            {apiHealthError ? <p>Last error: {apiHealthError}</p> : null}
            <a href="/api/health">Open /api/health</a>
          </>
        )}
      </div>

      {(error || scrapeError) && (
        <div style={{ border: "1px solid #a22", padding: 12, marginBottom: 12 }}>
          <strong>API Connectivity Help</strong>
          <p>{error || scrapeError}</p>
          <p>
            API Base: <code>{apiInfo.browserBase}</code>
          </p>
          <p>
            Proxy Target: <code>{apiInfo.proxyTarget}</code>
          </p>
          <p>
            Start API: <code>python -m webscraper.ticket_api.app --reload --port 8787 --db webscraper/output/tickets.sqlite</code>
          </p>
          <p>
            Start UI: <code>cd webscraper/ticket-ui && npm run dev:local-api</code>
          </p>
          <a href="/api/health">Open /api/health</a>
        </div>
      )}

      <HandleDropdown
        handles={handleOptions}
        selectedHandle={selectedHandle}
        search={handleFilter}
        onSearchChange={setHandleFilter}
        onSelect={setSelectedHandle}
      />

      {selectedSummary && (
        <p>
          Summary: {selectedSummary.ticket_count} tickets, {selectedSummary.open_count} open, last scrape {selectedSummary.last_scrape_utc || "-"}, latest update {selectedSummary.updated_latest_utc || "-"}
        </p>
      )}

      <div>
        <label>
          Mode
          <select value={jobMode} onChange={(e) => setJobMode(e.target.value as "latest" | "full")}>
            <option value="latest">latest</option>
            <option value="full">full</option>
          </select>
        </label>
        <label>
          Limit
          <input type="number" value={jobLimit} min={1} max={5000} onChange={(e) => setJobLimit(e.target.value)} placeholder="optional" />
        </label>
        <button disabled={!selectedHandle} onClick={startSingleScrape}>Run scrape</button>
      </div>

      {jobs.map((job) => {
        const jobLogTail = job.resultSummary?.logTail || job.logs?.slice(-40) || [];
        return (
          <div key={job.jobId} style={{ border: "1px solid #888", marginTop: 10, padding: 8 }}>
            <p>
              Job {job.jobId}: {job.status} ({job.progress.completed}/{job.progress.total}) for {job.handle} [{job.mode}]
            </p>
            {job.error && <p>Error: {job.error}</p>}
            {job.resultSummary?.errorType ? <p>Failure type: {job.resultSummary.errorType}</p> : null}
            {job.resultSummary?.command ? <p>Command: <code>{Array.isArray(job.resultSummary.command) ? job.resultSummary.command.join(" ") : job.resultSummary.command}</code></p> : null}
            {jobLogTail.length ? <pre>{jobLogTail.join("\n")}</pre> : null}
          </div>
        );
      })}

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      <table>
        <thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Updated</th><th>Created</th></tr></thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={`${t.ticket_id}-${t.updated_utc}-${selectedHandle}`}>
              <td>{t.ticket_id}</td>
              <td>{t.title || "-"}</td>
              <td>{t.status || "-"}</td>
              <td>{t.updated_utc || "-"}</td>
              <td>{t.created_utc || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
