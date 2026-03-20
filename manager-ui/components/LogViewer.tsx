'use client';
import { useEffect, useRef, useState } from 'react';
import { EventItem } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

async function fetchCombined(): Promise<EventItem[]> {
  const [managerRes, scraperRes] = await Promise.allSettled([
    fetch(`${API_BASE}/api/logs/recent`, { cache: 'no-store' }).then((r) => r.json()),
    fetch(`${API_BASE}/api/webscraper/events`, { cache: 'no-store' }).then((r) => r.json()),
  ]);

  const managerEvents: EventItem[] = managerRes.status === 'fulfilled' ? (managerRes.value.events ?? []) : [];
  const scraperEvents: EventItem[] = scraperRes.status === 'fulfilled' ? (scraperRes.value.events ?? []) : [];

  return [...managerEvents, ...scraperEvents].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

function fmtLine(e: EventItem): string {
  const ts = e.timestamp.slice(0, 19).replace('T', ' ');
  const lvl = e.level.toUpperCase().padEnd(5);
  const cat = `[${e.category}]`.padEnd(10);
  return `${ts} ${lvl} ${cat} ${e.message}`;
}

export function LogViewer() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const reload = () =>
    fetchCombined()
      .then((evs) => { setEvents(evs); setErr(null); })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));

  useEffect(() => {
    reload();
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  return (
    <div>
      {err && <p className="mb-1 text-xs text-red-400">{err}</p>}
      <pre className="h-64 overflow-auto rounded bg-black p-2 text-xs">
        {events.length === 0 ? 'No events yet.' : events.map(fmtLine).join('\n')}
        <div ref={bottomRef} />
      </pre>
    </div>
  );
}
