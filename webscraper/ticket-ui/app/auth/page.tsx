"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { ApiRequestError, apiGet, apiPost, apiPostForm } from "../../lib/api";

type DomainCount = { domain: string; count: number };
type AuthStatus = {
  ok: boolean;
  cookie_count: number;
  domains: string[];
  domain_counts?: DomainCount[];
  last_loaded: string | null;
  source: string;
  missing_domains?: string[];
};
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
type ImportResponse = {
  ok: boolean;
  format_used: string;
  source_filename: string;
  total_parsed: number;
  total_kept: number;
  target_domains: string[];
};

const DEFAULT_DOMAINS = ["secure.123.net", "123.net"];

export default function AuthPage() {
  const [uploadName, setUploadName] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedDomains, setSelectedDomains] = useState<string[]>(DEFAULT_DOMAINS.slice());
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
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setUploadName(file?.name || "");
  };

  const importCookies = async () => {
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
      const result = await apiPostForm<ImportResponse>("/api/auth/import-file", fd);
      setMessage(
        `Imported ${result.total_kept}/${result.total_parsed} cookies from ${result.source_filename} (${result.format_used}).`,
      );
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

  const clearCookies = async () => {
    await apiPost("/api/auth/clear", {});
    setValidate(null);
    setSelectedFile(null);
    setUploadName("");
    setMessage(null);
    await refreshStatus();
  };

  return (
    <main>
      <h2>Auth Cookies</h2>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      {message && <p style={{ color: "#166534" }}>{message}</p>}

      <section>
        <h3>Import Cookies</h3>
        <input type="file" accept=".json,.txt" onChange={onUpload} /> {uploadName ? <span>{uploadName}</span> : null}
      </section>

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
        <button onClick={importCookies}>Import</button>
        <button onClick={clearCookies} style={{ marginLeft: 8 }}>
          Clear
        </button>
        <button onClick={runValidate} style={{ marginLeft: 8 }}>
          Validate Auth
        </button>
      </div>

      <h3>Status</h3>
      <p>Last import: {status?.last_loaded || "-"}</p>
      <p>Imported cookies: {status?.cookie_count ?? 0}</p>
      <p>Source: {status?.source || "none"}</p>
      <p>Domains: {(status?.domains || []).join(", ") || "-"}</p>
      <p style={{ color: "#b91c1c" }}>Domains missing: {(status?.missing_domains || []).join(", ") || "None"}</p>
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
          <p>{validate.ok ? "PASS" : "FAIL"}</p>
          <table>
            <thead>
              <tr>
                <th>Domain</th>
                <th>Cookies</th>
                <th>Status</th>
                <th>Final URL</th>
                <th>Reason</th>
                <th>Hint</th>
              </tr>
            </thead>
            <tbody>
              {validate.results.map((item) => (
                <tr key={item.domain} style={{ background: item.ok ? "#dcfce7" : "#fee2e2" }}>
                  <td>{item.domain}</td>
                  <td>{item.cookieCount}</td>
                  <td>{item.statusCode ?? "-"}</td>
                  <td>{item.finalUrl || "-"}</td>
                  <td>{item.reason}</td>
                  <td>{item.hint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
