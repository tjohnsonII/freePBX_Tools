"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost } from "../lib/api";

type Ticket = { ticket_id: string; title?: string; subject?: string; status?: string; updated_utc?: string };
type TicketResponse = { items: Ticket[]; totalCount: number };
type HandleListResponse = { items: string[]; count: number };
type JobStatus = {
  job_id: string;
  status: string;
  total_handles: number;
  completed: number;
  running: boolean;
  errors: number;
  error_message?: string;
};
type EventsResponse = { items: { ts: string; level: string; handle?: string; message: string }[] };

const AUTH_ERROR = "Not authenticated. Import cookies in UI Auth page and retry.";

function formatApiError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export default function HandlesPage() {
  const apiInfo = useMemo(() => apiBaseInfo(), []);
  const [search, setSearch] = useState("");
  const [handles, setHandles] = useState<string[]>([]);
  const [selectedHandle, setSelectedHandle] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadHandles = async () => {
    const res = await apiGet<HandleListResponse>(`/api/handles/all?q=${encodeURIComponent(search)}&limit=1000`);
    const names = Array.isArray(res?.items) ? res.items : [];
    setHandles(names);
    if (!selectedHandle && names.length) {
      setSelectedHandle(names[0]);
    }
  };

  const loadTickets = async (handle: string) => {
    const res = await apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(handle)}/tickets?limit=50&status=any`);
    setTickets(Array.isArray(res?.items) ? res.items : []);
  };

  useEffect(() => {
    loadHandles().catch((e) => setError(formatApiError(e)));
  }, [search]);

  useEffect(() => {
    if (!selectedHandle) {
      setTickets([]);
      return;
    }
    loadTickets(selectedHandle).catch(() => setTickets([]));
  }, [selectedHandle]);

  useEffect(() => {
    if (!jobId) return;
    const timer = setInterval(() => {
      apiGet<JobStatus>(`/api/scrape/status?job_id=${encodeURIComponent(jobId)}`)
        .then((status) => {
          setJobStatus(status);
          if (status.status === "completed" && selectedHandle) {
            loadTickets(selectedHandle).catch(() => undefined);
          }
        })
        .catch(() => undefined);
      apiGet<EventsResponse>(`/api/events/latest?limit=50&job_id=${encodeURIComponent(jobId)}`)
        .then((res) => {
          const items = Array.isArray(res?.items) ? res.items : [];
          setEvents(items.map((e) => `${e.ts} [${e.level}] ${e.handle ?? "-"}: ${e.message}`));
        })
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, [jobId, selectedHandle]);

  const startScrape = async (mode: "all" | "one") => {
    try {
      setError(null);
      const payload =
        mode === "one"
          ? { mode: "one", handle: selectedHandle, refresh_handles: false, rescrape: false }
          : { mode: "all", refresh_handles: false, rescrape: false };
      const response = await apiPost<{ job_id: string }>("/api/scrape/start", payload);
      setJobId(response.job_id);
      setJobStatus(null);
      setEvents([]);
    } catch (e) {
      setError(formatApiError(e));
    }
  };

  const showAuthCallout = (error || jobStatus?.error_message || "").includes("Not authenticated");

  return (
    <main>
      <p>
        API Base: <code>{apiInfo.browserBase}</code> Proxy: <code>{apiInfo.proxyTarget}</code>
      </p>

      {error && <p style={{ color: "#a22" }}>{error}</p>}
      {showAuthCallout && (
        <p style={{ background: "#fff3cd", padding: "10px" }}>
          {AUTH_ERROR} <Link href="/auth">Go to Auth</Link>
        </p>
      )}

      <HandleDropdown selectedHandle={selectedHandle} handles={handles} search={search} onSearchChange={setSearch} onSelect={setSelectedHandle} />

      <div>
        <button onClick={() => startScrape("one")} disabled={!selectedHandle}>
          Scrape selected handle
        </button>
        <button onClick={() => startScrape("all")}>Scrape all handles</button>
      </div>

      {jobStatus && (
        <section>
          <h3>Job status</h3>
          <p>
            Job: {jobStatus.job_id} | Status: {jobStatus.status} | Progress: {jobStatus.completed}/{jobStatus.total_handles} | Errors: {jobStatus.errors}
          </p>
          {jobStatus.error_message && <p style={{ color: "#a22" }}>{jobStatus.error_message}</p>}
        </section>
      )}

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Status</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={`${t.ticket_id}-${t.updated_utc}`}>
              <td>{t.ticket_id}</td>
              <td>{t.title || t.subject || "-"}</td>
              <td>{t.status || "-"}</td>
              <td>{t.updated_utc || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Latest events</h3>
      <pre style={{ maxHeight: 260, overflow: "auto" }}>{events.join("\n")}</pre>
    </main>
  );
}
