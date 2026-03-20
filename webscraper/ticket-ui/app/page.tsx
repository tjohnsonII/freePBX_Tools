"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import HandleDropdown from "./components/HandleDropdown";
import OrchestrationDashboard from "./components/OrchestrationDashboard";
import { ApiRequestError, apiBaseInfo, apiGet, apiPost, apiPostForm } from "../lib/api";
import { BrowserSyncTarget, syncAuthFromBrowser } from "../lib/authBrowserSync";

type Ticket = { ticket_id: string; title?: string; subject?: string; status?: string; updated_utc?: string };
type TicketResponse = { items: Ticket[]; totalCount: number };
type HandleListResponse = { items: string[]; count: number };
type HandleRow = { handle: string; status?: string; error?: string; last_updated_utc?: string; ticket_count?: number };
type AuthStatus = {
  cookie_count: number;
  domains: string[];
  last_imported: number | null;
  source: string;
  authenticated?: boolean;
  mode?: string;
  detail?: string;
  last_check_ts?: string | null;
  last_error?: string | null;
  profile_dir?: string | null;
  suggestion?: string | null;
  active_source?: string | null;
  source_context?: Record<string, unknown> | null;
  last_import_method_attempted?: string | null;
  last_import_result?: { result?: string; source?: string; cookie_count?: number; overwritten_from?: string | null } | null;
  last_validation_result?: { authenticated?: boolean; reason?: string | null; source?: string | null } | null;
};
type AuthSeedResponse = { ok: boolean; mode_used: "auto" | "disk" | "cdp"; details?: Record<string, unknown>; next_step_if_failed?: string | null; cookie_count?: number };
type ChromeProfilesResponse = { ok: boolean; profiles: string[]; preferred: string | null };
type ValidateRow = { url: string; status?: number | null; final_url?: string | null; ok: boolean; hint?: string | null };
type ValidateResponse = { ok?: boolean;
  authenticated: boolean; reason?: string;
  reasons?: Array<Record<string, unknown>>; domains: string[]; cookie_count: number; checks: ValidateRow[] };
type JobResult = { errorType?: string; error?: string; auth?: ValidateResponse; logTail?: string[]; stderrTail?: string[]; errors?: number };
type JobStatus = { job_id: string; status: string; total_handles: number; completed: number; completed_handles?: number; current_handle?: string | null; per_handle_status?: Record<string, string>; running: boolean; errors: number; error_message?: string; result?: JobResult };
type EventsResponse = { items: { ts: string; level: string; handle?: string; message: string }[] };
const FALLBACK_TICKETING_TARGET_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi";
const TICKETING_TARGET_URL = process.env.NEXT_PUBLIC_TICKETING_TARGET_URL || process.env.NEXT_PUBLIC_TICKETING_LOGIN_URL || FALLBACK_TICKETING_TARGET_URL;
const AUTH_SOURCE_LABELS: Record<string, string> = {
  none: "none",
  paste: "paste",
  chrome_profile: "chrome_profile",
  edge_profile: "edge_profile",
  isolated_profile: "isolated_profile",
  cdp_debug_chrome: "cdp_debug_chrome",
};
const AUTH_LEGEND_ROWS = [
  "none = no auth loaded",
  "paste = manually pasted cookies",
  "chrome_profile = cookies imported from normal Chrome profile",
  "edge_profile = cookies imported from normal Edge profile",
  "isolated_profile = cookies imported from launcher-created isolated browser",
  "cdp_debug_chrome = cookies imported from live debug Chrome via CDP on 9222",
];

function formatApiError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.detail || error.message;
  return error instanceof Error ? error.message : String(error);
}

function formatEndpointError(endpoint: string, error: unknown): string {
  if (error instanceof ApiRequestError) {
    const status = error.status ?? "n/a";
    return `${endpoint} failed (status=${status}): ${error.detail || error.message}`;
  }
  return `${endpoint} failed: ${formatApiError(error)}`;
}


