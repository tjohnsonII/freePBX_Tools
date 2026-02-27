"use client";

import { useEffect, useMemo, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost, apiPostText } from "../lib/api";

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
type AuthStatus = { count: number; domains: string[]; stored_utc: string | null };

const AUTH_ERROR = "Not authenticated. Import cookies in the Web UI (Auth) and retry.";

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
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [cookieJson, setCookieJson] = useState("");
  const [authMessage, setAuthMessage] = useState<string | null>(null);

  const loadHandles = async () => {
    const res = await apiGet<HandleListResponse>(`/api/handles/all?q=${encodeURIComponent(search)}&limit=1000`);
    const names = Array.isArray(res?.items) ? res.items : [];
    setHandles(names);
    if (!selectedHandle && names.length) setSelectedHandle(names[0]);
  };

  const loadAuthStatus = async () => {
    const res = await apiGet<AuthStatus>("/api/auth/status");
    setAuthStatus(res);
  };

  const loadTickets = async (handle: string) => {
    const res = await apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(handle)}/tickets?limit=50&status=any`);
    setTickets(Array.isArray(res?.items) ? res.items : []);
  };

  useEffect(() => {
    loadHandles().catch((e) => setError(formatApiError(e)));
  }, [search]);

  useEffect(() => {
    loadAuthStatus().catch(() => setAuthStatus(null));
  }, []);

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
          if ((status.status === "completed" || status.status === "failed") && selectedHandle) {
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

  const saveImportedCookies = async () => {
    setError(null);
    setAuthMessage(null);
    const trimmed = cookieJson.trim();
    if (!trimmed) {
      setError("Paste cookie data first.");
      return;
    }

    let saved: AuthStatus;
    if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(trimmed);
      } catch {
        setError("Cookies must be valid JSON.");
        return;
      }
      saved = await apiPost<{ ok: boolean } & AuthStatus>("/api/auth/import-cookies", parsed);
    } else {
      saved = await apiPostText<{ ok: boolean } & AuthStatus>("/api/auth/import-cookies", cookieJson, "text/plain");
    }

    await loadAuthStatus();
    setAuthMessage(`Saved ${saved.count} cookies for domains: ${saved.domains.join(", ") || "-"}`);
    setCookieJson("");
    setShowImportModal(false);
  };

  const clearImportedCookies = async () => {
    setError(null);
    setAuthMessage(null);
    await apiPost<{ ok: boolean }>("/api/auth/clear-cookies", {});
    await loadAuthStatus();
    setAuthMessage("Imported cookies cleared.");
  };

  const startScrapeSelected = async () => {
    try {
      if (!selectedHandle) {
        setError("Select a handle first.");
        return;
      }
      setError(null);
      const response = await apiPost<{ job_id: string }>("/api/scrape/start", {
        mode: "one",
        handle: selectedHandle,
        refresh_handles: false,
        rescrape: false,
      });
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
      {authMessage && <p style={{ color: "#165c2d" }}>{authMessage}</p>}
      {showAuthCallout && (
        <div style={{ background: "#fff3cd", padding: "10px", marginBottom: "10px" }}>
          <p style={{ marginTop: 0 }}>{AUTH_ERROR}</p>
          <button onClick={() => setShowImportModal(true)}>Open Auth</button>
        </div>
      )}

      <section style={{ border: "1px solid #ddd", padding: "12px", marginBottom: "14px" }}>
        <h3 style={{ marginTop: 0 }}>Authentication</h3>
        <p>
          Status:{" "}
          <span
            style={{
              background: (authStatus?.count || 0) > 0 ? "#d1fae5" : "#fee2e2",
              color: (authStatus?.count || 0) > 0 ? "#065f46" : "#7f1d1d",
              padding: "4px 8px",
              borderRadius: "999px",
              fontWeight: 600,
            }}
          >
            {(authStatus?.count || 0) > 0 ? "Ready" : "No Imported Cookies"}
          </span>
        </p>
        <p>
          Count: {authStatus?.count ?? 0} | Domains: {(authStatus?.domains || []).join(", ") || "-"} | Stored: {authStatus?.stored_utc || "-"}
        </p>
        <div>
          <button onClick={() => setShowImportModal(true)}>Import Cookies</button>
          <button onClick={clearImportedCookies} style={{ marginLeft: 8 }}>
            Clear Cookies
          </button>
        </div>
      </section>

      <HandleDropdown selectedHandle={selectedHandle} handles={handles} search={search} onSearchChange={setSearch} onSelect={setSelectedHandle} />

      <div>
        <button onClick={startScrapeSelected} disabled={!selectedHandle}>
          Scrape Selected Handle
        </button>
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

      {showImportModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", display: "grid", placeItems: "center" }}>
          <div style={{ background: "#fff", width: "min(900px, 92vw)", padding: 16, borderRadius: 8 }}>
            <h3>Import Cookies</h3>
            <p>Paste JSON or Netscape cookie.txt format.</p>
            <textarea rows={16} style={{ width: "100%" }} value={cookieJson} onChange={(e) => setCookieJson(e.target.value)} />
            <div style={{ marginTop: 8 }}>
              <button onClick={saveImportedCookies}>Save</button>
              <button onClick={() => setShowImportModal(false)} style={{ marginLeft: 8 }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
