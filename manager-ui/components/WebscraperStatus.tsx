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

type WebscraperData = {
  api_ok: boolean;
  api_target: string;
  db_tickets: number;
  db_handles: number;
  current_state: string;
  backend_health: string;
  last_error: string | null;
  last_successful_scrape: string | null;
  last_scraped_handle: string | null;
  active_job: ActiveJob | null;
  fetch_errors: string[];
  checked_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

async function fetchStatus(): Promise<WebscraperData> {
  const res = await fetch(`${API_BASE}/api/webscraper/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
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

  return (
    <div className="space-y-3">
      {/* Status tile row */}
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs uppercase text-slate-400">Scraper API</h3>
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
            <h3 className="text-xs uppercase text-slate-400">Current State</h3>
            <StatusBadge ok={data?.current_state !== 'error' && data?.api_ok === true} />
          </div>
          <p className="text-sm font-mono">{data?.current_state ?? '…'}</p>
        </div>
      </div>

      {/* Active job */}
      {data?.active_job && (
        <div className="card">
          <h3 className="mb-2 text-xs uppercase text-slate-400">Active Job</h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm font-mono lg:grid-cols-4">
            <div><span className="text-slate-400">id </span>{data.active_job.job_id.slice(0, 8)}…</div>
            <div><span className="text-slate-400">state </span>{data.active_job.state}</div>
            <div><span className="text-slate-400">step </span>{data.active_job.step}</div>
            <div><span className="text-slate-400">written </span>{data.active_job.records_written} / {data.active_job.records_found}</div>
          </div>
        </div>
      )}

      {/* Info row */}
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

      {/* Fetch errors from backend (e.g. 8788 down) */}
      {data && data.fetch_errors.length > 0 && (
        <div className="card border border-red-800 text-xs font-mono text-red-400">
          {data.fetch_errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
    </div>
  );
}
