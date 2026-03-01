"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { ApiRequestError, apiGet, apiPost, apiPostForm } from "../../lib/api";

type DomainCount = { domain: string; count: number };
type AuthStatus = {
  cookie_count: number;
  domains: string[];
  domain_counts?: DomainCount[];
  last_imported: number | null;
  source: string;
};
type AuthSeedResponse = {
  ok: boolean;
  mode_used: "auto" | "disk" | "cdp";
  details?: Record<string, unknown>;
  next_step_if_failed?: string | null;
  cookie_count?: number;
};
type ChromeProfilesResponse = {
  ok: boolean;
  profiles: string[];
  preferred: string | null;
};
type ValidateRow = {
  url: string;
  status?: number | null;
  final_url?: string | null;
  ok: boolean;
  hint?: string | null;
};
type ValidateResponse = {
  ok?: boolean;
  authenticated: boolean;
  reason?: string;
  reasons?: Array<Record<string, unknown>>;
  checks: ValidateRow[];
  cookie_count: number;
  domains: string[];
};
type AuthLaunchResponse = {
  ok: boolean;
  forced: boolean;
  cookies_saved: boolean;
  profile_dir: string;
  warnings?: string[];
};
type AuthResetResponse = {
  ok: boolean;
  removed: string[];
  warnings: string[];
};

const FALLBACK_TICKETING_TARGET_URL = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi";
const TICKETING_TARGET_URL = process.env.NEXT_PUBLIC_TICKETING_TARGET_URL || process.env.NEXT_PUBLIC_TICKETING_LOGIN_URL || FALLBACK_TICKETING_TARGET_URL;

