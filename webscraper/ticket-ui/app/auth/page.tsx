"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost, apiPostText } from "../../lib/api";

type AuthStatus = {
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
    const trimmed = cookieJson.trim();
    if (!trimmed) {
      setError("Paste cookie data first.");
      return;
    }
    if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(trimmed);
      } catch {
        setError("Cookies must be valid JSON.");
        return;
      }
      await apiPost<{ ok: boolean }>("/api/auth/import-cookies", parsed);
    } else {
      await apiPostText<{ ok: boolean }>("/api/auth/import-cookies", cookieJson, "text/plain");
    }
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
      <p>Paste cookies from browser extension (JSON or Netscape cookie.txt format).</p>
      <textarea rows={14} style={{ width: "100%" }} value={cookieJson} onChange={(e) => setCookieJson(e.target.value)} />
      <div>
        <button onClick={saveCookies}>Save Cookies</button>
        <button onClick={clearCookies}>Clear Cookies</button>
      </div>
      <h3>Auth status</h3>
      <p>Imported cookies: {(status?.count || 0) > 0 ? "Yes" : "No"}</p>
      <p>Cookie count: {status?.count ?? 0}</p>
      <p>Domains: {(status?.domains || []).join(", ") || "-"}</p>
      <p>Stored UTC: {status?.stored_utc || "-"}</p>
    </main>
  );
}
