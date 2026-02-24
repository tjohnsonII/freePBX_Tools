"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost, getLastApiCall } from "../lib/api";

type HandleRow = { handle: string; status?: string; last_message?: string; ticketsCount?: number };
type Ticket = { ticket_id: string; title?: string; status?: string; updated_utc?: string; created_utc?: string };
type TicketResponse = { items: Ticket[]; totalCount: number };
type DebugDb = { dbPathAbs: string; counts: { handles: number; tickets: number; scrape_jobs: number }; tables: string[] };
type ScrapeStatus = { jobId: string; status: string; startedAt?: string; finishedAt?: string; error?: string; summary?: any };

type ScrapeMode = "all" | "handle" | "ticket";

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
  const [handlesMeta, setHandlesMeta] = useState<HandleRow[]>([]);
  const [mode, setMode] = useState<ScrapeMode>("handle");
  const [ticketId, setTicketId] = useState("");
  const [limit, setLimit] = useState("50");
  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState<ScrapeStatus | null>(null);
  const [sseEvents, setSseEvents] = useState<string[]>([]);
  const [debugDb, setDebugDb] = useState<DebugDb | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  const refreshAll = async () => {
    const hs = await apiGet<{ items: string[] }>(`/api/handles/all?q=${encodeURIComponent(search)}&limit=500`);
    setHandles(hs.items);
    if (!selectedHandle && hs.items.length) setSelectedHandle(hs.items[0]);
    const dbInfo = await apiGet<DebugDb>("/api/debug/db");
    setDebugDb(dbInfo);
    const hRows = await apiGet<HandleRow[]>(`/api/handles?q=${encodeURIComponent(search)}&limit=500&offset=0`);
    setHandlesMeta(hRows);
  };

  useEffect(() => {
    refreshAll().catch((e) => setError(formatApiError(e)));
  }, [search]);

  useEffect(() => {
    if (!selectedHandle) return;
    apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(selectedHandle)}/tickets?limit=100&status=any`)
      .then((r) => setTickets(r.items))
      .catch((e) => setError(formatApiError(e)));
  }, [selectedHandle]);

  const startScrape = async () => {
    try {
      setError(null);
      setSseEvents([]);
      const payload: any = { mode, limit: Number(limit) || undefined };
      if (mode === "handle" || mode === "ticket") payload.handle = selectedHandle;
      if (mode === "ticket") payload.ticketId = ticketId;
      const res = await apiPost<{ jobId: string }>("/api/scrape", payload);
      setJobId(res.jobId);
      const es = new EventSource(`/api/scrape/${res.jobId}/events`);
      sseRef.current = es;
      es.onmessage = (event) => setSseEvents((prev) => [...prev, event.data].slice(-200));
      const poll = setInterval(async () => {
        const js = await apiGet<ScrapeStatus>(`/api/scrape/${res.jobId}/status`);
        setJobStatus(js);
        if (["completed", "failed"].includes(js.status)) {
          clearInterval(poll);
          es.close();
          if (selectedHandle) {
            const rows = await apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(selectedHandle)}/tickets?limit=100&status=any`);
            setTickets(rows.items);
            refreshAll().catch(() => undefined);
          }
        }
      }, 1500);
    } catch (e) {
      setError(formatApiError(e));
    }
  };

  const selectedHandleMeta = handlesMeta.find((h) => h.handle === selectedHandle);
  const lastApi = getLastApiCall();

  return (
    <main>
      <h1>Ticket History</h1>
      {error && <p style={{ color: "#a22" }}>{error}</p>}

      <section style={{ border: "1px solid #888", padding: 10, marginBottom: 10 }}>
        <h3>Diagnostics</h3>
        <p>DB path: <code>{debugDb?.dbPathAbs || "-"}</code></p>
        <p>Counts: handles={debugDb?.counts?.handles ?? 0} tickets={debugDb?.counts?.tickets ?? 0} jobs={debugDb?.counts?.scrape_jobs ?? 0}</p>
        <p>Last API call: {lastApi ? `${lastApi.url} status=${lastApi.status} ms=${lastApi.ms} count=${lastApi.count ?? "-"}` : "-"}</p>
        <p>Last scrape job: {jobStatus ? `${jobStatus.jobId} ${jobStatus.status}` : "-"}</p>
        <p>Artifacts folder hint: <code>webscraper/output/artifacts/{jobId || "<jobId>"}</code></p>
        <p>API Base: <code>{apiInfo.browserBase}</code> Proxy: <code>{apiInfo.proxyTarget}</code></p>
      </section>

      <HandleDropdown handles={handles} selectedHandle={selectedHandle} search={search} onSearchChange={setSearch} onSelect={setSelectedHandle} />

      <div>
        <label>Mode
          <select value={mode} onChange={(e) => setMode(e.target.value as ScrapeMode)}>
            <option value="handle">latest</option>
            <option value="all">all</option>
            <option value="ticket">ticket</option>
          </select>
        </label>
        <label>Ticket Id <input value={ticketId} onChange={(e) => setTicketId(e.target.value)} disabled={mode !== "ticket"} /></label>
        <label>Limit <input type="number" value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
        <button onClick={startScrape}>Run</button>
      </div>

      {sseEvents.length > 0 && <pre style={{ maxHeight: 240, overflow: "auto" }}>{sseEvents.join("\n")}</pre>}

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      {tickets.length === 0 ? (
        <p>No tickets found. tickets_count={debugDb?.counts?.tickets ?? 0}; last_status={selectedHandleMeta?.status || "-"}; last_message={selectedHandleMeta?.last_message || "-"}</p>
      ) : (
        <table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Updated</th></tr></thead><tbody>
          {tickets.map((t) => <tr key={`${t.ticket_id}-${t.updated_utc}`}><td>{t.ticket_id}</td><td>{t.title || "-"}</td><td>{t.status || "-"}</td><td>{t.updated_utc || "-"}</td></tr>)}
        </tbody></table>
      )}
    </main>
  );
}
