"use client";

import { useEffect, useMemo, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost, apiPostText } from "../lib/api";

type Ticket = { ticket_id: string; title?: string; subject?: string; status?: string; updated_utc?: string };
type TicketResponse = { items: Ticket[]; totalCount: number };
type HandleListResponse = { items: string[]; count: number };
type HandleRow = { handle: string; status?: string; error?: string; last_updated_utc?: string; ticket_count?: number };
type AuthStatus = { total: number; domains: { domain: string; count: number }[]; stored_utc: string | null };
type ValidateRow = { domain: string; cookieCount: number; ok: boolean; statusCode?: number | null; finalUrl?: string | null; reason: string; hint: string };
type ValidateResponse = { ok: boolean; results: ValidateRow[] };
type JobResult = { errorType?: string; error?: string; auth?: ValidateResponse; logTail?: string[]; stderrTail?: string[]; errors?: number };
type JobStatus = {
  job_id: string;
  status: string;
  total_handles: number;
  completed: number;
  running: boolean;
  errors: number;
  error_message?: string;
  result?: JobResult;
};
type EventsResponse = { items: { ts: string; level: string; handle?: string; message: string }[] };

function formatApiError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

const VALIDATE_TARGETS = ["secure.123.net", "noc-tickets.123.net", "10.123.203.1"];

