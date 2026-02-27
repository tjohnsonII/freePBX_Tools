"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { apiGet, apiPost, apiPostText } from "../../lib/api";

type AuthStatus = { count: number; domains: string[]; created_utc: string | null; missing_domains?: string[] };
type ValidateResponse = { ok: boolean; results: { domain: string; ok: boolean; reason: string }[] };

const DEFAULT_DOMAINS = ["secure.123.net", "noc-tickets.123.net", "10.123.203.1"];

export default function AuthPage() {
  const [cookieText, setCookieText] = useState("");
  const [uploadName, setUploadName] = useState<string>("");
  const [selectedDomains, setSelectedDomains] = useState<string[]>(DEFAULT_DOMAINS.slice(0, 2));
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [validate, setValidate] = useState<ValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = async () => {
    const res = await apiGet<AuthStatus>(`/api/auth/status?selectedDomains=${encodeURIComponent(selectedDomains.join(","))}`);
    setStatus(res);
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
    const trimmed = cookieText.trim();
    if (!trimmed) return setError("Paste cookies or upload a file first.");

    if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
      const parsed = JSON.parse(trimmed);
      await apiPost("/api/auth/import", { cookies: parsed, selectedDomains });
    } else {
      await apiPostText(`/api/auth/import`, JSON.stringify({ text: cookieText, selectedDomains }), "application/json");
    }
    await refreshStatus();
    const val = await apiPost<ValidateResponse>("/api/auth/validate", { selectedDomains });
    setValidate(val);
  };

  const clearCookies = async () => {
    await apiPost("/api/auth/clear", {});
    setValidate(null);
    setCookieText("");
    setUploadName("");
    await refreshStatus();
  };

  return (
    <main>
      <h2>Auth</h2>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
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
        <button onClick={clearCookies} style={{ marginLeft: 8 }}>
          Clear cookies
        </button>
      </div>

      <h3>Status</h3>
      <p>Stored timestamp: {status?.created_utc || "-"}</p>
      <p>Count of cookies: {status?.count ?? 0}</p>
      <p>Domains detected: {(status?.domains || []).join(", ") || "-"}</p>
      <p style={{ color: "#b91c1c" }}>Domains missing: {(status?.missing_domains || []).join(", ") || "None"}</p>

      {validate && (
        <section>
          <h3>Validation</h3>
          <p>{validate.ok ? "PASS" : "FAIL"}</p>
          <ul>
            {validate.results.map((item) => (
              <li key={item.domain} style={{ color: item.ok ? "#166534" : "#b91c1c" }}>
                {item.domain}: {item.ok ? "PASS" : "FAIL"} - {item.reason}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
