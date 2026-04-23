"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";
import styles from "./noc-queue.module.css";

type NocTicket = {
  ticket_id: string;
  view: string;
  subject: string;
  status: string;
  opened: string;
  customer: string;
  priority: string;
  assigned_to: string;
  ticket_type: string;
  ticket_id_url: string;
  last_seen_utc: string;
};

const VIEWS = [
  { key: "all",    label: "All Views" },
  { key: "hosted", label: "Hosted" },
  { key: "noc",    label: "NOC" },
  { key: "all_q",  label: "All Queue" },
  { key: "local",  label: "Local NOC" },
] as const;

type ViewKey = typeof VIEWS[number]["key"];

export default function NocQueuePage() {
  const [tickets, setTickets] = useState<NocTicket[]>([]);
  const [activeView, setActiveView] = useState<ViewKey>("all");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshingView, setRefreshingView] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTickets = async () => {
    try {
      const res = await apiGet<{ items: NocTicket[] }>("/api/noc-queue/records");
      setTickets(Array.isArray(res?.items) ? res.items : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const pollJob = async (job_id: string, label: string): Promise<void> => {
    for (let i = 0; i < 180; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const job = await apiGet<{ current_state: string; error_message?: string }>(
        `/api/jobs/${job_id}`
      );
      if (job.current_state === "done") {
        await loadTickets();
        setLastRefreshed(new Date().toISOString());
        return;
      }
      if (job.current_state === "error") {
        setError(job.error_message || `${label} refresh failed`);
        return;
      }
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const { job_id } = await apiPost<{ job_id: string }>("/api/noc-queue/refresh", {});
      await pollJob(job_id, "NOC queue");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  // Maps frontend tab key → DB view key sent to the API
  const tabViewKey = (key: string) => key === "all_q" ? "all" : key;

  const handleRefreshView = async (key: string) => {
    const vk = tabViewKey(key);
    setRefreshingView(vk);
    setError(null);
    try {
      const { job_id } = await apiPost<{ job_id: string }>("/api/noc-queue/refresh", { view: vk });
      await pollJob(job_id, key);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshingView(null);
    }
  };

  useEffect(() => {
    setLoading(true);
    loadTickets().finally(() => setLoading(false));
    pollTimer.current = setInterval(() => loadTickets().catch(() => undefined), 30000);
    return () => { if (pollTimer.current) clearInterval(pollTimer.current); };
  }, []);

  const viewCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of tickets) counts[t.view] = (counts[t.view] || 0) + 1;
    return counts;
  }, [tickets]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const viewFiltered = activeView === "all"
      ? tickets
      : tickets.filter((t) => t.view === (activeView === "all_q" ? "all" : activeView));
    return q
      ? viewFiltered.filter((t) =>
          [t.ticket_id, t.subject, t.customer, t.status, t.assigned_to, t.priority]
            .some((v) => (v || "").toLowerCase().includes(q))
        )
      : viewFiltered;
  }, [tickets, activeView, filter]);

  const statusClass = (s: string) => {
    const l = (s || "").toLowerCase();
    if (l.includes("open") || l.includes("new") || l.includes("active")) return styles.statusOpen;
    if (l.includes("pend")) return styles.statusPending;
    return styles.statusClosed;
  };

  return (
    <main className={styles.main}>
      <section className={styles.section}>
        <div className={styles.headerRow}>
          <h2 className={styles.title}>NOC Ticket Queues</h2>
          <div className={styles.controls}>
            <input
              type="search"
              className={styles.searchInput}
              placeholder="Filter tickets…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button type="button" className={styles.refreshBtn} onClick={handleRefresh} disabled={refreshing}>
              {refreshing ? "Waiting for browser…" : "Refresh all queues"}
            </button>
          </div>
        </div>

        {lastRefreshed && (
          <p className={styles.subtle}>
            Last refreshed: {lastRefreshed.slice(0, 19).replace("T", " ")} UTC
            &nbsp;·&nbsp; {tickets.length} tickets total
          </p>
        )}
        {!lastRefreshed && tickets.length > 0 && (
          <p className={styles.subtle}>{tickets.length} cached tickets</p>
        )}
        {error && <p className={styles.error}>{error}</p>}

        {/* ── Tabs ── */}
        <div className={styles.tabRow}>
          <div className={styles.tabs}>
            {VIEWS.map((v) => {
              const count = v.key === "all"
                ? tickets.length
                : viewCounts[v.key === "all_q" ? "all" : v.key] ?? 0;
              return (
                <button
                  key={v.key}
                  type="button"
                  className={`${styles.tab} ${activeView === v.key ? styles.tabActive : ""}`}
                  onClick={() => setActiveView(v.key)}
                >
                  {v.label}
                  {count > 0 && <span className={styles.badge}>{count}</span>}
                </button>
              );
            })}
          </div>
          {activeView !== "all" && (
            <button
              type="button"
              className={styles.scrapeTabBtn}
              onClick={() => handleRefreshView(activeView)}
              disabled={refreshingView !== null || refreshing}
            >
              {refreshingView === tabViewKey(activeView) ? "Waiting for browser…" : `Scrape ${VIEWS.find((v) => v.key === activeView)?.label}`}
            </button>
          )}
        </div>

        {loading && <p className={styles.subtle}>Loading…</p>}

        {!loading && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Ticket ID</th>
                  <th className={styles.th}>Subject</th>
                  <th className={styles.th}>Customer</th>
                  <th className={styles.th}>Status</th>
                  <th className={styles.th}>Priority</th>
                  <th className={styles.th}>Assigned To</th>
                  <th className={styles.th}>Opened</th>
                  {activeView === "all" && <th className={styles.th}>Queue</th>}
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr key={`${t.view}-${t.ticket_id}`} className={styles.row}>
                    <td className={styles.mono}>
                      {t.ticket_id_url
                        ? <a href={t.ticket_id_url} target="_blank" rel="noreferrer">{t.ticket_id}</a>
                        : t.ticket_id}
                    </td>
                    <td className={styles.subject}>{t.subject || "—"}</td>
                    <td className={styles.mono}>{t.customer || "—"}</td>
                    <td>
                      <span className={statusClass(t.status)}>{t.status || "—"}</span>
                    </td>
                    <td className={styles.mono}>{t.priority || "—"}</td>
                    <td>{t.assigned_to || "—"}</td>
                    <td className={styles.mono}>{t.opened ? t.opened.slice(0, 10) : "—"}</td>
                    {activeView === "all" && (
                      <td><span className={styles.viewBadge}>{t.view}</span></td>
                    )}
                  </tr>
                ))}
                {filtered.length === 0 && !loading && (
                  <tr>
                    <td colSpan={activeView === "all" ? 8 : 7} className={styles.emptyCell}>
                      {filter
                        ? "No tickets match the filter."
                        : 'No cached tickets — click "Refresh all queues" to fetch.'}
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