export default function HandlesPage() {
  const apiInfo = useMemo(() => apiBaseInfo(), []);
  const [search, setSearch] = useState("");
  const [handles, setHandles] = useState<string[]>([]);
  const [handleRows, setHandleRows] = useState<HandleRow[]>([]);
  const [selectedHandle, setSelectedHandle] = useState("");
  const [selectedHandles, setSelectedHandles] = useState<Set<string>>(new Set());
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authValidate, setAuthValidate] = useState<ValidateResponse | null>(null);
  const [showEvents, setShowEvents] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [cookieText, setCookieText] = useState("");
  const [cookieFileName, setCookieFileName] = useState("");
  const [cookieFile, setCookieFile] = useState<File | null>(null);
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const [seedModeUsed, setSeedModeUsed] = useState<string | null>(null);
  const [authStatusError, setAuthStatusError] = useState<string | null>(null);
  const [chromeProfiles, setChromeProfiles] = useState<string[]>([]);
  const [chromeProfileDir, setChromeProfileDir] = useState<string>("Profile 1");
  const [browserSyncDomain, setBrowserSyncDomain] = useState("secure.123.net");
  const [browserSyncLoading, setBrowserSyncLoading] = useState<BrowserSyncTarget | null>(null);
  const [syncConfirmBrowser, setSyncConfirmBrowser] = useState<BrowserSyncTarget | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const enableLocalAuthSync = process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_ENABLE_LOCAL_AUTH_SYNC === "1";

  const hasSecureDomain = (authStatus?.domains || []).some((domain) => {
    const normalized = domain.replace(/^\./, "").toLowerCase();
    return normalized === "secure.123.net" || normalized.endsWith(".secure.123.net") || normalized === "123.net" || normalized.endsWith(".123.net");
  });
  const wrongDomainLoaded = (authStatus?.cookie_count || 0) > 0 && !hasSecureDomain;
  const isAuthenticated = authStatus?.authenticated !== false;
  const scrapeDisabledReason = !isAuthenticated
    ? "Not authenticated: worker is paused until login completes."
    : (wrongDomainLoaded ? "Wrong cookie domain set loaded" : "");
  const activeAuthSource = authStatus?.active_source || authStatus?.source || "none";
  const currentSource = AUTH_SOURCE_LABELS[activeAuthSource] || activeAuthSource;
  const sourceContext = authStatus?.source_context || {};
  const authWarnings = useMemo(() => {
    const warnings: string[] = [];
    if (currentSource !== "none" && currentSource !== "cdp_debug_chrome") {
      warnings.push(`Debug Chrome flow note: currently authenticated from ${currentSource}; Seed Auth may replace it with cdp_debug_chrome.`);
    }
    if ((sourceContext?.cdp_reachable as boolean | undefined) && currentSource !== "cdp_debug_chrome") {
      warnings.push("Debug Chrome is live on 9222, but Sync from Chrome targets local profile Profile 1.");
    }
    if (currentSource === "paste") {
      warnings.push("Paste Cookies is currently active; a successful browser import will replace this state.");
    }
    if (currentSource !== "isolated_profile") {
      warnings.push("Launch Login (isolated) uses a different browser profile than Chrome Profile 1.");
    }
    return warnings;
  }, [currentSource, sourceContext]);


  const filteredHandles = useMemo(() => new Set(handles.map((item) => item.toUpperCase())), [handles]);
  const filteredHandleRows = useMemo(() => handleRows.filter((row) => filteredHandles.has(row.handle.toUpperCase())), [filteredHandles, handleRows]);
  const availableChromeProfiles = chromeProfiles.length ? chromeProfiles : ["Profile 1", "Default"];
  const selectedCount = selectedHandles.size;
  const allFilteredSelected = filteredHandleRows.length > 0 && filteredHandleRows.every((row) => selectedHandles.has(row.handle));
  const someFilteredSelected = filteredHandleRows.some((row) => selectedHandles.has(row.handle));

  const loadHandles = async () => {
    let loadedNames: string[] = [];
    try {
      const endpoint = `/api/handles/all?q=${encodeURIComponent(search)}&limit=1000`;
      const res = await apiGet<HandleListResponse>(endpoint);
      const names = Array.isArray(res?.items) ? res.items : [];
      loadedNames = names;
      setHandles(names);
    } catch (error) {
      setHandles([]);
      setError(formatEndpointError("/api/handles/all", error));
    }
    try {
      const endpoint = "/api/handles?limit=1000&offset=0";
      const table = await apiGet<{ items: HandleRow[] }>(endpoint);
      setHandleRows(Array.isArray(table?.items) ? table.items : []);
    } catch (error) {
      setHandleRows([]);
      setError(formatEndpointError("/api/handles", error));
    }
    if (!selectedHandle && loadedNames.length) setSelectedHandle(loadedNames[0]);
  };

  const loadAuthStatus = async () => {
    try {
      setAuthStatus(await apiGet<AuthStatus>("/api/auth/status"));
      setAuthStatusError(null);
    } catch (e) {
      setAuthStatus({ cookie_count: 0, domains: [], last_imported: null, source: "none", authenticated: false });
      setAuthStatusError(`Auth status unavailable: ${formatApiError(e)}`);
    }
  };

  const runValidate = async () => {
    const payload = await apiGet<ValidateResponse>("/api/auth/validate?domain=secure.123.net&timeout_seconds=10");
    setAuthValidate(payload);
    await loadAuthStatus();
    return payload;
  };

  const loadTickets = async (handle: string) => {
    const res = await apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(handle)}/tickets?limit=50&status=any`);
    setTickets(Array.isArray(res?.items) ? res.items : []);
  };

  const loadChromeProfiles = async () => {
    try {
      const res = await apiGet<ChromeProfilesResponse>("/api/auth/chrome_profiles");
      setChromeProfiles(res.profiles || []);
      if (res.preferred) setChromeProfileDir(res.preferred);
    } catch {
      setChromeProfiles([]);
    }
  };

  useEffect(() => { loadHandles().catch((e) => setError(formatApiError(e))); }, [search]);
  useEffect(() => { loadAuthStatus().catch(() => undefined); loadChromeProfiles().catch(() => undefined); }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      loadAuthStatus().catch(() => undefined);
    }, 4000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => { if (selectedHandle) loadTickets(selectedHandle).catch(() => setTickets([])); else setTickets([]); }, [selectedHandle]);

  useEffect(() => {
    setSelectedHandles((prev) => {
      const available = new Set(handleRows.map((row) => row.handle));
      const next = new Set(Array.from(prev).filter((handle) => available.has(handle)));
      return next.size === prev.size ? prev : next;
    });
  }, [handleRows]);

  useEffect(() => {
    if (!jobId) return;
    const timer = setInterval(() => {
      apiGet<JobStatus>(`/api/scrape/status?job_id=${encodeURIComponent(jobId)}`)
        .then((status) => {
          setJobStatus(status);
          loadHandles().catch(() => undefined);
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

  const importCookieText = async () => {
    const text = cookieText.trim();
    if (!text) return setError("Paste cookie data first.");
    setError(null);
    setAuthMessage(null);
    try {
      await apiPost<AuthStatus & { total_kept: number }>("/api/auth/import", { text });
      await loadAuthStatus();
      await runValidate();
      setAuthMessage("Cookie text imported.");
      setCookieText("");
      setShowImportModal(false);
    } catch (e) {
      setError(formatApiError(e));
    }
  };

  const importCookieFile = async () => {
    if (!cookieFile) return setError("Select a JSON or TXT cookie file first.");
    setError(null);
    setAuthMessage(null);
    const fd = new FormData();
    fd.append("file", cookieFile);
    try {
      await apiPostForm<AuthStatus & { total_kept: number }>("/api/auth/import-file", fd);
      await loadAuthStatus();
      await runValidate();
      setAuthMessage(`Imported ${cookieFile.name}.`);
      setCookieFile(null);
      setCookieFileName("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e) {
      setError(formatApiError(e));
    }
  };

  const launchLoginIsolated = async () => {
    setError(null);
    setAuthMessage(null);
    try {
      const response = await apiPost<{ ok: boolean; browser: string; profile_dir: string; command?: string[]; started?: boolean }>("/api/auth/launch-browser", {
        url: TICKETING_TARGET_URL,
        profile: "ticketing",
        new_window: true,
      });
      const commandText = Array.isArray(response.command) ? response.command.join(" ") : "";
      if (response.started) {
        setAuthMessage("Opened isolated browser profile for login.");
      } else {
        setAuthMessage(`Could not auto-launch browser. Run manually: ${commandText || "see server logs"}`);
      }
    } catch (e) {
      const message = formatApiError(e);
      setError(`Launch Login failed: ${message}`);
      window.open(TICKETING_TARGET_URL, "_blank", "noopener,noreferrer");
    }
  };

  const launchAuthenticateHelper = async () => {
    await launchLoginIsolated();
    await loadAuthStatus();
  };


  const launchLoginSeeded = async () => {
    setError(null);
    setAuthMessage(null);
    setSeedModeUsed(null);
    try {
      const result = await apiPost<AuthSeedResponse>("/api/auth/seed", {
        mode: "auto",
        chrome_profile_dir: chromeProfileDir,
        seed_domains: ["secure.123.net", "123.net"],
        cdp_port: 9222,
      });
      setSeedModeUsed(result.mode_used || "auto");
      if (!result.ok) {
        setError(result.next_step_if_failed || "Auth seed failed.");
        return;
      }
      await loadAuthStatus();
      setAuthMessage(`Seeded auth cookies using ${result.mode_used.toUpperCase()} mode.`);
    } catch (e) {
      const message = formatApiError(e);
      setError(`Launch seeded login failed: ${message}`);
    }
  };


  const launchDebugChrome = async () => {
    setError(null);
    try {
      await apiPost("/api/auth/launch_debug_chrome", { cdp_port: 9222, profile_name: "Default" });
      setAuthMessage("Launched debug Chrome on port 9222.");
    } catch (e) {
      setError(formatApiError(e));
    }
  };

  const restartApi = async () => {
    setError(null);
    try {
      await apiPost("/api/admin/restart", {});
      setAuthMessage("API restart signal sent. Reconnecting in 3s…");
      setTimeout(loadAuthStatus, 3000);
    } catch (e) {
      setError(`Restart failed: ${e}`);
    }
  };

  const clearImportedCookies = async () => {
    setError(null);
    setAuthMessage(null);
    await apiPost<AuthStatus>("/api/auth/clear", {});
    await loadAuthStatus();
    setAuthValidate(null);
    setAuthMessage("Imported cookies cleared.");
  };

  const requestBrowserSync = (browser: BrowserSyncTarget) => {
    if (!enableLocalAuthSync) return;
    setSyncConfirmBrowser(browser);
  };

  const runBrowserSync = async () => {
    if (!syncConfirmBrowser) return;
    const domain = browserSyncDomain.trim() || "secure.123.net";
    const profile = chromeProfileDir || "Default";

    setSyncConfirmBrowser(null);
    setError(null);
    setAuthMessage(null);
    setBrowserSyncLoading(syncConfirmBrowser);

    try {
      const response = await syncAuthFromBrowser({ browser: syncConfirmBrowser, domain, profile });
      await loadAuthStatus();
      await runValidate();
      const importedCount = response.imported_count ?? 0;
      const targetDomain = response.domain || domain;
      setAuthMessage(`Browser sync succeeded. Imported ${importedCount} cookies for ${targetDomain}.`);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBrowserSyncLoading(null);
    }
  };

  const onPickFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setCookieFile(file);
    setCookieFileName(file?.name || "");
  };

  const startScrapeSelected = async () => {
    try {
      if (!selectedHandle) return setError("Select a handle first.");
      setError(null);
      if ((authStatus?.cookie_count || 0) > 0) {
        await runValidate();
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

  const toggleHandleSelection = (handle: string) => {
    setSelectedHandles((prev) => {
      const next = new Set(prev);
      if (next.has(handle)) next.delete(handle);
      else next.add(handle);
      return next;
    });
  };

  const selectAllFiltered = () => {
    setSelectedHandles((prev) => {
      const next = new Set(prev);
      for (const row of filteredHandleRows) next.add(row.handle);
      return next;
    });
  };

  const clearSelection = () => setSelectedHandles(new Set());

  const toggleSelectAllFiltered = () => {
    if (allFilteredSelected) {
      setSelectedHandles((prev) => {
        const next = new Set(prev);
        for (const row of filteredHandleRows) next.delete(row.handle);
        return next;
      });
      return;
    }
    selectAllFiltered();
  };

  const startScrapeSelectedBatch = async () => {
    if (selectedCount === 0) return;
    try {
      setError(null);
      if ((authStatus?.cookie_count || 0) > 0) {
        await runValidate();
      }
      const handlesToScrape = Array.from(selectedHandles);
      const response = await apiPost<{ job_id: string }>("/api/scrape/handles", {
        handles: handlesToScrape,
        mode: "normal",
      });
      setJobId(response.job_id);
      setJobStatus(null);
      setEvents([]);
      clearSelection();
    } catch (e) {
      setError(formatApiError(e));
    }
  };

  const jobError = jobStatus?.result?.error || jobStatus?.error_message;

  return (
    <main>
      <OrchestrationDashboard />
      <p>API Base: <code>{apiInfo.browserBase}</code> Proxy: <code>{apiInfo.proxyTarget}</code></p>
      {!isAuthenticated ? (
        <div style={{ background: "#fff7ed", border: "1px solid #fdba74", color: "#9a3412", padding: 10, marginBottom: 12 }}>
          <strong>Not authenticated.</strong> Scraping worker is paused. Click <strong>Authenticate</strong> to log in.
          <button onClick={launchAuthenticateHelper} style={{ marginLeft: 10 }}>Authenticate</button>
          {authStatus?.last_error ? <div style={{ marginTop: 6 }}>Last error: {authStatus.last_error}</div> : null}
        </div>
      ) : null}
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      {authMessage && <p style={{ color: "#165c2d" }}>{authMessage}</p>}
      {seedModeUsed && <p>Mode used: <strong>{seedModeUsed}</strong></p>}
      {authStatusError && <p style={{ color: "#a16207" }}>{authStatusError}</p>}

      <section style={{ border: "1px solid #ddd", padding: 12, marginBottom: 14 }}>
        <h3 style={{ marginTop: 0 }}>Authentication</h3>
        <section style={{ background: "#f8fafc", border: "1px solid #cbd5e1", padding: 10, marginBottom: 10 }}>
          <h4 style={{ margin: "0 0 8px" }}>Auth help: sources + recommended flow</h4>
          <p style={{ margin: "0 0 8px" }}><strong>Auth legend</strong></p>
          <ul style={{ marginTop: 0 }}>
            {AUTH_LEGEND_ROWS.map((item) => <li key={item}><code>{item}</code></li>)}
          </ul>
          <p style={{ marginBottom: 6 }}><strong>Recommended auth flows</strong></p>
          <pre style={{ whiteSpace: "pre-wrap", background: "#ffffff", border: "1px solid #e2e8f0", padding: 8 }}>
{`Flow A — Debug Chrome (recommended for dev)
1) Launch Debug Chrome
2) Confirm http://127.0.0.1:9222/json/version is reachable
3) Log into secure.123.net in that debug Chrome window
4) Click Seed Auth (auto)
5) Click Validate Auth

