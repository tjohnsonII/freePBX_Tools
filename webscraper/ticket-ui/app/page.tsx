"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import OrchestrationDashboard from "./components/OrchestrationDashboard";
import { apiGet } from "../lib/api";
import styles from "./kb.module.css";

type HandleRow = {
  handle: string;
  status?: string;
  last_updated_utc?: string;
  ticket_count?: number;
};

type KBTicket = {
  ticket_id: string;
  handle: string;
  subject?: string;
  status?: string;
  created_utc?: string;
  updated_utc?: string;
  ticket_url?: string;
  notes_preview?: string | null;
};

type KBSearchResult = {
  items: KBTicket[];
  totalCount: number;
  page: number;
  pageSize: number;
};

export default function KBPage() {
  // Handle list state
  const [handleSearch, setHandleSearch] = useState("");
  const [handleRows, setHandleRows] = useState<HandleRow[]>([]);
  const [totalTickets, setTotalTickets] = useState<number | null>(null);
  const [handleError, setHandleError] = useState<string | null>(null);

  // Ticket search state
  const [ticketQ, setTicketQ] = useState("");
  const [ticketHandle, setTicketHandle] = useState("");
  const [ticketStatus, setTicketStatus] = useState("");
  const [ticketResults, setTicketResults] = useState<KBSearchResult | null>(null);
  const [ticketPage, setTicketPage] = useState(1);
  const [searching, setSearching] = useState(false);
  const [ticketError, setTicketError] = useState<string | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadHandles = async () => {
    try {
      const res = await apiGet<{ items: HandleRow[] }>("/api/handles?limit=1000&offset=0");
      setHandleRows(Array.isArray(res?.items) ? res.items : []);
      setHandleError(null);
    } catch (e) {
      setHandleError(e instanceof Error ? e.message : String(e));
    }
  };

  const loadStats = async () => {
    try {
      const res = await apiGet<{ total_tickets?: number; db_counts?: { tickets?: number } }>("/api/health");
      setTotalTickets(res.total_tickets ?? res.db_counts?.tickets ?? null);
    } catch {
      // non-critical
    }
  };

  const runTicketSearch = async (q: string, handle: string, status: string, page: number) => {
    setSearching(true);
    setTicketError(null);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (handle) params.set("handle", handle);
      if (status) params.set("status", status);
      params.set("page", String(page));
      params.set("page_size", "20");
      const res = await apiGet<KBSearchResult>(`/api/kb/tickets?${params.toString()}`);
      setTicketResults(res);
    } catch (e) {
      setTicketError(e instanceof Error ? e.message : String(e));
      setTicketResults(null);
    } finally {
      setSearching(false);
    }
  };

  // Debounced search trigger
  useEffect(() => {
    const hasFilter = ticketQ.trim() || ticketHandle || ticketStatus;
    if (!hasFilter) {
      setTicketResults(null);
      return;
    }
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      runTicketSearch(ticketQ, ticketHandle, ticketStatus, ticketPage);
    }, 350);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [ticketQ, ticketHandle, ticketStatus, ticketPage]);

  // Reset page when filters change
  useEffect(() => {
    setTicketPage(1);
  }, [ticketQ, ticketHandle, ticketStatus]);

  useEffect(() => {
    loadHandles().catch(() => undefined);
    loadStats().catch(() => undefined);
    const timer = setInterval(() => {
      loadHandles().catch(() => undefined);
      loadStats().catch(() => undefined);
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  const filteredHandleRows = useMemo(() => {
    const q = handleSearch.trim().toUpperCase();
    const rows = q ? handleRows.filter((r) => r.handle.toUpperCase().includes(q)) : handleRows;
    return [...rows].sort((a, b) => {
      const da = a.last_updated_utc || "";
      const db = b.last_updated_utc || "";
      return db.localeCompare(da);
    });
  }, [handleRows, handleSearch]);

  const totalPages = ticketResults ? Math.ceil(ticketResults.totalCount / ticketResults.pageSize) : 0;

  return (
    <main className={styles.main}>
      <OrchestrationDashboard />

      {/* ── Ticket Search ─────────────────────────────────────────────────── */}
      <section className={styles.kbSection}>
        <h2>Search Tickets</h2>
        <div className={styles.searchRow}>
          <input
            type="search"
            className={styles.searchInput}
            placeholder="Keyword (subject, notes, ticket ID…)"
            value={ticketQ}
            onChange={(e) => setTicketQ(e.target.value)}
          />
          <select
            aria-label="Filter by handle"
            className={styles.searchFilter}
            value={ticketHandle}
            onChange={(e) => setTicketHandle(e.target.value)}
          >
            <option value="">All handles</option>
            {handleRows.map((r) => (
              <option key={r.handle} value={r.handle}>{r.handle}</option>
            ))}
          </select>
          <select
            aria-label="Filter by status"
            className={styles.searchFilter}
            value={ticketStatus}
            onChange={(e) => setTicketStatus(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="Open">Open</option>
            <option value="Closed">Closed</option>
          </select>
        </div>
        {ticketError && <p className={styles.error}>{ticketError}</p>}
        {searching && <p className={styles.subtle}>Searching…</p>}
        {ticketResults && !searching && (
          <>
            <p className={styles.subtle}>
              {ticketResults.totalCount.toLocaleString()} tickets found
              {totalPages > 1 && ` · page ${ticketPage}/${totalPages}`}
            </p>
            <div className={styles.ticketList}>
              {ticketResults.items.map((t) => (
                <div key={`${t.handle}-${t.ticket_id}`} className={styles.ticketCard}>
                  <div className={styles.ticketHeader}>
                    <span className={styles.ticketHandle}>{t.handle}</span>
                    <a href={`/tickets/${encodeURIComponent(t.ticket_id)}`} className={styles.ticketId}>
                      {t.ticket_id}
                    </a>
                    <span className={`${styles.ticketStatus} ${t.status === "Open" ? styles.statusOpen : styles.statusClosed}`}>
                      {t.status || "?"}
                    </span>
                    <span className={styles.ticketDate}>{(t.updated_utc || t.created_utc || "").slice(0, 10)}</span>
                  </div>
                  {t.subject && <div className={styles.ticketSubject}>{t.subject}</div>}
                  {t.notes_preview && (
                    <div className={styles.ticketNotes}>{t.notes_preview}{t.notes_preview.length >= 300 ? "…" : ""}</div>
                  )}
                </div>
              ))}
              {ticketResults.items.length === 0 && (
                <p className={styles.emptyCell}>No tickets match the current filters.</p>
              )}
            </div>
            {totalPages > 1 && (
              <div className={styles.pagination}>
                <button onClick={() => setTicketPage((p) => Math.max(1, p - 1))} disabled={ticketPage <= 1}>
                  ← Prev
                </button>
                <span>{ticketPage} / {totalPages}</span>
                <button onClick={() => setTicketPage((p) => Math.min(totalPages, p + 1))} disabled={ticketPage >= totalPages}>
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {/* ── Handle Summary ────────────────────────────────────────────────── */}
      <section className={styles.kbSection}>
        <h2>Knowledge Base</h2>
        {handleError && <p className={styles.error}>{handleError}</p>}
        <div className={styles.kbStats}>
          <span>Total: {totalTickets !== null ? totalTickets.toLocaleString() : "…"} tickets</span>
          <span>{handleRows.length} handles</span>
        </div>
        <input
          type="search"
          className={styles.search}
          placeholder="Filter handles…"
          value={handleSearch}
          onChange={(e) => setHandleSearch(e.target.value)}
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
            {filteredHandleRows.map((row) => (
              <tr key={row.handle}>
                <td>
                  <a href={`/handles/${encodeURIComponent(row.handle)}`}>{row.handle}</a>
                </td>
                <td>{row.ticket_count ?? 0}</td>
                <td>{row.last_updated_utc ? row.last_updated_utc.slice(0, 10) : "-"}</td>
                <td>{row.status || "-"}</td>
              </tr>
            ))}
            {filteredHandleRows.length === 0 && (
              <tr>
                <td colSpan={4} className={styles.emptyCell}>
                  {handleSearch ? "No handles match filter." : "No handles found."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