export default function HandlesPage() {
  const apiInfo = useMemo(() => apiBaseInfo(), []);
  const [search, setSearch] = useState("");
  const [handles, setHandles] = useState<string[]>([]);
  const [handleRows, setHandleRows] = useState<HandleRow[]>([]);
  const [selectedHandle, setSelectedHandle] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authValidate, setAuthValidate] = useState<ValidateResponse | null>(null);
  const [showEvents, setShowEvents] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [cookieJson, setCookieJson] = useState("");
  const [authMessage, setAuthMessage] = useState<string | null>(null);

  const loadHandles = async () => {
    const res = await apiGet<HandleListResponse>(`/api/handles/all?q=${encodeURIComponent(search)}&limit=1000`);
    const names = Array.isArray(res?.items) ? res.items : [];
    setHandles(names);
    const table = await apiGet<{ items: HandleRow[] }>(`/api/handles?limit=1000&offset=0`);
    setHandleRows(Array.isArray(table?.items) ? table.items : []);
    if (!selectedHandle && names.length) setSelectedHandle(names[0]);
  };

  const loadAuthStatus = async () => setAuthStatus(await apiGet<AuthStatus>("/api/auth/status"));

  const runValidate = async () => {
    const payload = await apiPost<ValidateResponse>("/api/auth/validate", { targets: VALIDATE_TARGETS, timeoutSeconds: 10 });
    setAuthValidate(payload);
    return payload;
  };

  const loadTickets = async (handle: string) => {
    const res = await apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(handle)}/tickets?limit=50&status=any`);
    setTickets(Array.isArray(res?.items) ? res.items : []);
  };

  useEffect(() => { loadHandles().catch((e) => setError(formatApiError(e))); }, [search]);
  useEffect(() => { loadAuthStatus().catch(() => setAuthStatus(null)); }, []);
  useEffect(() => { if (selectedHandle) loadTickets(selectedHandle).catch(() => setTickets([])); else setTickets([]); }, [selectedHandle]);

  useEffect(() => {
    if (!jobId) return;
    const timer = setInterval(() => {
      apiGet<JobStatus>(`/api/scrape/status?job_id=${encodeURIComponent(jobId)}`)
        .then((status) => {
          setJobStatus(status);
          if ((status.status === "completed" || status.status === "failed") && selectedHandle) loadTickets(selectedHandle).catch(() => undefined);
        })
        .catch(() => undefined);
      if (showEvents) {
        apiGet<EventsResponse>(`/api/events/latest?limit=50&job_id=${encodeURIComponent(jobId)}`)
          .then((res) => {
            const items = Array.isArray(res?.items) ? res.items : [];
            setEvents(items.map((e) => `${e.ts} [${e.level}] ${e.handle ?? "-"}: ${e.message}`));
          })
          .catch(() => undefined);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [jobId, selectedHandle, showEvents]);

  const saveImportedCookies = async () => {
    setError(null);
    setAuthMessage(null);
    const trimmed = cookieJson.trim();
    if (!trimmed) return setError("Paste cookie data first.");

    const saved = trimmed.startsWith("[") || trimmed.startsWith("{")
      ? await apiPost<{ message?: string }>("/api/auth/import-cookies", JSON.parse(trimmed))
      : await apiPostText<{ message?: string }>("/api/auth/import-cookies", cookieJson, "text/plain");

    await loadAuthStatus();
    setAuthMessage(saved.message || "Cookies imported.");
    setCookieJson("");
    setShowImportModal(false);
  };

  const clearImportedCookies = async () => {
    setError(null);
    setAuthMessage(null);
    await apiPost<{ ok: boolean }>("/api/auth/clear-cookies", {});
    await loadAuthStatus();
    setAuthValidate(null);
    setAuthMessage("Imported cookies cleared.");
  };

  const startScrapeSelected = async () => {
    try {
      if (!selectedHandle) return setError("Select a handle first.");
      setError(null);
      const validation = await runValidate();
      if (!validation.ok) {
        setError("Auth validation failed. Review details below and fix cookies before scraping.");
        return;
      }
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

  const jobError = jobStatus?.result?.error || jobStatus?.error_message;

  return (
    <main>
      <p>API Base: <code>{apiInfo.browserBase}</code> Proxy: <code>{apiInfo.proxyTarget}</code></p>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      {authMessage && <p style={{ color: "#165c2d" }}>{authMessage}</p>}

      <section style={{ border: "1px solid #ddd", padding: 12, marginBottom: 14 }}>
        <h3 style={{ marginTop: 0 }}>Authentication</h3>
        <p>Count: {authStatus?.total ?? 0} | Domains: {(authStatus?.domains || []).map((d) => `${d.domain} (${d.count})`).join(", ") || "-"}</p>
        <button onClick={() => setShowImportModal(true)}>Import Cookies</button>
        <button onClick={clearImportedCookies} style={{ marginLeft: 8 }}>Clear Cookies</button>
        <button onClick={runValidate} style={{ marginLeft: 8 }}>Validate Auth</button>
      </section>

      <HandleDropdown selectedHandle={selectedHandle} handles={handles} search={search} onSearchChange={setSearch} onSelect={setSelectedHandle} />
      <div><button onClick={startScrapeSelected} disabled={!selectedHandle}>Scrape Selected Handle</button></div>

      {jobStatus && (
        <section>
          <h3>Job status</h3>
          <p>Job: {jobStatus.job_id} | Status: {jobStatus.status} | Progress: {jobStatus.completed}/{jobStatus.total_handles} | Errors: {jobStatus.errors}</p>
        </section>
      )}

      {(jobStatus?.status === "failed" || authValidate?.ok === false) && (
        <section style={{ border: "2px solid #dc2626", background: "#fee2e2", padding: 12, marginTop: 12 }}>
          <h3 style={{ marginTop: 0 }}>Scrape failure details</h3>
          <p><strong>Summary:</strong> {jobError || "Auth validation failed"}</p>
          <table>
            <thead><tr><th>Domain</th><th>Cookies</th><th>Status</th><th>Final URL</th><th>Reason</th><th>Hint</th></tr></thead>
            <tbody>
              {((jobStatus?.result?.auth?.results || authValidate?.results || [])).map((item) => (
                <tr key={item.domain}>
                  <td>{item.domain}</td><td>{item.cookieCount}</td><td>{item.statusCode ?? "-"}</td><td>{item.finalUrl || "-"}</td><td>{item.reason}</td><td>{item.hint}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <details><summary>logTail</summary><pre>{(jobStatus?.result?.logTail || []).join("\n") || "-"}</pre></details>
          <details><summary>stderrTail</summary><pre>{(jobStatus?.result?.stderrTail || []).join("\n") || "-"}</pre></details>
          <button onClick={() => setShowEvents((v) => !v)}>{showEvents ? "Hide" : "Open"} latest scrape_job_events</button>
        </section>
      )}

      {showEvents && <pre style={{ maxHeight: 260, overflow: "auto" }}>{events.join("\n")}</pre>}

      <section style={{ marginTop: 14 }}>
        <h3>Handles</h3>
        <table><thead><tr><th>Handle</th><th>Status</th><th>Error</th><th>Last Updated</th><th>Ticket Count</th><th>Actions</th></tr></thead><tbody>
          {handleRows.map((row) => (
            <tr key={row.handle}><td>{row.handle}</td><td>{row.status || "-"}</td><td>{row.error || "-"}</td><td>{row.last_updated_utc || "-"}</td><td>{row.ticket_count ?? 0}</td><td><button onClick={() => setSelectedHandle(row.handle)}>Select</button></td></tr>
          ))}
        </tbody></table>
      </section>

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      <table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Updated</th></tr></thead><tbody>
        {tickets.map((t) => (<tr key={`${t.ticket_id}-${t.updated_utc}`}><td>{t.ticket_id}</td><td>{t.title || t.subject || "-"}</td><td>{t.status || "-"}</td><td>{t.updated_utc || "-"}</td></tr>))}
      </tbody></table>

      {showImportModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", display: "grid", placeItems: "center" }}>
          <div style={{ background: "#fff", width: "min(900px, 92vw)", padding: 16, borderRadius: 8 }}>
            <h3>Import Cookies</h3>
            <p>Paste JSON or Netscape cookie.txt format.</p>
            <textarea rows={16} style={{ width: "100%" }} value={cookieJson} onChange={(e) => setCookieJson(e.target.value)} />
            <div style={{ marginTop: 8 }}><button onClick={saveImportedCookies}>Save</button><button onClick={() => setShowImportModal(false)} style={{ marginLeft: 8 }}>Cancel</button></div>
          </div>
        </div>
      )}
    </main>
  );
}
