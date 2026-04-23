'use client';

import { useEffect, useState } from 'react';
import { StatusCard } from './StatusCard';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

type StatusData = {
  summary: any;
  db: any;
  dbIntegrity: any;
  apiOk: boolean;
};

const EMPTY: StatusData = { summary: null, db: null, dbIntegrity: null, apiOk: false };

async function fetchStatus(): Promise<StatusData> {
  const [summary, db, dbIntegrity] = await Promise.all([
    fetch(`${API_BASE}/api/status/summary`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch(`${API_BASE}/api/db/summary`,      { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch(`${API_BASE}/api/db/integrity`,    { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
  ]);
  return { summary, db, dbIntegrity, apiOk: summary !== null };
}

export function DashboardStatus() {
  const [data, setData] = useState<StatusData>(EMPTY);

  useEffect(() => {
    fetchStatus().then(setData);
    const t = setInterval(() => fetchStatus().then(setData), 6000);
    return () => clearInterval(t);
  }, []);

  const { summary, db, dbIntegrity, apiOk } = data;

  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      <StatusCard title="API Health" ok={apiOk} summary={apiOk ? 'FastAPI online' : 'unreachable'} />
      <StatusCard
        title="Scraper Worker"
        ok={summary ? !summary.worker?.paused : false}
        summary={summary ? (summary.worker?.paused ? 'paused' : 'running') : '…'}
      />
      <StatusCard
        title="Database"
        ok={db?.file_exists ?? false}
        summary={db ? (db.file_exists ? `${db.tickets_count ?? 0} tickets` : 'not found') : '…'}
      />
      <StatusCard
        title="DB Integrity"
        ok={dbIntegrity?.ok ?? false}
        summary={dbIntegrity ? (dbIntegrity.result ?? dbIntegrity.message ?? 'unknown') : '…'}
      />
    </div>
  );
}
