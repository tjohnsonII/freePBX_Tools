import { useEffect, useMemo, useRef, useState } from 'react';

type DiagnosticsPayload = {
  ok?: boolean;
  generated_at_utc?: string;
  meta?: {
    hostname?: string;
    freepbx_version?: string;
    asterisk_version?: string;
  };
  calls?: { active?: number };
  endpoints?: {
    total?: number;
    registered?: number;
    unregistered?: number;
    percent_registered?: number;
    registered_ids?: string[];
  };
  time_conditions?: { total?: number; forced?: number; auto?: number };
  services?: Array<{ name?: string; state?: string; enabled?: string } | Record<string, unknown>>;
  snapshot?: { path?: string; exists?: boolean; age_seconds?: number; mtime_utc?: string };
  error?: string;
  stderr?: string;
  _stderr?: string;
  _hint?: string;
};

type ServiceRow = {
  name?: string;
  state?: string;
  enabled?: string;
};

type ServiceEntry =
  | { name?: string; state?: string; enabled?: string }
  | Record<string, unknown>;

function isAbortError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  if (!('name' in err)) return false;
  return (err as { name?: unknown }).name === 'AbortError';
}

function toErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function getServiceRow(svc: ServiceEntry): ServiceRow {
  if (!svc || typeof svc !== 'object') return {};
  const rec = svc as Record<string, unknown>;
  const name = typeof rec.name === 'string' ? rec.name : undefined;
  const state = typeof rec.state === 'string' ? rec.state : undefined;
  const enabled = typeof rec.enabled === 'string' ? rec.enabled : undefined;
  return { name, state, enabled };
}

function formatAge(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) return '—';
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function pillStyle(kind: 'ok' | 'warn' | 'bad' | 'neutral'): React.CSSProperties {
  const base: React.CSSProperties = {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 700,
    lineHeight: '16px',
  };
  if (kind === 'ok') return { ...base, background: '#e8f7ee', color: '#16794a', border: '1px solid #bfe9cf' };
  if (kind === 'warn') return { ...base, background: '#fff6e5', color: '#8a5a00', border: '1px solid #ffd59a' };
  if (kind === 'bad') return { ...base, background: '#ffecec', color: '#b42318', border: '1px solid #ffb3b3' };
  return { ...base, background: '#f2f4f7', color: '#475467', border: '1px solid #e4e7ec' };
}

function svcStateKind(state?: string): 'ok' | 'warn' | 'bad' | 'neutral' {
  const s = (state || '').toLowerCase();
  if (s === 'active') return 'ok';
  if (s === 'failed') return 'bad';
  if (s === 'inactive') return 'neutral';
  if (s) return 'warn';
  return 'neutral';
}

function svcEnabledKind(enabled?: string): 'ok' | 'warn' | 'bad' | 'neutral' {
  const s = (enabled || '').toLowerCase();
  if (s === 'enabled') return 'ok';
  if (s === 'masked') return 'bad';
  if (s === 'disabled') return 'neutral';
  if (s === 'static' || s === 'indirect') return 'warn';
  if (s) return 'warn';
  return 'neutral';
}

