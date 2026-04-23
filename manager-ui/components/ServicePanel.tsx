'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8787';

// ── types ─────────────────────────────────────────────────────────────────────
type Service = {
  name: string;
  label: string;
  group: string;
  pid: number | null;
  pid_alive: boolean;
  port: number | null;
  port_up: boolean | null;
  log: string | null;
  started_at: number | null;
};

type LogState = { lines: string[]; loading: boolean };

// ── helpers ───────────────────────────────────────────────────────────────────
function isUp(svc: Service): boolean {
  if (svc.port !== null) return svc.port_up === true;
  return svc.pid_alive;
}

function uptimeStr(started_at: number | null): string {
  if (!started_at) return '—';
  const secs = Math.floor(Date.now() / 1000) - started_at;
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

// ── group ordering/labels ─────────────────────────────────────────────────────
const GROUP_ORDER = ['manager', 'scraper', 'extras', 'system'];
const GROUP_LABELS: Record<string, string> = {
  manager: 'Manager Stack',
  scraper: 'Scraper Stack',
  extras:  'Extra Services',
  system:  'System Infrastructure',
};

// ── API calls ─────────────────────────────────────────────────────────────────
async function fetchServices(): Promise<Service[]> {
  const res = await fetch(`${API_BASE}/api/services`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()).services as Service[];
}

async function callRestart(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/services/${name}/restart`, { method: 'POST' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
}

async function callFullRestart(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/services/full-restart`, { method: 'POST' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

async function fetchLogs(name: string): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/services/${name}/logs?lines=120`, { cache: 'no-store' });
  if (!res.ok) return [];
  return (await res.json()).lines as string[];
}

// ── LogDrawer ─────────────────────────────────────────────────────────────────
function LogDrawer({ name, onClose }: { name: string; onClose: () => void }) {
  const [state, setState] = useState<LogState>({ lines: [], loading: true });
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const lines = await fetchLogs(name);
    setState({ lines, loading: false });
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, [name]);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="mt-2 rounded border border-slate-700 bg-black">
      <div className="flex items-center justify-between border-b border-slate-700 px-2 py-1">
        <span className="text-xs font-mono text-slate-400">{name}.log</span>
        <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-200">✕ close</button>
      </div>
      <pre className="h-48 overflow-auto p-2 text-xs text-slate-300 font-mono leading-relaxed">
        {state.loading
          ? 'Loading…'
          : state.lines.length === 0
          ? 'No log output yet.'
          : state.lines.join('\n')}
        <div ref={bottomRef} />
      </pre>
    </div>
  );
}

// ── ServiceCard ───────────────────────────────────────────────────────────────
function ServiceCard({ svc }: { svc: Service }) {
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);
  const up = isUp(svc);

  const handleRestart = async () => {
    setRestarting(true);
    setError(null);
    try {
      await callRestart(svc.name);
      await new Promise((r) => setTimeout(r, 1800));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRestarting(false);
    }
  };

  return (
    <div className={`rounded-lg border p-3 flex flex-col gap-2 transition-colors ${
      up ? 'border-slate-700 bg-slate-900' : 'border-rose-900 bg-slate-900'
    }`}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold leading-tight">{svc.label}</span>
        <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-bold ${
          up ? 'bg-emerald-800 text-emerald-200' : 'bg-rose-900 text-rose-200'
        }`}>
          {up ? '● UP' : '○ DOWN'}
        </span>
      </div>

      {/* Meta row */}
      <div className="text-xs font-mono text-slate-400 space-y-0.5">
        {svc.port && (
          <div className="flex justify-between">
            <span>port</span>
            <span className={svc.port_up ? 'text-slate-200' : 'text-rose-400'}>:{svc.port}</span>
          </div>
        )}
        {svc.pid && (
          <div className="flex justify-between">
            <span>pid</span>
            <span className={svc.pid_alive ? 'text-slate-200' : 'text-rose-400'}>
              {svc.pid}{svc.pid_alive ? '' : ' ✗'}
            </span>
          </div>
        )}
        {svc.started_at && (
          <div className="flex justify-between">
            <span>uptime</span>
            <span className="text-slate-200">{uptimeStr(svc.started_at)}</span>
          </div>
        )}
        {!svc.port && !svc.pid && (
          <span className="text-slate-600">not tracked</span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded bg-rose-950 px-2 py-1 text-xs text-rose-300 font-mono break-all">
          {error}
        </div>
      )}

      {/* Action row */}
      <div className="mt-auto flex gap-1.5">
        <button
          onClick={handleRestart}
          disabled={restarting}
          className="flex-1 rounded bg-slate-700 py-1.5 text-xs font-medium hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {restarting ? '⟳ Restarting…' : '↺ Restart'}
        </button>
        {svc.log && (
          <button
            onClick={() => setShowLog((v) => !v)}
            className={`rounded px-2.5 py-1.5 text-xs transition-colors ${
              showLog ? 'bg-blue-700 hover:bg-blue-600' : 'bg-slate-700 hover:bg-slate-600'
            }`}
            title="Toggle log"
          >
            ≡ Logs
          </button>
        )}
      </div>

      {showLog && <LogDrawer name={svc.name} onClose={() => setShowLog(false)} />}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────
export function ServicePanel() {
  const [services, setServices] = useState<Service[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [fullRestarting, setFullRestarting] = useState(false);
  const [fullRestartMsg, setFullRestartMsg] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const reload = useCallback(() =>
    fetchServices()
      .then((s) => { setServices(s); setLoadErr(null); setLastRefresh(new Date()); })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e))),
  []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 4000);
    return () => clearInterval(t);
  }, [reload]);

  const handleFullRestart = async () => {
    if (!confirm('Run FULL_START.sh? This restarts ALL services including VPN and Apache.')) return;
    setFullRestarting(true);
    setFullRestartMsg(null);
    try {
      await callFullRestart();
      setFullRestartMsg('FULL_START.sh launched — services restarting in background.');
    } catch (e) {
      setFullRestartMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setFullRestarting(false);
    }
  };

  // Group services
  const grouped: Record<string, Service[]> = {};
  for (const svc of services) {
    (grouped[svc.group] ??= []).push(svc);
  }

  const upCount = services.filter(isUp).length;
  const totalCount = services.length;

  return (
    <div className="space-y-4">
      {/* ── top bar ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-400">
            {upCount}/{totalCount} services up
          </span>
          {lastRefresh && (
            <span className="text-xs text-slate-600">
              updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          {loadErr && <span className="text-xs text-rose-400">{loadErr}</span>}
        </div>
        <button
          onClick={handleFullRestart}
          disabled={fullRestarting}
          className="rounded bg-amber-700 px-4 py-2 text-sm font-semibold hover:bg-amber-600 disabled:opacity-50 transition-colors"
        >
          {fullRestarting ? '⟳ Launching FULL_START…' : '⚡ Full Restart (FULL_START.sh)'}
        </button>
      </div>

      {fullRestartMsg && (
        <div className={`rounded border px-3 py-2 text-sm font-mono ${
          fullRestartMsg.startsWith('Error')
            ? 'border-rose-700 bg-rose-950 text-rose-300'
            : 'border-emerald-700 bg-emerald-950 text-emerald-300'
        }`}>
          {fullRestartMsg}
        </div>
      )}

      {/* ── groups ── */}
      {GROUP_ORDER.filter((g) => grouped[g]?.length).map((group) => (
        <div key={group}>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
            {GROUP_LABELS[group] ?? group}
          </h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {grouped[group].map((svc) => (
              <ServiceCard key={svc.name} svc={svc} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