Flow B — Isolated Login
1) Launch Login (isolated)
2) Log into secure.123.net in that isolated browser
3) Import auth from isolated profile (or Seed Auth / Sync as needed)
4) Click Validate Auth

Flow C — Local Browser Profile Sync
1) Select browser/profile
2) Click Sync from Chrome or Sync from Edge
3) Click Validate Auth`}
          </pre>
          <p style={{ marginBottom: 6 }}><strong>Sequence diagram (text)</strong></p>
          <pre style={{ whiteSpace: "pre-wrap", background: "#ffffff", border: "1px solid #e2e8f0", padding: 8 }}>
{`Debug Chrome flow:
User -> Launch Debug Chrome
Browser(9222) -> Login to secure.123.net
User -> Seed Auth (auto)
Ticket API -> CDP connect 127.0.0.1:9222 -> read cookies -> store auth state
User -> Validate Auth
Ticket API -> probe secure.123.net with imported cookies -> authenticated true/false

Isolated flow:
User -> Launch Login (isolated)
Isolated Browser Profile -> Login to secure.123.net
Ticket API -> read isolated profile cookies -> store auth state
User -> Validate Auth`}
          </pre>
          <p style={{ marginBottom: 6 }}><strong>Log-driven diagnosis (run one flow at a time)</strong></p>
          <pre style={{ whiteSpace: "pre-wrap", background: "#ffffff", border: "1px solid #e2e8f0", padding: 8 }}>
{`Do not mix Flow A/B/C in the same test run.
After each single flow, immediately capture the last 120 lines and compare outputs.