export default function AuthPage() {
  const [text, setText] = useState("");
  const [uploadName, setUploadName] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [validate, setValidate] = useState<ValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [modeUsed, setModeUsed] = useState<string | null>(null);
  const [statusWarning, setStatusWarning] = useState<string | null>(null);
  const [chromeProfiles, setChromeProfiles] = useState<string[]>([]);
  const [chromeProfileDir, setChromeProfileDir] = useState<string>("Profile 1");

  const hasSecureDomain = (status?.domains || []).some((domain) => {
    const normalized = domain.replace(/^\./, "").toLowerCase();
    return normalized === "secure.123.net" || normalized.endsWith(".secure.123.net") || normalized === "123.net" || normalized.endsWith(".123.net");
  });
  const wrongDomainLoaded = (status?.cookie_count || 0) > 0 && !hasSecureDomain;

  const refreshStatus = async () => {
    try {
      const res = await apiGet<AuthStatus>("/api/auth/status");
      setStatus(res);
      setStatusWarning(null);
    } catch (err) {
      setStatus({ cookie_count: 0, domains: [], domain_counts: [], last_imported: null, source: "none" });
      setStatusWarning(err instanceof ApiRequestError ? (err.detail || err.message) : "Auth status unavailable.");
    }
  };

  const runValidate = async () => {
    const val = await apiGet<ValidateResponse>("/api/auth/validate?domain=secure.123.net&timeout_seconds=10");
    setValidate(val);
  };

  const loadChromeProfiles = async () => {
    try {
      const res = await apiGet<ChromeProfilesResponse>("/api/auth/chrome_profiles");
      setChromeProfiles(res.profiles || []);
      if (res.preferred) {
        setChromeProfileDir(res.preferred);
      }
    } catch {
      setChromeProfiles([]);
    }
  };

  useEffect(() => {
    refreshStatus().catch(() => undefined);
    loadChromeProfiles().catch(() => undefined);
  }, []);

  const onUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setUploadName(file?.name || "");
  };

  const importText = async () => {
    setError(null);
    setMessage(null);
    if (!text.trim()) {
      setError("Paste cookie data first.");
      return;
    }
    try {
      const result = await apiPost<{ cookie_count: number }>("/api/auth/import", { text });
      setMessage(`Imported ${result.cookie_count} cookies from pasted text.`);
      setText("");
      await refreshStatus();
      await runValidate();
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.detail || err.message);
      } else {
        setError("Cookie import failed.");
      }
    }
  };

  const importFile = async () => {
    setError(null);
    setValidate(null);
    setMessage(null);
    if (!selectedFile) {
      setError("Select a JSON or TXT cookie file first.");
      return;
    }

    const fd = new FormData();
    fd.append("file", selectedFile);

    try {
      const result = await apiPostForm<{ cookie_count: number; filename?: string }>("/api/auth/import-file", fd);
      setMessage(`Imported ${result.cookie_count} cookies from ${result.filename || selectedFile.name}.`);
      await refreshStatus();
      await runValidate();
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.detail || err.message);
      } else {
        setError("Cookie import failed.");
      }
    }
  };

  const launchLoginIsolated = async () => {
    setError(null);
    setMessage(null);
    try {
      const result = await apiPost<AuthLaunchResponse>(`/api/auth/launch?force=false&url=${encodeURIComponent(TICKETING_TARGET_URL)}`, {});
      const warningText = (result.warnings || []).length ? ` Warnings: ${result.warnings?.join(", ")}` : "";
      setMessage(`Opened login browser. Profile: ${result.profile_dir}.${warningText}`);
      await refreshStatus();
    } catch (err) {
      const launchError = err instanceof ApiRequestError ? (err.detail || err.message) : "Failed to launch login browser.";
      setError(launchError);
    }
  };

  const forceRelogin = async () => {
    setError(null);
    setMessage(null);
    try {
      const reset = await apiPost<AuthResetResponse>("/api/auth/force-reset", {});
      const launch = await apiPost<AuthLaunchResponse>(`/api/auth/launch?force=true&url=${encodeURIComponent(TICKETING_TARGET_URL)}`, {});
      const warnings = [...(reset.warnings || []), ...(launch.warnings || [])];
      const warningText = warnings.length ? ` Warnings: ${warnings.join(", ")}` : "";
      setMessage(`Force re-login complete. Profile: ${launch.profile_dir}. Cookies saved: ${launch.cookies_saved}.${warningText}`);
      await refreshStatus();
      await runValidate();
    } catch (err) {
      const launchError = err instanceof ApiRequestError ? (err.detail || err.message) : "Force re-login failed.";
      setError(launchError);
    }
  };

  const launchDebugChromeClick = async () => {
    setError(null);
    try {
      await apiPost("/api/auth/launch_debug_chrome", { cdp_port: 9222, profile_name: "Default" });
      setMessage("Launched debug Chrome on port 9222. Retry auth seed in CDP/Auto mode.");
    } catch (err) {
      setError(err instanceof ApiRequestError ? (err.detail || err.message) : "Failed to launch debug Chrome.");
    }
  };

  const launchLoginSeeded = async () => {
    setError(null);
    setMessage(null);
    setModeUsed(null);
    try {
      const result = await apiPost<AuthSeedResponse>("/api/auth/seed", {
        mode: "auto",
        chrome_profile_dir: chromeProfileDir,
        seed_domains: ["secure.123.net", "123.net"],
        cdp_port: 9222,
      });
      setModeUsed(result.mode_used || "auto");
      if (!result.ok) {
        setError(result.next_step_if_failed || "Auth seed failed.");
        return;
      }
      setMessage(`Seeded and imported auth cookies using ${result.mode_used.toUpperCase()} mode.`);
      await refreshStatus();
      await runValidate();
    } catch (err) {
      const launchError = err instanceof ApiRequestError ? (err.detail || err.message) : "Failed to seed auth cookies.";
      setError(launchError);
    }
  };

  const clearCookies = async () => {
    await apiPost("/api/auth/clear", {});
    setValidate(null);
    setSelectedFile(null);
    setUploadName("");
    setText("");
    setMessage(null);
    await refreshStatus();
  };

  return (
    <main>
      <h2>Auth Cookies</h2>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      {message && <p style={{ color: "#166534" }}>{message}</p>}
      {modeUsed && <p>Mode used: <strong>{modeUsed}</strong></p>}
      {statusWarning && <p style={{ color: "#a16207" }}>Status warning: {statusWarning}</p>}
      {wrongDomainLoaded && <p style={{ color: "#b91c1c", fontWeight: 600 }}>Wrong cookie domain set loaded; must include secure.123.net</p>}

      <section>
        <h3>Paste cookies</h3>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} style={{ width: "100%" }} />
        <div style={{ marginTop: 8 }}>
          <button onClick={importText} disabled={!text.trim()}>Import Pasted Cookies</button>
        </div>
      </section>

      <section>
        <h3>Upload cookies file</h3>
        <input type="file" accept=".json,.txt" onChange={onUpload} /> {uploadName ? <span>{uploadName}</span> : null}
        <div style={{ marginTop: 8 }}>
          <button onClick={importFile}>Upload Cookies File</button>
        </div>
      </section>

      <div style={{ marginTop: 8 }}>
        <button onClick={clearCookies}>Clear</button>
        <button onClick={launchLoginIsolated} style={{ marginLeft: 8 }}>
          Launch isolated login
        </button>
        <button onClick={forceRelogin} style={{ marginLeft: 8 }}>
          Force Re-Login (Clear Cookies)
        </button>
        <label style={{ marginLeft: 8 }}>
          Chrome Profile
          <select value={chromeProfileDir} onChange={(e) => setChromeProfileDir(e.target.value)} style={{ marginLeft: 6 }}>
            {(chromeProfiles.length ? chromeProfiles : ["Profile 1", "Default"]).map((profile) => (
              <option key={profile} value={profile}>
                {profile}
              </option>
            ))}
          </select>
        </label>
        <button onClick={launchLoginSeeded} style={{ marginLeft: 8 }}>Seed Auth (auto)</button>
        <button onClick={launchDebugChromeClick} style={{ marginLeft: 8 }}>Launch Debug Chrome</button>
        <button onClick={runValidate} disabled={wrongDomainLoaded} style={{ marginLeft: 8 }}>
          Validate Auth
        </button>
      </div>

      <h3>Status</h3>
      <p>Last import: {status?.last_imported || "-"}</p>
      <p>Imported cookies: {status?.cookie_count ?? 0}</p>
      <p>Source: {status?.source || "none"}</p>
      <p>Domains: {(status?.domains || []).join(", ") || "-"}</p>
      <table>
        <thead>
          <tr>
            <th>Domain</th>
            <th>Cookie Count</th>
          </tr>
        </thead>
        <tbody>
          {(status?.domain_counts || []).map((row) => (
            <tr key={row.domain}>
              <td>{row.domain}</td>
              <td>{row.count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {validate && (
        <section>
          <h3>Validation</h3>
          <p>Authenticated: {validate.authenticated ? "yes" : "no"}</p>
          <p>Reason: {validate.reason || "-"}</p>
          <table>
            <thead>
              <tr>
                <th>URL</th>
                <th>Status</th>
                <th>Final URL</th>
                <th>OK</th>
                <th>Hint</th>
              </tr>
            </thead>
            <tbody>
              {validate.checks.map((item) => (
                <tr key={item.url} style={{ background: item.ok ? "#dcfce7" : "#fee2e2" }}>
                  <td>{item.url}</td>
                  <td>{item.status ?? "-"}</td>
                  <td>{item.final_url || "-"}</td>
                  <td>{item.ok ? "yes" : "no"}</td>
                  <td>{item.hint || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
