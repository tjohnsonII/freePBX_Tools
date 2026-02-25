"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost, getLastApiCall } from "../lib/api";

type HandleRow = {
  handle: string;
  status?: string;
  error_message?: string;
  error?: string;
  finished_utc?: string;
  last_updated_utc?: string;
  artifacts_hint?: string;
  ticket_count?: number;
};
type Ticket = { ticket_id: string; title?: string; subject?: string; status?: string; updated_utc?: string };
type TicketResponse = { items: Ticket[]; totalCount: number };
type HandleLatest = { handle: string; status?: string; error_message?: string; started_utc?: string; finished_utc?: string; artifacts_hint?: string; last_run_id?: string };
type EventsResponse = { items: { ts: string; level: string; handle?: string; message: string }[] };

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
  const [events, setEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  const refreshAll = async () => {
    const hs = await apiGet<{ items?: HandleRow[] }>(`/api/handles`);
    const source = Array.isArray(hs?.items) ? hs.items : [];
    const filteredHandles = (source ?? [])
      .filter((row) => typeof row?.handle === "string")
      .filter((row) => row.handle.toLowerCase().includes(search.toLowerCase()));
    const names = filteredHandles.map((row) => row.handle);
    setHandles(Array.isArray(names) ? names : []);
    setHandlesMeta(Array.isArray(filteredHandles) ? filteredHandles : []);
    if (!selectedHandle && names.length) setSelectedHandle(names[0]);
  };

  useEffect(() => {
    refreshAll().catch((e) => setError(formatApiError(e)));
  }, [search]);

  useEffect(() => {
    if (!selectedHandle) {
      setTickets([]);
      setLatest(null);
      return;
    }
    apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(selectedHandle)}/tickets?limit=100&status=any`)
      .then((r) => setTickets(Array.isArray(r?.items) ? r.items : []))
      .catch(() => setTickets([]));
    apiGet<HandleLatest>(`/api/handles/${encodeURIComponent(selectedHandle)}/latest`).then(setLatest).catch(() => setLatest(null));
  }, [selectedHandle]);

  useEffect(() => {
    const timer = setInterval(() => {
      apiGet<EventsResponse>("/api/events/latest?limit=50")
        .then((res) => {
          const items = Array.isArray(res?.items) ? res.items : [];
          setEvents(items.map((e) => `${e.ts} ${e.level} ${e.handle ?? "-"} ${e.message}`));
        })
        .catch(() => setEvents([]));
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  const startScrape = async (mode: "all" | "one") => {
    try {
      setError(null);
      const payload: { mode: "all" | "one"; handle?: string; rescrape: boolean } = { mode, rescrape: true };
      if (mode === "one" && selectedHandle) payload.handle = selectedHandle;
      const res = await apiPost<{ job_id: string }>("/api/scrape/start", payload);
      const es = new EventSource(`/api/scrape/${res.job_id}/events`);
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
      <p>
        API Base: <code>{apiInfo.browserBase}</code> Proxy: <code>{apiInfo.proxyTarget}</code>
      </p>
      <p>Last API call: {lastApi ? `${lastApi.url} status=${lastApi.status} ms=${lastApi.ms}` : "-"}</p>

      <HandleDropdown selectedHandle={selectedHandle} handles={handles} search={search} onSearchChange={setSearch} onSelect={setSelectedHandle} />

      <div>
        <button onClick={() => startScrape("all")}>Scrape / Re-scrape</button>
        <button onClick={() => startScrape("one")} disabled={!selectedHandle}>
          Scrape Selected Handle
        </button>
      </div>

      <h2>Handles</h2>
      <table>
        <thead>
          <tr>
            <th>Handle</th>
            <th>Status</th>
            <th>Error</th>
            <th>Last Updated</th>
            <th>Ticket Count</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {(handlesMeta ?? []).map((h) => (
            <tr key={h.handle}>
              <td>{h.handle}</td>
              <td>{h.status || "never ran"}</td>
              <td>{h.error_message || h.error || "-"}</td>
              <td>{h.last_updated_utc || h.finished_utc || "-"}</td>
              <td>{h.ticket_count ?? 0}</td>
              <td>
                <button onClick={() => setSelectedHandle(h.handle)}>Select</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      {(tickets ?? []).length === 0 ? (
        <div>
          <p>No tickets in DB.</p>
          <p>
            Status: {latest?.status || "-"} Error: {latest?.error_message || "-"}
          </p>
          <p>
            Artifacts Hint: <code>{latest?.artifacts_hint || "-"}</code>
          </p>
        </div>
      ) : (
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
            {(tickets ?? []).map((t) => (
              <tr key={`${t.ticket_id}-${t.updated_utc}`}>
                <td>{t.ticket_id}</td>
                <td>{t.title || t.subject || "-"}</td>
                <td>{t.status || "-"}</td>
                <td>{t.updated_utc || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Live events (last 50)</h3>
      <pre style={{ maxHeight: 260, overflow: "auto" }}>{(events ?? []).join("\n")}</pre>
    </main>
  );
}
