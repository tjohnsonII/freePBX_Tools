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
  totalCount: number;
  page: number;
  pageSize: number;
};

type ScrapeStatus = {
  jobId: string;
  status: string;
  handle: string;
  progress: { completed: number; total: number };
  error?: string;
};

export default function HandlesPage() {
  const [handleFilter, setHandleFilter] = useState("");
  const [rows, setRows] = useState<HandleSummary[]>([]);
  const [selectedHandle, setSelectedHandle] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [job, setJob] = useState<ScrapeStatus | null>(null);

  const refreshHandles = async (query: string) => {
    try {
      setError(null);
      const list = await apiGet<HandleSummary[]>(`/api/handles?q=${encodeURIComponent(query)}&limit=500`);
      setRows(list);
      if (!selectedHandle && list.length > 0) {
        setSelectedHandle(list[0].handle);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    }
  };

  useEffect(() => {
    refreshHandles(handleFilter);
  }, [handleFilter]);

  useEffect(() => {
    if (!selectedHandle) {
      setTickets([]);
      return;
    }
    apiGet<TicketResponse>(`/api/tickets?handle=${encodeURIComponent(selectedHandle)}&page=1&pageSize=100&sort=newest`)
      .then((res) => {
        setError(null);
        setTickets(res.items);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setTickets([]);
      });
  }, [selectedHandle]);

  useEffect(() => {
    if (!job?.jobId || job.status === "completed" || job.status === "failed") {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const status = await apiGet<ScrapeStatus>(`/api/scrape/${job.jobId}`);
        setJob(status);
        if (status.status === "completed" || status.status === "failed") {
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

  const startScrape = async (mode: "latest" | "full") => {
    if (!selectedHandle) {
      setScrapeError("Select a handle first.");
      return;
    }
    try {
      setScrapeError(null);
      const payload = await apiPost<{ jobId: string; status: string }>("/api/scrape", {
        handle: selectedHandle,
        mode,
        limit: mode === "latest" ? 20 : undefined,
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
        Filter handles
        <input
          placeholder="Type to filter handles"
          value={handleFilter}
          onChange={(e) => setHandleFilter(e.target.value)}
        />
      </label>

      <label>
        Handle
        <select value={selectedHandle} onChange={(e) => setSelectedHandle(e.target.value)}>
          <option value="">Select a handle</option>
          {filteredRows.map((h) => (
            <option key={h.handle} value={h.handle}>
              {h.handle} ({h.ticketsCount})
            </option>
          ))}
        </select>
      </label>

      <div>
        <button disabled={!selectedHandle} onClick={() => startScrape("latest")}>Run Scrape (Latest)</button>
        <button disabled={!selectedHandle} onClick={() => startScrape("full")}>Run Scrape (Full)</button>
      </div>

      {error && <p>{error}</p>}
      {scrapeError && <p>{scrapeError}</p>}
      {job && (
        <div>
          <p>
            Job {job.jobId}: {job.status} ({job.progress.completed}/{job.progress.total}) for {job.handle}
          </p>
          {job.error && <p>{job.error}</p>}
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

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
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
