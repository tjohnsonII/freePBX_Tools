"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";
import styles from "./vpbx.module.css";

type VpbxRecord = {
  handle: string;
  name: string;
  account_status: string;
  ip: string;
  web_order: string;
  deployment_id: string;
  switch: string;
  devices: string;
  last_seen_utc: string;
};

type SortKey = keyof VpbxRecord;

export default function VpbxPage() {
  const [records, setRecords] = useState<VpbxRecord[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("handle");
  const [sortAsc, setSortAsc] = useState(true);
  const [refreshStatus, setRefreshStatus] = useState<string | null>(null);

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRecords = async () => {
    try {
      const res = await apiGet<{ items: VpbxRecord[] }>("/api/vpbx/records");
      setRecords(Array.isArray(res?.items) ? res.items : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const pollJob = async (
    job_id: string,
    label: string,
    onStatus?: (msg: string) => void,
  ): Promise<void> => {
    for (let i = 0; i < 600; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const [job, evts] = await Promise.all([
        apiGet<{ current_state: string; error_message?: string }>(`/api/jobs/${job_id}`),
        apiGet<{ events: { message: string }[] }>(`/api/jobs/${job_id}/events?limit=1`).catch(() => ({ events: [] })),
      ]);
      if (onStatus && evts.events.length > 0) {
        onStatus(evts.events[0].message.replace(/^vpbx[^:]*:/, "").trim());
      }
      if (job.current_state === "done") return;
      if (job.current_state === "error") {
        throw new Error(job.error_message || `${label} failed`);
      }
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    setRefreshStatus(null);
    try {
      const { job_id } = await apiPost<{ job_id: string }>("/api/vpbx/refresh", {});
      await pollJob(job_id, "VPBX", (msg) => setRefreshStatus(msg));
      await loadRecords();
      setLastRefreshed(new Date().toISOString());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
      setRefreshStatus(null);
    }
  };

  useEffect(() => {
    setLoading(true);
    loadRecords().finally(() => setLoading(false));
    pollTimer.current = setInterval(() => loadRecords().catch(() => undefined), 30000);
    return () => { if (pollTimer.current) clearInterval(pollTimer.current); };
  }, []);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) setSortAsc((a) => !a);
    else { setSortKey(key); setSortAsc(true); }
  };

  const filtered = useMemo(() => {
    const q = filter.trim().toUpperCase();
    const base = q
      ? records.filter((r) =>
          r.handle.toUpperCase().includes(q) || (r.name || "").toUpperCase().includes(q)
        )
      : records;
    return [...base].sort((a, b) => {
      const av = (a[sortKey] || "").toLowerCase();
      const bv = (b[sortKey] || "").toLowerCase();
      return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [records, filter, sortKey, sortAsc]);

  const arrow = (key: SortKey) => (sortKey === key ? (sortAsc ? " ↑" : " ↓") : "");

  return (
    <main className={styles.main}>
      <section className={styles.section}>
        <div className={styles.headerRow}>
          <h2 className={styles.title}>VPBX Records</h2>
          <div className={styles.controls}>
            <input
              type="search"
              className={styles.searchInput}
              placeholder="Filter by handle or name…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button type="button" className={styles.refreshBtn} onClick={handleRefresh} disabled={refreshing}>
              {refreshing ? "Waiting for browser…" : "Scrape vpbx.cgi"}
            </button>
          </div>
        </div>

        {lastRefreshed && (
          <p className={styles.subtle}>
            Last refreshed: {lastRefreshed.slice(0, 19).replace("T", " ")} UTC
            &nbsp;·&nbsp; {records.length} records
          </p>
        )}
        {!lastRefreshed && records.length > 0 && (
          <p className={styles.subtle}>{records.length} cached records</p>
        )}
        {refreshStatus && <p className={styles.subtle}>↻ {refreshStatus}</p>}
        {error && <p className={styles.error}>{error}</p>}
        {loading && <p className={styles.subtle}>Loading…</p>}

        {!loading && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  {(
                    [
                      ["handle", "Handle"],
                      ["name", "Name"],
                      ["account_status", "Status"],
                      ["ip", "IP"],
                      ["web_order", "Web Order"],
                      ["deployment_id", "Deployment ID"],
                      ["switch", "Switch"],
                      ["devices", "Devices"],
                      ["last_seen_utc", "Last Seen"],
                    ] as [SortKey, string][]
                  ).map(([key, label]) => (
                    <th key={key} className={styles.th} onClick={() => handleSort(key)}>
                      {label}{arrow(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.handle} className={styles.row}>
                    <td className={styles.handleCell}>{r.handle}</td>
                    <td>{r.name}</td>
                    <td>
                      <span className={r.account_status.toLowerCase().includes("active") ? styles.statusActive : styles.statusOther}>
                        {r.account_status || "—"}
                      </span>
                    </td>
                    <td className={styles.mono}>{r.ip || "—"}</td>
                    <td className={styles.mono}>{r.web_order || "—"}</td>
                    <td className={styles.mono}>{r.deployment_id || "—"}</td>
                    <td>{r.switch || "—"}</td>
                    <td>{r.devices || "—"}</td>
                    <td className={styles.mono}>
                      {r.last_seen_utc ? r.last_seen_utc.slice(0, 10) : "—"}
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && !loading && (
                  <tr>
                    <td colSpan={9} className={styles.emptyCell}>
                      {filter ? "No records match the filter." : 'No VPBX records cached yet — click "Scrape vpbx.cgi" to fetch.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}