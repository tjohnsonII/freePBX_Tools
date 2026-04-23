'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

type Ticket = {
  ticket_id: string;
  subject: string | null;
  status: string | null;
  created_at: string | null;
  updated_at: string | null;
  priority: string | null;
};

type TimelineItem = {
  id: number;
  event_utc: string | null;
  category: string;
  title: string;
  details: string | null;
  ticket_id: string | null;
};

type CompanyData = {
  handle: string;
  company: Record<string, unknown> | null;
  latest: Record<string, unknown> | null;
  tickets: Ticket[];
  timeline: TimelineItem[];
  errors: string[];
};

const CATEGORY_COLORS: Record<string, string> = {
  incident: 'text-red-400',
  outage: 'text-red-400',
  change: 'text-blue-400',
  request: 'text-green-400',
  maintenance: 'text-yellow-400',
  resolved: 'text-slate-400',
};

function categoryColor(cat: string): string {
  return CATEGORY_COLORS[cat?.toLowerCase()] ?? 'text-slate-300';
}

export default function HandleDetailPage() {
  const params = useParams();
  const handle = params?.handle as string;

  const [data, setData] = useState<CompanyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [buildResult, setBuildResult] = useState<string | null>(null);
  const [ticketFilter, setTicketFilter] = useState('');

  const load = () => {
    setLoading(true);
    fetch(`${API_BASE}/api/webscraper/company/${encodeURIComponent(handle)}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(String(e)); setLoading(false); });
  };

  useEffect(() => { if (handle) load(); }, [handle]);

  const buildTimeline = async () => {
    setBuilding(true);
    setBuildResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/webscraper/company/${encodeURIComponent(handle)}/build-timeline`, {
        method: 'POST',
      });
      const json = await res.json();
      setBuildResult(json.ok
        ? `Built — ${json.timeline_rows_written ?? 0} timeline rows, ${json.ticket_events_written ?? 0} events, ${json.resolution_patterns_written ?? 0} patterns`
        : `Error: ${json.error}`
      );
      if (json.ok) load();
    } catch (e) {
      setBuildResult(`Error: ${String(e)}`);
    } finally {
      setBuilding(false);
    }
  };

  const filteredTickets = data?.tickets.filter((t) => {
    if (!ticketFilter.trim()) return true;
    const q = ticketFilter.toLowerCase();
    return (
      t.ticket_id?.toLowerCase().includes(q) ||
      t.subject?.toLowerCase().includes(q) ||
      t.status?.toLowerCase().includes(q)
    );
  }) ?? [];

  const latest = data?.latest ?? {};
  const totalTickets = data?.tickets.length ?? 0;
  const openTickets = data?.tickets.filter((t) => t.status?.toLowerCase() === 'open').length ?? 0;

  return (
    <div className="space-y-3">
      {/* Breadcrumb */}
      <div className="text-xs text-slate-500">
        <Link href="/handles" className="hover:text-slate-300">Handles</Link>
        <span className="mx-2">/</span>
        <span className="font-mono text-slate-200">{handle}</span>
      </div>

      {loading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {data && (
        <>
          {/* Summary card */}
          <div className="card">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-mono text-lg font-semibold text-slate-100">{handle}</h2>
              <div className="flex items-center gap-2">
                {buildResult && <span className="text-xs text-slate-400">{buildResult}</span>}
                <button
                  onClick={buildTimeline}
                  disabled={building}
                  className="rounded bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600 disabled:opacity-50"
                >
                  {building ? 'Building…' : 'Build / Refresh Timeline'}
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs lg:grid-cols-4">
              <div>
                <div className="text-slate-400">Total Tickets</div>
                <div className="font-mono text-lg text-slate-100">{totalTickets}</div>
              </div>
              <div>
                <div className="text-slate-400">Open Tickets</div>
                <div className={`font-mono text-lg ${openTickets > 0 ? 'text-green-400' : 'text-slate-500'}`}>{openTickets}</div>
              </div>
              <div>
                <div className="text-slate-400">Last Scraped</div>
                <div className="font-mono text-slate-200">{(latest.finished_utc as string)?.slice(0, 19).replace('T', ' ') ?? '—'}</div>
              </div>
              <div>
                <div className="text-slate-400">Timeline Events</div>
                <div className="font-mono text-slate-200">{data.timeline.length}</div>
              </div>
            </div>
            {data.errors.length > 0 && (
              <div className="mt-2 text-xs text-red-400">{data.errors.join(' · ')}</div>
            )}
          </div>

          {/* Timeline */}
          {data.timeline.length > 0 ? (
            <div className="card">
              <h3 className="mb-3 text-xs font-semibold uppercase text-slate-400">Timeline</h3>
              <ol className="space-y-2">
                {data.timeline.map((ev) => (
                  <li key={ev.id} className="flex gap-3 text-xs">
                    <span className="w-36 shrink-0 font-mono text-slate-500">
                      {ev.event_utc ? ev.event_utc.slice(0, 10) : '—'}
                    </span>
                    <span className={`w-24 shrink-0 font-mono ${categoryColor(ev.category)}`}>{ev.category}</span>
                    <span className="text-slate-200">{ev.title}</span>
                    {ev.ticket_id && (
                      <span className="ml-auto shrink-0 font-mono text-slate-500">{ev.ticket_id}</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <div className="card text-xs text-slate-500">
              No timeline built yet. Click <strong className="text-slate-300">Build / Refresh Timeline</strong> above to generate it.
            </div>
          )}

          {/* Tickets */}
          <div className="card">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase text-slate-400">
                Tickets ({filteredTickets.length} / {totalTickets})
              </h3>
              <input
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
                placeholder="Filter tickets…"
                value={ticketFilter}
                onChange={(e) => setTicketFilter(e.target.value)}
              />
            </div>
            <div className="overflow-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-400">
                    <th className="pb-2 pr-4">Ticket ID</th>
                    <th className="pb-2 pr-4">Subject</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Priority</th>
                    <th className="pb-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTickets.map((t) => (
                    <tr key={t.ticket_id} className="border-b border-slate-800 hover:bg-slate-800">
                      <td className="py-1 pr-4 font-mono text-slate-300">{t.ticket_id}</td>
                      <td className="py-1 pr-4 max-w-xs truncate text-slate-200">{t.subject ?? '—'}</td>
                      <td className="py-1 pr-4">
                        <span className={`font-mono ${t.status?.toLowerCase() === 'open' ? 'text-green-400' : 'text-slate-500'}`}>
                          {t.status ?? '—'}
                        </span>
                      </td>
                      <td className="py-1 pr-4 font-mono text-slate-400">{t.priority ?? '—'}</td>
                      <td className="py-1 font-mono text-slate-500">
                        {t.created_at ? t.created_at.slice(0, 10) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