export default function DiagnosticsTab() {
  const [server, setServer] = useState('69.39.69.102');
  const [username, setUsername] = useState('123net');
  const [password, setPassword] = useState('');
  const [rootPassword, setRootPassword] = useState('');
  const [timeoutSec, setTimeoutSec] = useState(15);

  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshEverySec, setRefreshEverySec] = useState(10);

  const [loading, setLoading] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [payload, setPayload] = useState<DiagnosticsPayload | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const requestBody = useMemo(() => {
    return {
      server,
      username,
      password,
      root_password: rootPassword || password,
      timeout_seconds: timeoutSec,
    };
  }, [server, username, password, rootPassword, timeoutSec]);

  async function fetchDiagnostics(): Promise<void> {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setLastError(null);

    try {
      const res = await fetch('/api/diagnostics/summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
        signal: ac.signal,
      });

      const text = await res.text();
      let data: DiagnosticsPayload;
      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(`Non-JSON response (${res.status}): ${text.slice(0, 200)}`);
      }

      if (!res.ok) {
        const msg = data?.error || `Request failed (${res.status})`;
        const hint = data?._hint ? `\n\n${data._hint}` : '';
        throw new Error(`${msg}${hint}`);
      }

      setPayload(data);
      setLastFetchedAt(new Date());
    } catch (e: unknown) {
      if (isAbortError(e)) return;
      setLastError(toErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!autoRefresh) return;
    const ms = Math.max(2, refreshEverySec) * 1000;
    const id = window.setInterval(() => {
      void fetchDiagnostics();
    }, ms);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshEverySec, requestBody]);

  return (
    <div style={{ margin: '24px 0', maxWidth: 980 }}>
      <h2 style={{ marginTop: 0 }}>Remote FreePBX Diagnostics</h2>
      <div style={{ background: '#fff6e5', border: '1px solid #ffd59a', borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <b>Note:</b> This calls the local backend at <code>/api/diagnostics/summary</code> (Vite proxy → port 8002).
        Credentials are sent per-request and are not stored.
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={{ display: 'block', fontWeight: 600 }}>Server</label>
          <input value={server} onChange={(e) => setServer(e.target.value)} style={{ width: '100%' }} />
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600 }}>SSH Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} style={{ width: '100%' }} />
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600 }}>SSH Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ width: '100%' }} />
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600 }}>Root Password (optional)</label>
          <input type="password" value={rootPassword} onChange={(e) => setRootPassword(e.target.value)} style={{ width: '100%' }} />
          <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
            If blank, uses SSH password.
          </div>
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600 }}>Timeout (seconds)</label>
          <input
            type="number"
            min={3}
            value={timeoutSec}
            onChange={(e) => setTimeoutSec(Number(e.target.value))}
            style={{ width: '100%' }}
          />
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <button onClick={() => void fetchDiagnostics()} disabled={loading} style={{ padding: '8px 14px' }}>
            {loading ? 'Loading…' : 'Fetch Diagnostics'}
          </button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto-refresh
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            Every
            <input
              type="number"
              min={2}
              value={refreshEverySec}
              onChange={(e) => setRefreshEverySec(Number(e.target.value))}
              style={{ width: 80 }}
            />
            sec
          </label>
          {lastFetchedAt && (
            <span style={{ fontSize: 12, color: '#666' }}>
              Last fetched: {lastFetchedAt.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {lastError && (
        <div style={{ marginTop: 16, background: '#ffecec', border: '1px solid #ffb3b3', borderRadius: 8, padding: 12 }}>
          <b>Error:</b> {lastError}
        </div>
      )}

      {payload && (
        <div style={{ marginTop: 18 }}>
          {(payload.error || payload.stderr || payload._stderr || payload.ok === false) && (
            <div style={{ marginBottom: 14, background: '#ffecec', border: '1px solid #ffb3b3', borderRadius: 8, padding: 12 }}>
              <b>Diagnostics error:</b> {payload.error || 'Unknown error'}
              {payload._hint && (
                <div style={{ marginTop: 8 }}>
                  <b>Hint:</b> {payload._hint}
                </div>
              )}
              {(payload.stderr || payload._stderr) && (
                <div style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                  {String(payload.stderr || payload._stderr)}
                </div>
              )}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 12, color: '#666' }}>Host</div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{payload.meta?.hostname || '—'}</div>
              <div style={{ fontSize: 12, color: '#666', marginTop: 6 }}>Generated</div>
              <div style={{ fontFamily: 'monospace' }}>{payload.generated_at_utc || '—'}</div>
            </div>
            <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 12, color: '#666' }}>Active Calls</div>
              <div style={{ fontSize: 28, fontWeight: 800 }}>{payload.calls?.active ?? '—'}</div>
            </div>
            <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 12, color: '#666' }}>Endpoints Registered</div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>
                {payload.endpoints?.registered ?? '—'} / {payload.endpoints?.total ?? '—'}
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>
                {payload.endpoints?.percent_registered !== undefined ? `${payload.endpoints.percent_registered}%` : '—'}
              </div>
            </div>
            <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 12, color: '#666' }}>Time Conditions</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>
                Total: {payload.time_conditions?.total ?? '—'}
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>
                Forced: {payload.time_conditions?.forced ?? '—'} | Auto: {payload.time_conditions?.auto ?? '—'}
              </div>
            </div>
            <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 12, color: '#666' }}>Snapshot Age</div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>{formatAge(payload.snapshot?.age_seconds)}</div>
              <div style={{ fontSize: 12, color: '#666' }}>{payload.snapshot?.path || '—'}</div>
            </div>
            <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 12, color: '#666' }}>Versions</div>
              <div style={{ fontSize: 12, fontFamily: 'monospace' }}>FreePBX: {payload.meta?.freepbx_version || '—'}</div>
              <div style={{ fontSize: 12, fontFamily: 'monospace' }}>Asterisk: {payload.meta?.asterisk_version || '—'}</div>
            </div>
          </div>

          {payload.services && payload.services.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ marginBottom: 8 }}>Services</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f4f4f4' }}>
                    <th style={{ textAlign: 'left', padding: '6px 10px', borderBottom: '2px solid #ccc' }}>Name</th>
                    <th style={{ textAlign: 'left', padding: '6px 10px', borderBottom: '2px solid #ccc' }}>State</th>
                    <th style={{ textAlign: 'left', padding: '6px 10px', borderBottom: '2px solid #ccc' }}>Enabled</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.services.map((svc, idx) => {
                    const s = getServiceRow(svc);
                    return (
                      <tr key={idx}>
                        <td style={{ padding: '6px 10px', borderBottom: '1px solid #eee' }}>{s?.name ?? '—'}</td>
                        <td style={{ padding: '6px 10px', borderBottom: '1px solid #eee' }}>
                          <span style={pillStyle(svcStateKind(s?.state))}>{s?.state || 'unknown'}</span>
                        </td>
                        <td style={{ padding: '6px 10px', borderBottom: '1px solid #eee' }}>
                          <span style={pillStyle(svcEnabledKind(s?.enabled))}>{s?.enabled || 'unknown'}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {payload.endpoints?.registered_ids && payload.endpoints.registered_ids.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ marginBottom: 8 }}>Registered Endpoints (sample)</h3>
              <div style={{ fontFamily: 'monospace', fontSize: 12, background: '#fafafa', border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
                {payload.endpoints.registered_ids.slice(0, 50).join(', ')}
                {payload.endpoints.registered_ids.length > 50 ? ` … (+${payload.endpoints.registered_ids.length - 50} more)` : ''}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
