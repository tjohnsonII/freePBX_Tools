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

// ── Pairing types ──────────────────────────────────────────────────────────────

type PairedEntry    = { kind: 'paired';     openEv: TimelineItem; closeEv: TimelineItem | null };
type StandaloneEntry = { kind: 'standalone'; ev: TimelineItem };
type TlEntry = PairedEntry | StandaloneEntry;

const CLOSE_CATS = new Set(['resolved', 'phone_replacement']);

function pairTimeline(items: TimelineItem[]): TlEntry[] {
  // First pass: find the first (most-recent in desc order) close event per ticket
  const closeByTicket = new Map<string, TimelineItem>();
  const openTicketIds = new Set<string>();
  for (const ev of items) {
    const cat = ev.category?.toLowerCase() ?? '';
    if (!ev.ticket_id) continue;
    if (CLOSE_CATS.has(cat) && !closeByTicket.has(ev.ticket_id))
      closeByTicket.set(ev.ticket_id, ev);
    if (cat === 'ticket_opened')
      openTicketIds.add(ev.ticket_id);
  }

  // Mark which close-event IDs are claimed by a matching open
  const claimedIds = new Set<number>();
  for (const tid of openTicketIds) {
    const c = closeByTicket.get(tid);
    if (c) claimedIds.add(c.id);
  }

  // Second pass: build result list, skip claimed close events
  const emittedOpens = new Set<string>();
  const result: TlEntry[] = [];
  for (const ev of items) {
    if (claimedIds.has(ev.id)) continue;
    const cat = ev.category?.toLowerCase() ?? '';
    if (cat === 'ticket_opened' && ev.ticket_id) {
      if (emittedOpens.has(ev.ticket_id)) continue;
      emittedOpens.add(ev.ticket_id);
      result.push({ kind: 'paired', openEv: ev, closeEv: closeByTicket.get(ev.ticket_id) ?? null });
      continue;
    }
    result.push({ kind: 'standalone', ev });
  }
  return result;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const TIMESTAMP_RE = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/;

function parseDetails(raw: string | null): string | null {
  if (!raw) return null;
  const jsonIdx = raw.indexOf(' | {');
  if (jsonIdx > 0) {
    try {
      const data = JSON.parse(raw.slice(jsonIdx + 3));
      const notes: string = data?.detail?.notes ?? '';
      if (notes) {
        const first = notes.split(/\n(?:\s*\n|---|\s*From:|-----)/)[0].trim();
        if (first && !TIMESTAMP_RE.test(first))
          return first.length > 200 ? first.slice(0, 200) + '…' : first;
      }
      const subject = data?.subject ?? '';
      const status  = data?.status  ?? '';
      return [subject, status].filter(Boolean).join(' · ') || null;
    } catch { /* fall through */ }
  }
  const trimmed = (jsonIdx > 0 ? raw.slice(0, jsonIdx) : raw).trim();
  if (TIMESTAMP_RE.test(trimmed)) return null;
  return trimmed.length > 140 ? trimmed.slice(0, 140) + '…' : trimmed || null;
}

function durationLabel(openUtc: string | null, closeUtc: string | null): string | null {
  if (!openUtc || !closeUtc) return null;
  const days = Math.round((new Date(closeUtc).getTime() - new Date(openUtc).getTime()) / 86400000);
  if (isNaN(days)) return null;
  if (days === 0) return 'same day';
  return `${days} day${days === 1 ? '' : 's'}`;
}

function openAgeLabel(openUtc: string | null): string {
  if (!openUtc) return 'open';
  const days = Math.round((Date.now() - new Date(openUtc).getTime()) / 86400000);
  if (isNaN(days) || days < 0) return 'open';
  if (days === 0) return 'opened today';
  return `open ${days} day${days === 1 ? '' : 's'}`;
}

type TlStyle = { dot: string; card: string; badge: string; label: string };

function tlStyle(cat: string, s: typeof handleStyles): TlStyle {
  switch (cat) {
    case 'incident':
    case 'outage':
      return { dot: s.tlDotProblem,  card: s.tlCardProblem,     badge: s.tlBadgeProblem,     label: 'PROBLEM'     };
    case 'resolved':
      return { dot: s.tlDotResolved, card: s.tlCardResolved,    badge: s.tlBadgeResolved,    label: 'RESOLVED'    };
    case 'change':
      return { dot: s.tlDotChange,   card: s.tlCardChange,      badge: s.tlBadgeChange,      label: 'CHANGE'      };
    case 'maintenance':
      return { dot: s.tlDotMaint,    card: s.tlCardMaintenance, badge: s.tlBadgeMaintenance, label: 'MAINTENANCE' };
    case 'request':
      return { dot: s.tlDotDefault,  card: s.tlCardRequest,     badge: s.tlBadgeRequest,     label: 'REQUEST'     };
    case 'phone_replacement':
      return { dot: s.tlDotResolved, card: s.tlCardResolved,    badge: s.tlBadgeResolved,    label: 'REPAIRED'    };
    default:
      return { dot: s.tlDotDefault,  card: s.tlCardDefault,     badge: s.tlBadgeDefault,     label: cat.toUpperCase() || 'EVENT' };
  }
}

// ── Page ───────────────────────────────────────────────────────────────────────

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

  const latest      = detail?.latest ?? null;
  const openCount   = tickets.filter((t) => t.status?.toLowerCase() === "open").length;
  const tlEntries   = pairTimeline(timeline);
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
          <ol className={handleStyles.tlList}>
            {tlEntries.map((entry) => {
              if (entry.kind === 'paired') {
                const { openEv, closeEv } = entry;
                const isResolved = closeEv !== null;
                const closeCat   = closeEv?.category?.toLowerCase() ?? '';
                const closeLabel = closeCat === 'phone_replacement' ? 'REPAIRED' : 'RESOLVED';
                const dur        = isResolved
                  ? durationLabel(openEv.event_utc, closeEv!.event_utc)
                  : openAgeLabel(openEv.event_utc);
                const openDetail  = parseDetails(openEv.details);
                const closeDetail = isResolved ? parseDetails(closeEv!.details) : null;
                const showClose   = !!closeDetail;
                const showOpen    = !!openDetail && openDetail !== closeDetail;

                return (
                  <li key={openEv.id} className={handleStyles.tlItem}>
                    <div className={`${handleStyles.tlDot} ${isResolved ? handleStyles.tlDotResolved : handleStyles.tlDotOpen}`} />
                    <div className={`${handleStyles.tlCard} ${isResolved ? handleStyles.tlCardResolved : handleStyles.tlCardOpen}`}>
                      <div className={handleStyles.tlCardTop}>
                        <span className={handleStyles.tlDate}>
                          {openEv.event_utc ? openEv.event_utc.slice(0, 10) : '—'}
                        </span>
                        <span className={`${handleStyles.tlBadge} ${handleStyles.tlBadgeChange}`}>OPENED</span>
                        {isResolved && (
                          <>
                            <span className={handleStyles.tlArrow}>→</span>
                            <span className={`${handleStyles.tlBadge} ${handleStyles.tlBadgeResolved}`}>{closeLabel}</span>
                          </>
                        )}
                        {!isResolved && (
                          <span className={`${handleStyles.tlBadge} ${handleStyles.tlBadgeOpen}`}>STILL OPEN</span>
                        )}
                        {dur && <span className={handleStyles.tlDuration}>{dur}</span>}
                        <span className={handleStyles.tlTitle}>
                          {openEv.title?.replace(/^Ticket (?:opened|closed):\s*/i, '')}
                        </span>
                        {openEv.ticket_id && (
                          <Link
                            href={`/tickets/${encodeURIComponent(openEv.ticket_id)}?handle=${encodeURIComponent(handle)}`}
                            className={handleStyles.tlTicketId}
                          >
                            {openEv.ticket_id}
                          </Link>
                        )}
                      </div>
                      {(showClose || showOpen) && (
                        <div className={handleStyles.tlPairNotes}>
                          {showClose && (
                            <div className={handleStyles.tlPairNote}>
                              <span className={handleStyles.tlPairLabel}>Closed:</span>{closeDetail}
                            </div>
                          )}
                          {showOpen && (
                            <div className={handleStyles.tlPairNote}>
                              <span className={handleStyles.tlPairLabel}>Opened:</span>{openDetail}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                );
              }

              // Standalone event (incident, change, maintenance, orphan close, etc.)
              const { ev } = entry;
              const cat    = ev.category?.toLowerCase() ?? '';
              const ts     = tlStyle(cat, handleStyles);
              const detail = parseDetails(ev.details);
              return (
                <li key={ev.id} className={handleStyles.tlItem}>
                  <div className={`${handleStyles.tlDot} ${ts.dot}`} />
                  <div className={`${handleStyles.tlCard} ${ts.card}`}>
                    <div className={handleStyles.tlCardTop}>
                      <span className={handleStyles.tlDate}>
                        {ev.event_utc ? ev.event_utc.slice(0, 10) : '—'}
                      </span>
                      <span className={`${handleStyles.tlBadge} ${ts.badge}`}>{ts.label}</span>
                      <span className={handleStyles.tlTitle}>{ev.title?.replace(/^Ticket (?:opened|closed):\s*/i, '')}</span>
                      {ev.ticket_id && (
                        <Link
                          href={`/tickets/${encodeURIComponent(ev.ticket_id)}?handle=${encodeURIComponent(handle)}`}
                          className={handleStyles.tlTicketId}
                        >
                          {ev.ticket_id}
                        </Link>
                      )}
                    </div>
                    {detail && <div className={handleStyles.tlDetail}>{detail}</div>}
                  </div>
                </li>
              );
            })}
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
