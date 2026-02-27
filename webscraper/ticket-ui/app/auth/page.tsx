"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";

type AuthStatus = {
  hasImportedCookies: boolean;
  count: number;
  domains: string[];
  stored_utc: string | null;
};

export default function AuthPage() {
  const [cookieJson, setCookieJson] = useState("");
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = async () => {
    const res = await apiGet<AuthStatus>("/api/auth/status");
    setStatus(res);
  };

  useEffect(() => {
    refreshStatus().catch(() => setStatus(null));
  }, []);

  const saveCookies = async () => {
    setError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(cookieJson);
    } catch {
      setError("Cookies must be valid JSON.");
      return;
    }
    const isArray = Array.isArray(parsed);
    const wrapped = !!parsed && typeof parsed === "object" && Array.isArray((parsed as { cookies?: unknown }).cookies);
    if (!isArray && !wrapped) {
      setError("JSON must be an array of cookies or {\"cookies\":[...]}.");
      return;
    }
    await apiPost<AuthStatus>("/api/auth/import-cookies", parsed);
    setCookieJson("");
    await refreshStatus();
  };

  const clearCookies = async () => {
    setError(null);
    await apiPost<{ ok: boolean }>("/api/auth/clear-cookies", {});
    await refreshStatus();
  };

  return (
    <main>
      <h2>Auth</h2>
      {error && <p style={{ color: "#a22" }}>{error}</p>}
      <p>Paste cookies JSON exported from your browser extension.</p>
      <textarea rows={14} style={{ width: "100%" }} value={cookieJson} onChange={(e) => setCookieJson(e.target.value)} />
      <div>
        <button onClick={saveCookies}>Save Cookies</button>
        <button onClick={clearCookies}>Clear Cookies</button>
      </div>
      <h3>Auth status</h3>
      <p>Imported cookies: {status?.hasImportedCookies ? "Yes" : "No"}</p>
      <p>Cookie count: {status?.count ?? 0}</p>
      <p>Domains: {(status?.domains || []).join(", ") || "-"}</p>
      <p>Stored UTC: {status?.stored_utc || "-"}</p>
    </main>
  );
}
