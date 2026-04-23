'use client';

import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

async function safeFetch(url: string) {
  try {
    const r = await fetch(url, { cache: 'no-store' });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

export function InfraPanel() {
  const [ports, setPorts] = useState<any>(null);
  const [procs, setProcs] = useState<any>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    const load = async () => {
      const [p, pr] = await Promise.all([
        safeFetch(`${API_BASE}/api/system/ports`),
        safeFetch(`${API_BASE}/api/system/processes`),
      ]);
      setPorts(p);
      setProcs(pr);
      setErr(p === null && pr === null);
    };
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  if (err) return <div className="text-xs text-slate-500 font-mono">Manager API unreachable — retrying…</div>;

  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
      <div>
        <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Ports</h3>
        {ports ? (
          <pre className="rounded bg-black p-2 text-xs font-mono text-slate-300 overflow-auto max-h-48">
            {JSON.stringify(ports, null, 2)}
          </pre>
        ) : <div className="text-xs text-slate-600">Loading…</div>}
      </div>
      <div>
        <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-500">Processes</h3>
        {procs ? (
          <div className="space-y-0.5 max-h-48 overflow-auto">
            {(procs.processes ?? []).slice(0, 20).map((p: any, i: number) => (
              <div key={i} className="flex gap-2 text-xs font-mono text-slate-400">
                <span className="w-12 shrink-0 text-slate-200">{p.pid}</span>
                <span className="truncate">{p.name ?? p.cmdline ?? '—'}</span>
              </div>
            ))}
          </div>
        ) : <div className="text-xs text-slate-600">Loading…</div>}
      </div>
    </div>
  );
}
