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

async function fetchServiceLogs(): Promise<Record<string, string[]>> {
  try {
    const res = await fetch(`${API_BASE}/api/logs/files`, { cache: 'no-store' });
    const json = await res.json();
    return json.services ?? {};
  } catch {
    return {};
  }
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
  const [serviceLogs, setServiceLogs] = useState<Record<string, string[]>>({});
  const [activeService, setActiveService] = useState<string>('');
  const bottomRef = useRef<HTMLDivElement>(null);

  const reload = () =>
    fetchCombined()
      .then((evs) => { setEvents(evs); setErr(null); })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));

  const reloadServiceLogs = () =>
    fetchServiceLogs().then((logs) => {
      setServiceLogs(logs);
      setActiveService((prev) => (prev && logs[prev] ? prev : Object.keys(logs)[0] ?? ''));
    });

  useEffect(() => {
    reload();
    reloadServiceLogs();
    const t = setInterval(reload, 3000);
    const t2 = setInterval(reloadServiceLogs, 3000);
    return () => { clearInterval(t); clearInterval(t2); };
  }, []);

  const serviceNames = Object.keys(serviceLogs);
  const activeLines = activeService ? (serviceLogs[activeService] ?? []) : [];

  return (
    <div className="space-y-3">
      {/* Existing event log */}
      <div>
        {err && <p className="mb-1 text-xs text-red-400">{err}</p>}
        <pre className="h-64 overflow-auto rounded bg-black p-2 text-xs">
          {events.length === 0 ? 'No events yet.' : events.map(fmtLine).join('\n')}
          <div ref={bottomRef} />
        </pre>
      </div>

      {/* Service log file viewer */}
      {serviceNames.length > 0 && (
        <div>
          <div className="mb-1 flex flex-wrap gap-1">
            {serviceNames.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => setActiveService(name)}
                className={`rounded px-2 py-0.5 text-xs font-mono ${
                  name === activeService
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {name}
              </button>
            ))}
          </div>
          <pre className="h-64 overflow-auto rounded bg-black p-2 text-xs text-slate-300">
            {activeLines.length === 0
              ? `No output yet for ${activeService}.`
              : activeLines.join('\n')}
          </pre>
        </div>
      )}
    </div>
  );
}
