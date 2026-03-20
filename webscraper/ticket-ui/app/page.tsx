"use client";

import { useEffect, useMemo, useState } from "react";
import OrchestrationDashboard from "./components/OrchestrationDashboard";
import { apiGet } from "../lib/api";
import styles from "./kb.module.css";

type HandleRow = {
  handle: string;
  status?: string;
  last_updated_utc?: string;
  ticket_count?: number;
};

export default function KBPage() {
  const [search, setSearch] = useState("");
  const [handleRows, setHandleRows] = useState<HandleRow[]>([]);
  const [totalTickets, setTotalTickets] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadHandles = async () => {
    try {
      const res = await apiGet<{ items: HandleRow[] }>("/api/handles?limit=1000&offset=0");
      setHandleRows(Array.isArray(res?.items) ? res.items : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const loadStats = async () => {
    try {
      const res = await apiGet<{ total_tickets?: number; db_counts?: { tickets?: number } }>("/api/health");
      const count = res.total_tickets ?? res.db_counts?.tickets ?? null;
      setTotalTickets(count);
    } catch {
      // non-critical
    }
  };

  useEffect(() => {
    loadHandles().catch(() => undefined);
    loadStats().catch(() => undefined);
    const timer = setInterval(() => {
      loadHandles().catch(() => undefined);
      loadStats().catch(() => undefined);
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  const filteredRows = useMemo(() => {
    const q = search.trim().toUpperCase();
    const rows = q ? handleRows.filter((r) => r.handle.toUpperCase().includes(q)) : handleRows;
    return [...rows].sort((a, b) => {
      const da = a.last_updated_utc || "";
      const db = b.last_updated_utc || "";
      return db.localeCompare(da);
    });
  }, [handleRows, search]);

  return (
    <main className={styles.main}>
      <OrchestrationDashboard />

      <section className={styles.kbSection}>
        <h2>Knowledge Base</h2>
        {error && <p className={styles.error}>{error}</p>}
        <div className={styles.kbStats}>
          <span>Total: {totalTickets !== null ? totalTickets.toLocaleString() : "…"} tickets</span>
          <span>{handleRows.length} handles</span>
        </div>
        <input
          type="search"
          className={styles.search}
          placeholder="Search handles…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <table className={styles.handleTable}>
          <thead>
            <tr>
              <th>Handle</th>
              <th>Tickets</th>
              <th>Last Scraped</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row) => (
              <tr key={row.handle}>
                <td>
                  <a href={`/handles/${encodeURIComponent(row.handle)}`}>{row.handle}</a>
                </td>
                <td>{row.ticket_count ?? 0}</td>
                <td>{row.last_updated_utc ? row.last_updated_utc.slice(0, 10) : "-"}</td>
                <td>{row.status || "-"}</td>
              </tr>
            ))}
            {filteredRows.length === 0 && (
              <tr>
                <td colSpan={4} className={styles.emptyCell}>
                  {search ? "No handles match search." : "No handles found."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
