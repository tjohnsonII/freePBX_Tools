'use client';

import { useEffect, useState } from 'react';
import { StatusBadge } from './StatusBadge';

type ActiveJob = {
  job_id: string;
  state: string;
  step: string;
  records_found: number;
  records_written: number;
};

type ClientInfo = {
  client_id: string;
  connectivity: 'connected' | 'recent' | 'offline';
  last_seen_ago_s: number;
  last_seen_utc: string;
  status: string;
  job_id: string | null;
  current_handle: string | null;
  handles_done: number;
  handles_total: number;
  client_version: string | null;
};

type WebscraperData = {
  api_ok: boolean;
  api_target: string;
  db_tickets: number;
  db_handles: number;
  current_state: string;
  backend_health: string;
  last_error: string | null;
  last_scraped_handle: string | null;
  active_job: ActiveJob | null;
  client: ClientInfo | null;
  clients: ClientInfo[];
  fetch_errors: string[];
  checked_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

async function fetchStatus(): Promise<WebscraperData> {
  const res = await fetch(`${API_BASE}/api/webscraper/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function fmtAge(s: number): string {
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function connectivityColor(c: ClientInfo['connectivity']): string {
  return c === 'connected' ? 'text-green-400' : c === 'recent' ? 'text-yellow-400' : 'text-slate-500';
}

function connectivityDot(c: ClientInfo['connectivity']): string {
  return c === 'connected' ? '●' : c === 'recent' ? '◑' : '○';
}

export function WebscraperStatus() {
  const [data, setData] = useState<WebscraperData | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [lastPulse, setLastPulse] = useState<Date | null>(null);

  const reload = () =>
    fetchStatus()
      .then((d) => { setData(d); setLoadErr(null); setLastPulse(new Date()); })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)));

  useEffect(() => {
    reload();
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, []);

  const client = data?.client ?? null;
  const pct = client && client.handles_total > 0
    ? Math.round((client.handles_done / client.handles_total) * 100)
    : null;

  return (
    <div className="space-y-3">
      {/* Top stat tiles */}
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs uppercase text-slate-400">Ticket API</h3>
            <StatusBadge ok={data?.api_ok ?? false} />
          </div>
          <p className="text-sm">{data ? (data.api_ok ? 'online' : 'offline') : '…'}</p>
        </div>

        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs uppercase text-slate-400">DB Tickets</h3>
            <StatusBadge ok={(data?.db_tickets ?? 0) > 0} />
          </div>
          <p className="text-sm font-mono">{data?.db_tickets ?? '…'}</p>
        </div>

        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs uppercase text-slate-400">DB Handles</h3>
            <StatusBadge ok={(data?.db_handles ?? 0) > 0} />
          </div>
          <p className="text-sm font-mono">{data?.db_handles ?? '…'}</p>
        </div>

        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs uppercase text-slate-400">Scrape State</h3>
            <StatusBadge ok={data?.current_state === 'running'} />
          </div>
          <p className="text-sm font-mono">{data?.current_state ?? '…'}</p>
        </div>
      </div>

      {/* Client laptop status */}
      <div className="card">
        <h3 className="mb-3 text-xs uppercase text-slate-400">Client Laptop</h3>
        {!data ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : !client ? (
          <p className="text-sm text-slate-500">No heartbeat received yet — client has not connected.</p>
        ) : (
          <div className="space-y-3">
            {/* Connectivity + status row */}
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
              <span className={`font-mono font-bold ${connectivityColor(client.connectivity)}`}>
                {connectivityDot(client.connectivity)}{' '}
                {client.connectivity === 'connected' ? 'Connected' : client.connectivity === 'recent' ? 'Recently active' : 'Offline'}
              </span>
              <span className="text-slate-400">
                last seen <span className="text-slate-200">{fmtAge(client.last_seen_ago_s)}</span>
              </span>
              <span className="text-slate-400">
                status <span className="font-mono text-slate-200">{client.status ?? '—'}</span>
              </span>
              {client.client_id && (
                <span className="text-slate-400">
                  id <span className="font-mono text-slate-200">{client.client_id}</span>
                </span>
              )}
              {client.client_version && (
                <span className="text-slate-400">
                  v<span className="font-mono text-slate-200">{client.client_version}</span>
                </span>
              )}
            </div>

            {/* Progress bar — only when scraping */}
            {client.handles_total > 0 && (
              <div>
                <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
                  <span>
                    handle{' '}
                    <span className="font-mono text-slate-200">
                      {client.current_handle ?? '—'}
                    </span>
                  </span>
                  <span className="font-mono text-slate-200">
                    {client.handles_done} / {client.handles_total}
                    {pct !== null ? ` (${pct}%)` : ''}
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700">
                  <div
                    className="h-2 rounded-full bg-blue-500 transition-all duration-500"
                    style={{ width: `${pct ?? 0}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Active server-side job (from DB) */}
      {data?.active_job && (
        <div className="card">
          <h3 className="mb-2 text-xs uppercase text-slate-400">Active Job (DB)</h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm font-mono lg:grid-cols-4">
            <div><span className="text-slate-400">id </span>{data.active_job.job_id.slice(0, 8)}…</div>
            <div><span className="text-slate-400">state </span>{data.active_job.state}</div>
            <div><span className="text-slate-400">step </span>{data.active_job.step}</div>
            <div><span className="text-slate-400">written </span>{data.active_job.records_written} / {data.active_job.records_found}</div>
          </div>
        </div>
      )}

      {/* Footer row */}
      <div className="card">
        <div className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs font-mono text-slate-400 lg:grid-cols-3">
          <div><span className="text-slate-300">last handle </span>{data?.last_scraped_handle ?? 'none'}</div>
          <div><span className="text-slate-300">last error </span>{data?.last_error ?? 'none'}</div>
          <div>
            <span className="text-slate-300">heartbeat </span>
            {lastPulse ? lastPulse.toLocaleTimeString() : '—'}
            {loadErr && <span className="ml-2 text-red-400">{loadErr}</span>}
          </div>
        </div>
      </div>

      {data && data.fetch_errors.length > 0 && (
        <div className="card border border-red-800 text-xs font-mono text-red-400">
          {data.fetch_errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
    </div>
  );
}