Live tail of ticket API log:
Get-Content E:\\DevTools\\freepbx-tools\\var\\web-app-launcher\\logs\\webscraper_ticket_api.log -Wait -Tail 80

Capture last 120 lines after one flow:
Get-Content E:\\DevTools\\freepbx-tools\\var\\web-app-launcher\\logs\\webscraper_ticket_api.log -Tail 120

Save per-flow snapshots:
Flow A: Get-Content E:\\DevTools\\freepbx-tools\\var\\web-app-launcher\\logs\\webscraper_ticket_api.log -Tail 120 > flowA.txt
Flow B: Get-Content E:\\DevTools\\freepbx-tools\\var\\web-app-launcher\\logs\\webscraper_ticket_api.log -Tail 120 > flowB.txt
Flow C: Get-Content E:\\DevTools\\freepbx-tools\\var\\web-app-launcher\\logs\\webscraper_ticket_api.log -Tail 120 > flowC.txt

Live tail of ticket UI log:
Get-Content E:\\DevTools\\freepbx-tools\\var\\web-app-launcher\\logs\\webscraper_ticket_ui.log -Wait -Tail 60

Filter auth-related API lines:
Select-String -Path E:\\DevTools\\freepbx-tools\\var\\web-app-launcher\\logs\\webscraper_ticket_api.log -Pattern "auth_validate|Cookie import requested|route_hit|CDP|missing_cookie|redirected_to_login|isolated|debuggable|seed|import_from_browser"`}
          </pre>
        </section>
        {authWarnings.length > 0 ? (
          <div style={{ border: "1px solid #f59e0b", background: "#fffbeb", padding: 10, marginBottom: 10 }}>
            <strong>Auth flow warnings</strong>
            <ul style={{ marginBottom: 0 }}>
              {authWarnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          </div>
        ) : null}
        <p>Count: {authStatus?.cookie_count ?? 0} | Domains: {(authStatus?.domains || []).join(", ") || "-"}</p>
        <p>Active source: <strong>{currentSource}</strong> | DB source: {authStatus?.source || "none"} | Last Loaded: {authStatus?.last_imported || "-"}</p>
        <p>Last import attempt: {authStatus?.last_import_method_attempted || "-"} | Last import result: {authStatus?.last_import_result?.result || "-"}</p>
        <p>Last validation result: {authStatus?.last_validation_result?.authenticated === undefined ? "-" : String(Boolean(authStatus?.last_validation_result?.authenticated))} ({authStatus?.last_validation_result?.reason || "-"})</p>
        <p>Import context: browser={(sourceContext?.browser as string) || "-"} profile={(sourceContext?.profile as string) || "-"} cdp_port={(sourceContext?.cdp_port as number) || "-"} attempted_sources={JSON.stringify((sourceContext?.attempted_sources as unknown[]) || [])}</p>
        <p>Authenticated: {authStatus?.authenticated === false ? "false" : "true"} | Mode: {authStatus?.mode || "-"} | Last check: {authStatus?.last_check_ts || "-"}</p>
        {wrongDomainLoaded ? <p style={{ color: "#b91c1c", fontWeight: 600 }}>Wrong cookie domain set loaded; must include secure.123.net</p> : null}
                <input ref={fileInputRef} type="file" accept=".json,.txt" onChange={onPickFile} style={{ display: "none" }} />
        <div style={{ marginTop: 8 }}>
          <button onClick={() => fileInputRef.current?.click()}>Import Cookies</button>
          <button onClick={importCookieFile} style={{ marginLeft: 8 }}>Upload Selected File</button>
          <button onClick={() => setShowImportModal(true)} style={{ marginLeft: 8 }}>Paste Cookies</button>
          <button onClick={launchLoginIsolated} style={{ marginLeft: 8 }}>Launch Login (isolated)</button>
          <label style={{ marginLeft: 8 }}>Chrome Profile
            <select value={chromeProfileDir} onChange={(e) => setChromeProfileDir(e.target.value)} style={{ marginLeft: 6 }}>
              {availableChromeProfiles.map((profile) => (
                <option key={profile} value={profile}>{profile}</option>
              ))}
            </select>
          </label>
          <button onClick={launchLoginSeeded} style={{ marginLeft: 8 }}>Seed Auth (auto)</button>
          <button onClick={launchDebugChrome} style={{ marginLeft: 8 }}>Launch Debug Chrome</button>
          <button onClick={clearImportedCookies} style={{ marginLeft: 8 }}>Clear Cookies</button>
          <button onClick={runValidate} disabled={wrongDomainLoaded} style={{ marginLeft: 8 }}>Validate Auth</button>
          <button onClick={restartApi} style={{ marginLeft: 8 }}>Restart API</button>
        </div>
        {cookieFileName ? <p style={{ marginTop: 6 }}>Selected file: {cookieFileName}</p> : null}

        {enableLocalAuthSync ? (
          <section style={{ marginTop: 12, borderTop: "1px solid #ddd", paddingTop: 10 }}>
            <h4 style={{ margin: "0 0 8px" }}>Local Browser Sync (Dev Only)</h4>
            <p style={{ margin: "0 0 8px", color: "#a16207" }}>Imports cookies from your local browser profile for local development workflows only.</p>
            <label>
              Domain
              <input
                value={browserSyncDomain}
                onChange={(e) => setBrowserSyncDomain(e.target.value)}
                placeholder="secure.123.net"
                style={{ marginLeft: 6 }}
              />
            </label>
            <label style={{ marginLeft: 10 }}>
              Profile
              <select value={chromeProfileDir} onChange={(e) => setChromeProfileDir(e.target.value)} style={{ marginLeft: 6 }}>
                {availableChromeProfiles.map((profile) => (
                  <option key={profile} value={profile}>{profile}</option>
                ))}
              </select>
            </label>
            <div style={{ marginTop: 8 }}>
              <button onClick={() => requestBrowserSync("chrome")} disabled={browserSyncLoading !== null}>
                {browserSyncLoading === "chrome" ? "Syncing Chrome..." : "Sync from Chrome"}
              </button>
              <button onClick={() => requestBrowserSync("edge")} disabled={browserSyncLoading !== null} style={{ marginLeft: 8 }}>
                {browserSyncLoading === "edge" ? "Syncing Edge..." : "Sync from Edge"}
              </button>
            </div>
          </section>
        ) : null}
      </section>

      <HandleDropdown selectedHandle={selectedHandle} handles={handles} search={search} onSearchChange={setSearch} onSelect={setSelectedHandle} />
      <div>
        <button onClick={startScrapeSelected} disabled={!selectedHandle || !!scrapeDisabledReason} title={scrapeDisabledReason || undefined}>Scrape Selected Handle</button>
        {authValidate?.authenticated === false ? <span style={{ marginLeft: 8, color: "#a16207" }}>Auth looks invalid, but scrape is still allowed and may fail with details below.</span> : null}
      </div>

      <section style={{ marginTop: 10, border: "1px solid #ddd", padding: 10 }}>
        <strong>Selection</strong>
        <div style={{ marginTop: 6 }}>
          <button onClick={selectAllFiltered} disabled={filteredHandleRows.length === 0}>Select All</button>
          <button onClick={clearSelection} style={{ marginLeft: 8 }} disabled={selectedCount === 0}>Clear Selection</button>
          <button onClick={startScrapeSelectedBatch} style={{ marginLeft: 8 }} disabled={selectedCount === 0 || !!scrapeDisabledReason} title={scrapeDisabledReason || undefined}>Scrape Selected ({selectedCount})</button>
          <span style={{ marginLeft: 8 }}>Selected: {selectedCount}</span>
        </div>
        {selectedCount > 50 ? <p style={{ color: "#a16207", marginTop: 8 }}>You’re about to queue {selectedCount} handles; this may take a while.</p> : null}
      </section>

      {jobStatus && (
        <section>
          <h3>Job status</h3>
          <p>
            Job: {jobStatus.job_id} | Status: {jobStatus.status} | Progress: {jobStatus.completed}/{jobStatus.total_handles} | Errors: {jobStatus.errors}
            {jobStatus.current_handle ? ` | Current: ${jobStatus.current_handle}` : ""}
          </p>
        </section>
      )}

      {(jobStatus?.status === "failed" || authValidate?.authenticated === false) && (
        <section style={{ border: "2px solid #dc2626", background: "#fee2e2", padding: 12, marginTop: 12 }}>
          <h3 style={{ marginTop: 0 }}>Scrape failure details</h3>
          <p><strong>Summary:</strong> {jobError || "Auth validation failed"}</p>
          <table>
            <thead><tr><th>URL</th><th>Status</th><th>Final URL</th><th>OK</th><th>Hint</th></tr></thead>
            <tbody>{((jobStatus?.result?.auth?.checks || authValidate?.checks || [])).map((item) => (<tr key={item.url}><td>{item.url}</td><td>{item.status ?? "-"}</td><td>{item.final_url || "-"}</td><td>{item.ok ? "yes" : "no"}</td><td>{item.hint || "-"}</td></tr>))}</tbody>
          </table>
          <details><summary>logTail</summary><pre>{(jobStatus?.result?.logTail || []).join("\n") || "-"}</pre></details>
          <details><summary>stderrTail</summary><pre>{(jobStatus?.result?.stderrTail || []).join("\n") || "-"}</pre></details>
          <button onClick={() => setShowEvents((v) => !v)}>{showEvents ? "Hide" : "Open"} latest scrape_job_events</button>
        </section>
      )}

      {showEvents && <pre style={{ maxHeight: 260, overflow: "auto" }}>{events.join("\n")}</pre>}

      <section style={{ marginTop: 14 }}>
        <h3>Handles</h3>
        <table><thead><tr><th><input type="checkbox" checked={allFilteredSelected} ref={(el) => { if (el) el.indeterminate = !allFilteredSelected && someFilteredSelected; }} onChange={toggleSelectAllFiltered} /></th><th>Handle</th><th>Status</th><th>Error</th><th>Last Updated</th><th>Ticket Count</th><th>Actions</th></tr></thead><tbody>
          {filteredHandleRows.map((row) => (<tr key={row.handle}><td><input type="checkbox" checked={selectedHandles.has(row.handle)} onChange={() => toggleHandleSelection(row.handle)} /></td><td>{row.handle}</td><td>{row.status || "-"}</td><td>{row.error || (row.status === "error" ? "Unknown error" : "-")}</td><td>{row.last_updated_utc || "-"}</td><td>{row.ticket_count ?? 0}</td><td><button onClick={() => setSelectedHandle(row.handle)}>Select</button></td></tr>))}
        </tbody></table>
      </section>

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      <table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Updated</th></tr></thead><tbody>
        {tickets.map((t) => (<tr key={`${t.ticket_id}-${t.updated_utc}`}><td>{t.ticket_id}</td><td>{t.title || t.subject || "-"}</td><td>{t.status || "-"}</td><td>{t.updated_utc || "-"}</td></tr>))}
      </tbody></table>

      {showImportModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", display: "grid", placeItems: "center" }}>
          <div style={{ background: "#fff", width: "min(900px, 92vw)", padding: 16, borderRadius: 8 }}>
            <h3>Paste Cookies/Auth</h3>
            <p>Paste cookie header, Netscape cookie text, or JSON cookie export.</p>
            <textarea rows={16} style={{ width: "100%" }} value={cookieText} onChange={(e) => setCookieText(e.target.value)} />
            <div style={{ marginTop: 8 }}><button onClick={importCookieText}>Import Text</button><button onClick={() => setShowImportModal(false)} style={{ marginLeft: 8 }}>Cancel</button></div>
          </div>
        </div>
      )}

      {syncConfirmBrowser && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", display: "grid", placeItems: "center" }}>
          <div style={{ background: "#fff", width: "min(760px, 92vw)", padding: 16, borderRadius: 8 }}>
            <h3>Confirm Local Browser Cookie Sync</h3>
            <p>This action reads cookies from the current Windows user&apos;s local {syncConfirmBrowser} browser cookie store.</p>
            <p>Cookies are sensitive session data. Use this for local development only.</p>
            <p>Imported output is stored under <code>webscraper/var/cookies/</code> (gitignored).</p>
            <p><strong>Proceed?</strong></p>
            <div style={{ marginTop: 8 }}>
              <button onClick={runBrowserSync}>Proceed</button>
              <button onClick={() => setSyncConfirmBrowser(null)} style={{ marginLeft: 8 }}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
