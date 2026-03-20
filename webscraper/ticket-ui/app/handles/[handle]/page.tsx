"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../../../lib/api";
import styles from "../../kb.module.css";
import handleStyles from "./handle.module.css";

type HandleLatest = {
  handle: string;
  status?: string;
  error_message?: string;
  finished_utc?: string;
  ticket_count?: number;
};

type Ticket = {
  ticket_id: string;
  title?: string;
  subject?: string;
  status?: string;
  created_utc?: string;
  updated_utc?: string;
  ticket_url?: string;
  priority?: string;
};

type TimelineItem = {
  id: number;
  event_utc: string | null;
  category: string;
  title: string;
  details: string | null;
  ticket_id: string | null;
};

type CompanyDetail = {
  company: Record<string, unknown> | null;
  latest: HandleLatest | null;
};

const CATEGORY_COLOR: Record<string, string> = {
  incident: handleStyles.catIncident,
  outage: handleStyles.catOutage,
  change: handleStyles.catChange,
  request: handleStyles.catRequest,
  maintenance: handleStyles.catMaintenance,
  resolved: handleStyles.catResolved,
};

export default function HandleDetailPage({ params }: { params: { handle: string } }) {
  const handle = decodeURIComponent(params.handle);

  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [ticketFilter, setTicketFilter] = useState("");
  const [building, setBuilding] = useState(false);
  const [buildMsg, setBuildMsg] = useState<string | null>(null);
  const [error] = useState<string | null>(null);

  const load = () => {
    apiGet<CompanyDetail>(`/api/companies/${encodeURIComponent(handle)}`)
      .then(setDetail)
      .catch(() => setDetail(null));
    apiGet<{ items: Ticket[] }>(`/api/handles/${encodeURIComponent(handle)}/tickets?status=any&limit=500`)
      .then((r) => setTickets(Array.isArray(r?.items) ? r.items : []))
      .catch(() => setTickets([]));
    apiGet<{ items: TimelineItem[] }>(`/api/companies/${encodeURIComponent(handle)}/timeline?limit=200`)
      .then((r) => setTimeline(Array.isArray(r?.items) ? r.items : []))
      .catch(() => setTimeline([]));
  };

  useEffect(() => { load(); }, [handle]);

  const buildTimeline = async () => {
    setBuilding(true);
    setBuildMsg(null);
    try {
      const res = await apiPost<{ ok: boolean; timeline_rows_written?: number; ticket_events_written?: number; resolution_patterns_written?: number; error?: string }>(
        "/api/jobs/build-timeline",
        { handle }
      );
      setBuildMsg(
        res.ok
          ? `Done — ${res.timeline_rows_written ?? 0} timeline rows, ${res.ticket_events_written ?? 0} events, ${res.resolution_patterns_written ?? 0} patterns`
          : `Error: ${res.error}`
      );
      if (res.ok) load();
    } catch (e) {
      setBuildMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBuilding(false);
    }
  };

  const latest = detail?.latest ?? null;
  const openCount = tickets.filter((t) => t.status?.toLowerCase() === "open").length;
  const filteredTickets = tickets.filter((t) => {
    if (!ticketFilter.trim()) return true;
    const q = ticketFilter.toLowerCase();
    return (
      t.ticket_id?.toLowerCase().includes(q) ||
      (t.title ?? t.subject ?? "").toLowerCase().includes(q) ||
      t.status?.toLowerCase().includes(q)
    );
  });

  return (
    <main>
      <div className={handleStyles.breadcrumb}>
        <Link href="/">KB</Link> / <span className={handleStyles.handleName}>{handle}</span>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {/* ── Summary card ───────────────────────────────────────────────── */}
      <section className={styles.kbSection}>
        <div className={handleStyles.summaryHeader}>
          <h2 className={handleStyles.handleTitle}>{handle}</h2>
          <div className={handleStyles.buildRow}>
            {buildMsg && <span className={styles.subtle}>{buildMsg}</span>}
            <button
              type="button"
              onClick={buildTimeline}
              disabled={building}
              className={handleStyles.buildBtn}
            >
              {building ? "Building…" : "Build / Refresh Timeline"}
            </button>
          </div>
        </div>
        <div className={handleStyles.statGrid}>
          <div className={handleStyles.statTile}>
            <div className={handleStyles.statLabel}>Total Tickets</div>
            <div className={handleStyles.statValue}>{tickets.length}</div>
          </div>
          <div className={handleStyles.statTile}>
            <div className={handleStyles.statLabel}>Open</div>
            <div className={`${handleStyles.statValue} ${openCount > 0 ? handleStyles.statOpen : ""}`}>{openCount}</div>
          </div>
          <div className={handleStyles.statTile}>
            <div className={handleStyles.statLabel}>Timeline Events</div>
            <div className={handleStyles.statValue}>{timeline.length}</div>
          </div>
          <div className={handleStyles.statTile}>
            <div className={handleStyles.statLabel}>Last Scraped</div>
            <div className={handleStyles.statMono}>
              {latest?.finished_utc ? latest.finished_utc.slice(0, 19).replace("T", " ") : "—"}
            </div>
          </div>
        </div>
      </section>

      {/* ── Timeline ───────────────────────────────────────────────────── */}
      <section className={styles.kbSection}>
        <h2>Timeline</h2>
        {timeline.length === 0 ? (
          <p className={styles.subtle}>
            No timeline built yet. Click <strong>Build / Refresh Timeline</strong> above to generate it from scraped tickets.
          </p>
        ) : (
          <ol className={handleStyles.timeline}>
            {timeline.map((ev) => (
              <li key={ev.id} className={handleStyles.timelineItem}>
                <span className={handleStyles.timelineDate}>
                  {ev.event_utc ? ev.event_utc.slice(0, 10) : "—"}
                </span>
                <span className={`${handleStyles.timelineCat} ${CATEGORY_COLOR[ev.category?.toLowerCase()] ?? ""}`}>
                  {ev.category}
                </span>
                <span className={handleStyles.timelineTitle}>{ev.title}</span>
                {ev.ticket_id && (
                  <Link
                    href={`/tickets/${encodeURIComponent(ev.ticket_id)}?handle=${encodeURIComponent(handle)}`}
                    className={handleStyles.timelineTicketId}
                  >
                    {ev.ticket_id}
                  </Link>
                )}
                {ev.details && <span className={handleStyles.timelineDetails}>{ev.details}</span>}
              </li>
            ))}
          </ol>
        )}
      </section>

      {/* ── Tickets ────────────────────────────────────────────────────── */}
      <section className={styles.kbSection}>
        <div className={handleStyles.sectionHeader}>
          <h2>Tickets ({filteredTickets.length} / {tickets.length})</h2>
          <input
            type="search"
            className={styles.search}
            placeholder="Filter tickets…"
            value={ticketFilter}
            onChange={(e) => setTicketFilter(e.target.value)}
          />
        </div>
        {filteredTickets.length === 0 ? (
          <p className={styles.emptyCell}>No tickets match.</p>
        ) : (
          <div className={styles.ticketList}>
            {filteredTickets.map((t) => (
              <div key={t.ticket_id} className={styles.ticketCard}>
                <div className={styles.ticketHeader}>
                  <Link
                    href={`/tickets/${encodeURIComponent(t.ticket_id)}?handle=${encodeURIComponent(handle)}`}
                    className={styles.ticketId}
                  >
                    {t.ticket_id}
                  </Link>
                  <span className={`${styles.ticketStatus} ${(t.status?.toLowerCase() === "open") ? styles.statusOpen : styles.statusClosed}`}>
                    {t.status || "?"}
                  </span>
                  {t.priority && <span className={styles.subtle}>{t.priority}</span>}
                  <span className={styles.ticketDate}>
                    {(t.updated_utc || t.created_utc || "").slice(0, 10)}
                  </span>
                </div>
                {(t.title ?? t.subject) && (
                  <div className={styles.ticketSubject}>{t.title ?? t.subject}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
