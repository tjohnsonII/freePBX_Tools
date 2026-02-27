"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { apiGet, apiPost, apiPostText } from "../../lib/api";

type DomainCount = { domain: string; count: number };
type AuthStatus = { stored: boolean; total: number; domains: DomainCount[]; created_utc: string | null; missing_domains?: string[] };
type ValidateRow = {
  domain: string;
  cookieCount: number;
  ok: boolean;
  statusCode?: number | null;
  finalUrl?: string | null;
  reason: string;
  hint: string;
};
type ValidateResponse = { ok: boolean; results: ValidateRow[] };

const DEFAULT_DOMAINS = ["secure.123.net", "noc-tickets.123.net", "10.123.203.1"];

export default function AuthPage() {
  const [cookieText, setCookieText] = useState("");
  const [uploadName, setUploadName] = useState<string>("");
  const [selectedDomains, setSelectedDomains] = useState<string[]>(DEFAULT_DOMAINS.slice(0, 2));
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [validate, setValidate] = useState<ValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refreshStatus = async () => {
    const res = await apiGet<AuthStatus>(`/api/auth/status?selectedDomains=${encodeURIComponent(selectedDomains.join(","))}`);
    setStatus(res);
  };

  const runValidate = async () => {
    const val = await apiPost<ValidateResponse>("/api/auth/validate", { targets: selectedDomains, timeoutSeconds: 10 });
    setValidate(val);
  };

  useEffect(() => {
    refreshStatus().catch(() => setStatus(null));
  }, [selectedDomains.join(",")]);

  const onUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadName(file.name);
    setCookieText(await file.text());
  };

  const importCookies = async () => {
    setError(null);
    setValidate(null);
    setMessage(null);
    const trimmed = cookieText.trim();
    if (!trimmed) return setError("Paste cookies or upload a file first.");

    let result: { message?: string } = {};
    if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
      const parsed = JSON.parse(trimmed);
      result = await apiPost("/api/auth/import", { cookies: parsed, selectedDomains });
    } else {
      result = await apiPostText(`/api/auth/import`, JSON.stringify({ text: cookieText, selectedDomains }), "application/json");
    }
    setMessage(result.message || null);
    await refreshStatus();
    await runValidate();
  };

  const clearCookies = async () => {
    await apiPost("/api/auth/clear", {});
    setValidate(null);
    setCookieText("");
    setUploadName("");
    setMessage(null);
    await refreshStatus();
  };

  return (
    <main>
      <h2>Auth</h2>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      {message && <p style={{ color: "#166534" }}>{message}</p>}
      <p>Paste cookies</p>
      <textarea rows={12} style={{ width: "100%" }} value={cookieText} onChange={(e) => setCookieText(e.target.value)} />
      <p>Upload cookies file</p>
      <input type="file" onChange={onUpload} /> {uploadName ? <span>{uploadName}</span> : null}

      <h3>Target domains</h3>
      {DEFAULT_DOMAINS.map((domain) => (
        <label key={domain} style={{ display: "block" }}>
          <input
            type="checkbox"
            checked={selectedDomains.includes(domain)}
            onChange={(e) =>
              setSelectedDomains((current) => (e.target.checked ? [...current, domain] : current.filter((item) => item !== domain)))
            }
          />
          {domain}
        </label>
      ))}

      <div style={{ marginTop: 8 }}>
        <button onClick={importCookies}>Import Cookies</button>
        <button onClick={clearCookies} style={{ marginLeft: 8 }}>Clear cookies</button>
        <button onClick={runValidate} style={{ marginLeft: 8 }}>Validate Auth</button>
      </div>

      <h3>Status</h3>
      <p>Stored timestamp: {status?.created_utc || "-"}</p>
      <p>Total cookies: {status?.total ?? 0}</p>
      <p style={{ color: "#b91c1c" }}>Domains missing: {(status?.missing_domains || []).join(", ") || "None"}</p>
      <table>
        <thead><tr><th>Domain</th><th>Cookie Count</th></tr></thead>
        <tbody>
          {(status?.domains || []).map((row) => (
            <tr key={row.domain}><td>{row.domain}</td><td>{row.count}</td></tr>
          ))}
        </tbody>
      </table>

      {validate && (
        <section>
          <h3>Validation</h3>
          <p>{validate.ok ? "PASS" : "FAIL"}</p>
          <table>
            <thead><tr><th>Domain</th><th>Cookies</th><th>Status</th><th>Final URL</th><th>Reason</th><th>Hint</th></tr></thead>
            <tbody>
              {validate.results.map((item) => (
                <tr key={item.domain} style={{ background: item.ok ? "#dcfce7" : "#fee2e2" }}>
                  <td>{item.domain}</td><td>{item.cookieCount}</td><td>{item.statusCode ?? "-"}</td><td>{item.finalUrl || "-"}</td><td>{item.reason}</td><td>{item.hint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
