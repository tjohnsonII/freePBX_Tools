"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiRequestError, apiGet } from "../../lib/api";

type LogItem = { name: string; size: number; mtime: string };

const LINE_OPTIONS = [200, 500, 2000, 5000] as const;

function formatApiError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.detail || error.message;
  return error instanceof Error ? error.message : String(error);
}

export default function LogsPage() {
  const [items, setItems] = useState<LogItem[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [lineCount, setLineCount] = useState<number>(2000);
  const [lines, setLines] = useState<string[]>([]);
  const [search, setSearch] = useState<string>("");
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [enableHint, setEnableHint] = useState<string>("set WEBSCRAPER_LOGS_ENABLED=1");

  const checkEnabled = async () => {
    const response = await apiGet<{ enabled: boolean; how_to_enable?: string }>("/api/logs/enabled");
    const isEnabled = Boolean(response?.enabled);
    setEnableHint(response?.how_to_enable || "set WEBSCRAPER_LOGS_ENABLED=1");
    setEnabled(isEnabled);
    return isEnabled;
  };

  const loadList = async () => {
    if (enabled === false) return;
    const response = await apiGet<{ items: LogItem[] }>("/api/logs/list");
    const next = Array.isArray(response?.items) ? response.items : [];
    setItems(next);
    if (!selected && next.length) setSelected(next[0].name);
    if (selected && !next.some((item) => item.name === selected)) {
      setSelected(next[0]?.name || "");
    }
  };

  const loadTail = async (name: string, count: number) => {
    if (enabled === false) return;
    if (!name) {
      setLines([]);
      return;
    }
    const response = await apiGet<{ name: string; lines: string[] }>(`/api/logs/tail?name=${encodeURIComponent(name)}&lines=${count}`);
    setLines(Array.isArray(response?.lines) ? response.lines : []);
  };

  useEffect(() => {
    checkEnabled()
      .then((isEnabled) => {
        if (!isEnabled) return;
        return loadList();
      })
      .catch((e) => {
        const msg = formatApiError(e);
        if (msg.includes("logs_disabled")) {
          setError(`Logs API disabled. To enable: ${enableHint}`);
          setEnabled(false);
          return;
        }
        setError(msg);
      });
  }, []);

  useEffect(() => {
    if (enabled !== true) return;
    loadTail(selected, lineCount).catch((e) => setError(formatApiError(e)));
  }, [selected, lineCount, enabled]);

  useEffect(() => {
    if (!autoRefresh || enabled !== true) return;
    const timer = setInterval(() => {
      loadList().catch(() => undefined);
      loadTail(selected, lineCount).catch(() => undefined);
    }, 1500);
    return () => clearInterval(timer);
  }, [autoRefresh, selected, lineCount, enabled]);

  const filtered = useMemo(() => {
    if (!search.trim()) return lines;
    const needle = search.toLowerCase();
    return lines.filter((line) => line.toLowerCase().includes(needle));
  }, [lines, search]);

  const copyFiltered = async () => {
    try {
      await navigator.clipboard.writeText(filtered.join("\n"));
    } catch {
      setError("Clipboard copy failed.");
    }
  };

  return (
    <main>
      <h2>Logs</h2>
      {enabled === false ? <p style={{ color: "#a22" }}>Logs API disabled. To enable: <code>{enableHint}</code></p> : null}
      {error ? <p style={{ color: "#a22" }}>{error}</p> : null}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <label>Log File
          <select value={selected} onChange={(e) => setSelected(e.target.value)} style={{ marginLeft: 6 }}>
            {items.map((item) => (
              <option key={item.name} value={item.name}>{item.name} ({item.size} bytes)</option>
            ))}
          </select>
        </label>
        <label>Lines
          <select value={lineCount} onChange={(e) => setLineCount(Number(e.target.value))} style={{ marginLeft: 6 }}>
            {LINE_OPTIONS.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>Search
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="filter lines" style={{ marginLeft: 6 }} />
        </label>
        <label>
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} /> Auto-refresh
        </label>
        <button disabled={enabled !== true} onClick={() => loadTail(selected, lineCount).catch((e) => setError(formatApiError(e)))}>Refresh</button>
        <button onClick={copyFiltered}>Copy</button>
      </div>
      <p>Total lines shown: {filtered.length} / {lines.length}</p>
      <pre style={{ border: "1px solid #ddd", padding: 10, maxHeight: "70vh", overflow: "auto", background: "#0f172a", color: "#e2e8f0" }}>
        {filtered.join("\n") || "No lines."}
      </pre>
    </main>
  );
}
