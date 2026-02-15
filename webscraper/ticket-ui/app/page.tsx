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
};

type ApiHealth = {
  status: string;
  db_path?: string;
};

function formatApiError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.kind === "network") {
      return "Unable to reach API (network/proxy issue).";
    }
    if (error.kind === "timeout") {
      return "Request timed out while waiting for API.";
    }
    if (error.kind === "http") {
      return error.message;
    }
  }
  return error instanceof Error ? error.message : String(error);
}

export default function HandlesPage() {
  const [handleFilter, setHandleFilter] = useState("");
  const [handleOptions, setHandleOptions] = useState<string[]>([]);
  const [selectedHandle, setSelectedHandle] = useState("");
  const [selectedSummary, setSelectedSummary] = useState<HandleSummary | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<ScrapeStatus[]>([]);
  const [jobMode, setJobMode] = useState<"latest" | "full">("latest");
  const [jobLimit, setJobLimit] = useState(20);
  const [apiHealth, setApiHealth] = useState<ApiHealth | null>(null);
  const [apiHealthError, setApiHealthError] = useState<string | null>(null);

  const apiInfo = useMemo(() => apiBaseInfo(), []);

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
    apiGet<HandleListPayload>(`/api/handles/all?q=${encodeURIComponent(handleFilter)}&limit=500`)
      .then((res) => {
        setHandleOptions(res.items);
        if (!selectedHandle && res.items.length) {
          setSelectedHandle(res.items[0]);
        }
      })
      .catch((e) => {
        setError(formatApiError(e));
        setHandleOptions([]);
      });
  }, [handleFilter, selectedHandle]);

  useEffect(() => {
    if (!selectedHandle) {
      setSelectedSummary(null);
      setTickets([]);
      return;
    }

    apiGet<HandleSummary[]>(`/api/handles/summary?q=${encodeURIComponent(selectedHandle)}&limit=1&offset=0`)
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
    }, 1500);

    return () => clearInterval(timer);
  }, [jobs]);

  const startSingleScrape = async () => {
    if (!selectedHandle) {
      setScrapeError("Select a handle first.");
      return;
    }
    try {
      setScrapeError(null);
      const payload = await apiPost<{ jobId: string; status: string }>("/api/scrape", {
        handle: selectedHandle,
        mode: jobMode,
        limit: jobMode === "latest" ? jobLimit : undefined,
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
          <p>
            API OK. db_path: <code>{apiHealth.db_path || "(unknown)"}</code>
          </p>
        ) : (
          <>
            <p>API unreachable. Start it with: <code>python -m webscraper.ticket_api.app --reload</code></p>
            <p>Proxy Target: <code>{apiInfo.proxyTarget}</code></p>
            {apiHealthError ? <p>Last error: {apiHealthError}</p> : null}
          </>
        )}
      </div>

      {(error || scrapeError) && (
        <div style={{ border: "1px solid #a22", padding: 12, marginBottom: 12 }}>
          <strong>API Connectivity Help</strong>
          <p>{error || scrapeError}</p>
          <p>API Base: {apiInfo.browserBase}</p>
          <p>Proxy Target: {apiInfo.proxyTarget}</p>
          <p>Start API: <code>python -m webscraper.ticket_api.app --reload --port 8787</code></p>
          <p>Start stack: <code>cd webscraper/ticket-ui && npm run dev:stack</code></p>
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
          <input type="number" value={jobLimit} min={1} max={5000} onChange={(e) => setJobLimit(Number(e.target.value || 20))} />
        </label>
        <button disabled={!selectedHandle} onClick={startSingleScrape}>Run scrape</button>
      </div>

      {jobs.map((job) => (
        <div key={job.jobId} style={{ border: "1px solid #888", marginTop: 10, padding: 8 }}>
          <p>
            Job {job.jobId}: {job.status} ({job.progress.completed}/{job.progress.total}) for {job.handle} [{job.mode}]
          </p>
          {job.error && <p>{job.error}</p>}
          {job.logs?.length ? <pre>{job.logs.slice(-50).join("\n")}</pre> : null}
        </div>
      ))}

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
