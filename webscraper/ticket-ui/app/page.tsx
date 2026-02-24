"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost, getLastApiCall } from "../lib/api";

type HandleRow = { handle: string; status?: string; error_message?: string; finished_utc?: string; artifacts_hint?: string; ticket_count?: number };
type Ticket = { ticket_id: string; title?: string; status?: string; updated_utc?: string };
type TicketResponse = { items: Ticket[]; totalCount: number };
type HandleLatest = { handle: string; status?: string; error_message?: string; started_utc?: string; finished_utc?: string; artifacts_hint?: string; last_run_id?: string };
type EventsResponse = { items: { ts: string; level: string; event: string; message: string }[] };

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
  const [latest, setLatest] = useState<HandleLatest | null>(null);
  const [mode, setMode] = useState<ScrapeMode>("handle");
  const [ticketId, setTicketId] = useState("");
  const [limit, setLimit] = useState("50");
  const [events, setEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  const refreshAll = async () => {
    const hs = await apiGet<{ items: string[] }>(`/api/handles`);
    const latest = await apiGet<any>(`/api/runs/latest/tickets_all`).catch(() => null);
    const allHandles = hs.items.filter((h) => h.toLowerCase().includes(search.toLowerCase()));
    setHandles(allHandles);
    if (!selectedHandle && allHandles.length) setSelectedHandle(allHandles[0]);
    const merged: HandleRow[] = allHandles.map((h) => {
      const row = latest?.handles?.[h];
      if (!row) return { handle: h, status: "never ran", error_message: "-", finished_utc: "-", ticket_count: 0 };
      return { handle: h, status: row.status, error_message: row.error || "-", finished_utc: row.finished_utc || "-", ticket_count: row.ticket_count || 0 };
    });
    setHandlesMeta(merged);
  };

  useEffect(() => {
    refreshAll().catch((e) => setError(formatApiError(e)));
  }, [search]);

  useEffect(() => {
    if (!selectedHandle) return;
    apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(selectedHandle)}/tickets?limit=100&status=any`).then((r) => setTickets(r.items));
    apiGet<HandleLatest>(`/api/handles/${encodeURIComponent(selectedHandle)}/latest`).then(setLatest).catch(() => setLatest(null));
  }, [selectedHandle]);

  useEffect(() => {
    const timer = setInterval(() => {
      apiGet<EventsResponse>("/api/events/latest?limit=50")
        .then((res) => setEvents(res.items.map((e) => `${e.ts} ${e.level} ${e.event} ${e.message}`)))
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  const startScrape = async () => {
    try {
      setError(null);
      const payload: any = { mode, limit: Number(limit) || undefined };
      if (mode === "handle" || mode === "ticket") payload.handle = selectedHandle;
      if (mode === "ticket") payload.ticketId = ticketId;
      const res = await apiPost<{ jobId: string }>("/api/scrape", payload);
      const es = new EventSource(`/api/scrape/${res.jobId}/events`);
      sseRef.current = es;
      es.onmessage = (event) => setEvents((prev) => [...prev, event.data].slice(-50));
      refreshAll().catch(() => undefined);
    } catch (e) {
      setError(formatApiError(e));
    }
  };

  const lastApi = getLastApiCall();

  return (
    <main>
      <h1>Ticket History</h1>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      <p>API Base: <code>{apiInfo.browserBase}</code> Proxy: <code>{apiInfo.proxyTarget}</code></p>
      <p>Last API call: {lastApi ? `${lastApi.url} status=${lastApi.status} ms=${lastApi.ms}` : "-"}</p>

      <HandleDropdown selectedHandle={selectedHandle} search={search} onSearchChange={setSearch} onSelect={setSelectedHandle} />

      <div>
        <label>Mode
          <select value={mode} onChange={(e) => setMode(e.target.value as ScrapeMode)}>
            <option value="handle">one handle</option>
            <option value="all">all handles</option>
            <option value="ticket">one ticket</option>
          </select>
        </label>
        <label>Ticket Id <input value={ticketId} onChange={(e) => setTicketId(e.target.value)} disabled={mode !== "ticket"} /></label>
        <label>Limit <input type="number" value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
        <button onClick={startScrape}>Scrape / Re-scrape</button>
      </div>

      <h2>Handles</h2>
      <table><thead><tr><th>Handle</th><th>Status</th><th>Error</th><th>Last Updated</th><th>Ticket Count</th><th>Actions</th></tr></thead><tbody>
        {handlesMeta.map((h) => (
          <tr key={h.handle}>
            <td>{h.handle}</td><td>{h.status || "never ran"}</td><td>{h.error_message || "-"}</td><td>{h.finished_utc || "-"}</td><td>{h.ticket_count ?? 0}</td>
            <td><button onClick={() => { setSelectedHandle(h.handle); setMode("handle"); }}>Scrape</button></td>
          </tr>
        ))}
      </tbody></table>

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      {tickets.length === 0 ? (
        <div>
          <p>No tickets in DB.</p>
          <p>Status: {latest?.status || "-"} Error: {latest?.error_message || "-"}</p>
          <p>Artifacts Hint: <code>{latest?.artifacts_hint || "-"}</code></p>
          <pre style={{ maxHeight: 160, overflow: "auto" }}>{JSON.stringify(latest || {}, null, 2)}</pre>
        </div>
      ) : (
        <table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Updated</th></tr></thead><tbody>
          {tickets.map((t) => <tr key={`${t.ticket_id}-${t.updated_utc}`}><td>{t.ticket_id}</td><td>{t.title || "-"}</td><td>{t.status || "-"}</td><td>{t.updated_utc || "-"}</td></tr>)}
        </tbody></table>
      )}

      <h3>Live events (last 50)</h3>
      <pre style={{ maxHeight: 260, overflow: "auto" }}>{events.join("\n")}</pre>
    </main>
  );
}
