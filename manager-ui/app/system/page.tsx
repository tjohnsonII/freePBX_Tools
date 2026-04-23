'use client';

import { useEffect, useState } from 'react';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

async function safeFetch(url: string) {
  try {
    const r = await fetch(url, { cache: 'no-store' });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

export default function SystemPage() {
  const [data, setData] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const [ports, processes, env, paths, diag] = await Promise.all([
        safeFetch(`${API_BASE}/api/system/ports`),
        safeFetch(`${API_BASE}/api/system/processes`),
        safeFetch(`${API_BASE}/api/system/env`),
        safeFetch(`${API_BASE}/api/system/paths`),
        safeFetch(`${API_BASE}/api/diagnostics/system`),
      ]);
      setData({ ports, processes, env, paths, diag });
      setLoading(false);
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  if (loading) {
    return <div className="text-sm text-slate-500 p-4">Loading system data…</div>;
  }

  const unavailable = (label: string) => (
    <div className="text-xs text-slate-500 font-mono">Manager API unreachable — {label} unavailable</div>
  );

  return (
    <div className="space-y-2">
      <SectionCard title="Ports">
        {data.ports ? <DataPreviewTable rows={[data.ports]} /> : unavailable('ports')}
      </SectionCard>
      <SectionCard title="Processes">
        {data.processes ? <DataPreviewTable rows={data.processes.processes || []} /> : unavailable('processes')}
      </SectionCard>
      <SectionCard title="Env">
        {data.env ? <DataPreviewTable rows={[data.env]} /> : unavailable('env')}
      </SectionCard>
      <SectionCard title="Paths">
        {data.paths ? <DataPreviewTable rows={[data.paths]} /> : unavailable('paths')}
      </SectionCard>
      <SectionCard title="System Diagnostics">
        {data.diag ? <DataPreviewTable rows={[data.diag]} /> : unavailable('diagnostics')}
      </SectionCard>
    </div>
  );
}
