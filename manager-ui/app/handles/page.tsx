'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

type HandleSummary = {
  handle: string;
  ticket_count: number;
  open_count: number;
  last_scrape_utc: string | null;
  updated_latest_utc: string | null;
};

export default function HandlesPage() {
  const [items, setItems] = useState<HandleSummary[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/webscraper/handles?limit=1000`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => { setItems(d.items ?? []); setLoading(false); })
      .catch((e) => { setError(String(e)); setLoading(false); });
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter((h) => h.handle.toLowerCase().includes(q));
  }, [items, search]);

  return (
    <div className="space-y-3">
      <div className="card flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold">Handles ({filtered.length} / {items.length})</h2>
        <input
          className="rounded border border-slate-700 bg-slate-900 px-3 py-1 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          placeholder="Search handles…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {!loading && !error && (
        <div className="card overflow-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                <th className="pb-2 pr-4">Handle</th>
                <th className="pb-2 pr-4 text-right">Tickets</th>
                <th className="pb-2 pr-4 text-right">Open</th>
                <th className="pb-2">Last Scraped</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((h) => (
                <tr key={h.handle} className="border-b border-slate-800 hover:bg-slate-800">
                  <td className="py-1 pr-4 font-mono">
                    <Link href={`/handles/${h.handle}`} className="text-blue-400 hover:underline">
                      {h.handle}
                    </Link>
                  </td>
                  <td className="py-1 pr-4 text-right font-mono">{h.ticket_count ?? 0}</td>
                  <td className="py-1 pr-4 text-right font-mono">
                    <span className={(h.open_count ?? 0) > 0 ? 'text-green-400' : 'text-slate-500'}>
                      {h.open_count ?? 0}
                    </span>
                  </td>
                  <td className="py-1 font-mono text-slate-400">
                    {h.last_scrape_utc ? h.last_scrape_utc.slice(0, 19).replace('T', ' ') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
