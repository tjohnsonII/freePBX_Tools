"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type HandleSummary = {
  handle: string;
  ticketsCount: number;
  lastTicketAt?: string;
  lastScrapeAt?: string;
  status?: string;
};

type Ticket = {
  ticket_id: string;
  title?: string;
  status?: string;
  updated_utc?: string;
  created_utc?: string;
};

type TicketResponse = {
  items: Ticket[];
  total: number;
};

type ScrapeStatus = {
  jobId: string;
  status: string;
  progress: { completed: number; total: number };
  logs: string[];
};

export default function HandlesPage() {
  const [handleFilter, setHandleFilter] = useState("");
  const [rows, setRows] = useState<HandleSummary[]>([]);
  const [selectedHandles, setSelectedHandles] = useState<string[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [job, setJob] = useState<ScrapeStatus | null>(null);

  const primaryHandle = selectedHandles[0] || "";

  const refreshHandles = async (query: string) => {
    try {
      setError(null);
      const list = await apiGet<HandleSummary[]>(`/api/handles?q=${encodeURIComponent(query)}&limit=500`);
      setRows(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    }
  };

  useEffect(() => {
    refreshHandles(handleFilter);
  }, [handleFilter]);

  useEffect(() => {
    if (!primaryHandle) {
      setTickets([]);
      return;
    }
    apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(primaryHandle)}/tickets?limit=100`)
      .then((res) => {
        setError(null);
        setTickets(res.items);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setTickets([]);
      });
  }, [primaryHandle]);

  useEffect(() => {
    if (!job?.jobId || job.status === "completed" || job.status === "failed") {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const status = await apiGet<ScrapeStatus>(`/api/scrape/${job.jobId}`);
        setJob(status);
        if (status.status === "completed") {
          refreshHandles(handleFilter);
        }
      } catch (e) {
        setScrapeError(e instanceof Error ? e.message : String(e));
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [job?.jobId, job?.status, handleFilter]);

  const filteredRows = useMemo(
    () => rows.filter((row) => row.handle.toLowerCase().includes(handleFilter.toLowerCase())),
    [rows, handleFilter],
  );

  const onSelectHandles = (values: string[]) => {
    setSelectedHandles(values);
    setScrapeError(null);
  };

  const startScrape = async (handles: string[], mode: "latest" | "full") => {
    try {
      setScrapeError(null);
      const payload = await apiPost<{ jobId: string }>("/api/scrape", {
        handles,
        mode,
        maxTickets: mode === "latest" ? 20 : undefined,
      });
      const status = await apiGet<ScrapeStatus>(`/api/scrape/${payload.jobId}`);
      setJob(status);
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <main>
      <h1>Ticket History</h1>
      <label>
        Search handles
        <input
          placeholder="Type to filter handles"
          value={handleFilter}
          onChange={(e) => setHandleFilter(e.target.value)}
        />
      </label>

      <select
        multiple
        size={10}
        value={selectedHandles}
        onChange={(e) =>
          onSelectHandles(Array.from(e.target.selectedOptions).map((opt) => opt.value))
        }
      >
        {filteredRows.map((h) => (
          <option key={h.handle} value={h.handle}>
            {h.handle} ({h.ticketsCount})
          </option>
        ))}
      </select>

      <div>
        <button disabled={selectedHandles.length === 0} onClick={() => startScrape(selectedHandles, "latest")}>Scrape Selected</button>
        <button
          onClick={() => {
            if (window.confirm("Scrape all handles? This may take a while.")) {
              startScrape(rows.map((r) => r.handle), "full");
            }
          }}
        >
          Scrape All
        </button>
      </div>

      {error && <p>{error}</p>}
      {scrapeError && <p>{scrapeError}</p>}
      {job && (
        <div>
          <p>
            Job {job.jobId}: {job.status} ({job.progress.completed}/{job.progress.total})
          </p>
          <pre>{job.logs.slice(-8).join("\n")}</pre>
        </div>
      )}

      <h2>Handles</h2>
      <table>
        <thead>
          <tr><th>Handle</th><th>Tickets</th><th>Last Ticket</th><th>Last Scrape</th><th>Status</th></tr>
        </thead>
        <tbody>
          {filteredRows.map((h) => (
            <tr key={h.handle}>
              <td>{h.handle}</td>
              <td>{h.ticketsCount ?? 0}</td>
              <td>{h.lastTicketAt || "-"}</td>
              <td>{h.lastScrapeAt || "-"}</td>
              <td>{h.status || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>{primaryHandle ? `Tickets for ${primaryHandle}` : "Select a handle"}</h2>
      <table>
        <thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Updated</th><th>Created</th></tr></thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={`${t.ticket_id}-${t.updated_utc}`}>
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
