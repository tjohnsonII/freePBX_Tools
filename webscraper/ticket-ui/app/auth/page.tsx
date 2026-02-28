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
type ValidateRow = {
  url: string;
  status?: number | null;
  final_url?: string | null;
  ok: boolean;
  hint?: string | null;
};
type ValidateResponse = {
  authenticated: boolean;
  reason?: string;
  checks: ValidateRow[];
  cookie_count: number;
  domains: string[];
};

export default function AuthPage() {
  const [text, setText] = useState("");
  const [uploadName, setUploadName] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [validate, setValidate] = useState<ValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [statusWarning, setStatusWarning] = useState<string | null>(null);

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
    const val = await apiPost<ValidateResponse>("/api/auth/validate", { timeoutSeconds: 10, targets: [] });
    setValidate(val);
  };

  useEffect(() => {
    refreshStatus().catch(() => undefined);
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
    setText("");
    setMessage(null);
    await refreshStatus();
  };

  return (
    <main>
      <h2>Auth Cookies</h2>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      {message && <p style={{ color: "#166534" }}>{message}</p>}
      {statusWarning && <p style={{ color: "#a16207" }}>Status warning: {statusWarning}</p>}

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
          <button onClick={importFile} disabled={!selectedFile}>Upload Cookies File</button>
        </div>
      </section>

      <div style={{ marginTop: 8 }}>
        <button onClick={clearCookies}>Clear</button>
        <button onClick={runValidate} style={{ marginLeft: 8 }}>
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
