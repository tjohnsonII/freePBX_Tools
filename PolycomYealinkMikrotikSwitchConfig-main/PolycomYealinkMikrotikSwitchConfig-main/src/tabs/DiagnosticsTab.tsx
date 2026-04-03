import { useEffect, useMemo, useRef, useState } from 'react';
import './DiagnosticsTab.css';

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
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) return '\u2014';
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function pillClass(kind: 'ok' | 'warn' | 'bad' | 'neutral'): string {
  return `diag-pill diag-pill-${kind}`;
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
    <div className="diag-root">
      <h2>Remote FreePBX Diagnostics</h2>
      <div className="diag-note">
        <b>Note:</b> This calls the local backend at <code>/api/diagnostics/summary</code> (Vite proxy &rarr; port 8002).
        Credentials are sent per-request and are not stored.
      </div>

      <div className="diag-form-grid">
        <div>
          <label className="diag-label" htmlFor="diag-server">Server</label>
          <input id="diag-server" className="diag-input" value={server} onChange={(e) => setServer(e.target.value)} title="FreePBX server address" />
        </div>
        <div>
          <label className="diag-label" htmlFor="diag-username">SSH Username</label>
          <input id="diag-username" className="diag-input" value={username} onChange={(e) => setUsername(e.target.value)} title="SSH username" />
        </div>
        <div>
          <label className="diag-label" htmlFor="diag-password">SSH Password</label>
          <input id="diag-password" className="diag-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} title="SSH password" />
        </div>
        <div>
          <label className="diag-label" htmlFor="diag-root-password">Root Password (optional)</label>
          <input id="diag-root-password" className="diag-input" type="password" value={rootPassword} onChange={(e) => setRootPassword(e.target.value)} title="Root password (uses SSH password if blank)" />
          <div className="diag-hint">If blank, uses SSH password.</div>
        </div>
        <div>
          <label className="diag-label" htmlFor="diag-timeout">Timeout (seconds)</label>
          <input
            id="diag-timeout"
            className="diag-input"
            type="number"
            min={3}
            value={timeoutSec}
            onChange={(e) => setTimeoutSec(Number(e.target.value))}
            title="Request timeout in seconds"
          />
        </div>

        <div className="diag-actions">
          <button type="button" className="diag-btn" onClick={() => void fetchDiagnostics()} disabled={loading}>
            {loading ? 'Loading\u2026' : 'Fetch Diagnostics'}
          </button>
          <label className="diag-check-label">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto-refresh
          </label>
          <label className="diag-check-label">
            Every
            <input
              className="diag-refresh-input"
              type="number"
              min={2}
              value={refreshEverySec}
              onChange={(e) => setRefreshEverySec(Number(e.target.value))}
              title="Refresh interval in seconds"
            />
            sec
          </label>
          {lastFetchedAt && (
            <span className="diag-muted">
              Last fetched: {lastFetchedAt.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {lastError && (
        <div className="diag-error">
          <b>Error:</b> {lastError}
        </div>
      )}

      {payload && (
        <div className="diag-payload">
          {(payload.error || payload.stderr || payload._stderr || payload.ok === false) && (
            <div className="diag-payload-error">
              <b>Diagnostics error:</b> {payload.error || 'Unknown error'}
              {payload._hint && (
                <div className="diag-hint-row">
                  <b>Hint:</b> {payload._hint}
                </div>
              )}
              {(payload.stderr || payload._stderr) && (
                <div className="diag-stderr">
                  {String(payload.stderr || payload._stderr)}
                </div>
              )}
            </div>
          )}

          <div className="diag-stats-grid">
            <div className="diag-card">
              <div className="diag-card-label">Host</div>
              <div className="diag-card-value-lg">{payload.meta?.hostname || '\u2014'}</div>
              <div className="diag-card-label-mt">Generated</div>
              <div className="diag-mono">{payload.generated_at_utc || '\u2014'}</div>
            </div>
            <div className="diag-card">
              <div className="diag-card-label">Active Calls</div>
              <div className="diag-card-value-xl">{payload.calls?.active ?? '\u2014'}</div>
            </div>
            <div className="diag-card">
              <div className="diag-card-label">Endpoints Registered</div>
              <div className="diag-card-value-md">
                {payload.endpoints?.registered ?? '\u2014'} / {payload.endpoints?.total ?? '\u2014'}
              </div>
              <div className="diag-card-label">
                {payload.endpoints?.percent_registered !== undefined ? `${payload.endpoints.percent_registered}%` : '\u2014'}
              </div>
            </div>
            <div className="diag-card">
              <div className="diag-card-label">Time Conditions</div>
              <div className="diag-card-value-sm">
                Total: {payload.time_conditions?.total ?? '\u2014'}
              </div>
              <div className="diag-card-label">
                Forced: {payload.time_conditions?.forced ?? '\u2014'} | Auto: {payload.time_conditions?.auto ?? '\u2014'}
              </div>
            </div>
            <div className="diag-card">
              <div className="diag-card-label">Snapshot Age</div>
              <div className="diag-card-value-lg-bold">{formatAge(payload.snapshot?.age_seconds)}</div>
              <div className="diag-card-label">{payload.snapshot?.path || '\u2014'}</div>
            </div>
            <div className="diag-card">
              <div className="diag-card-label">Versions</div>
              <div className="diag-mono-sm">FreePBX: {payload.meta?.freepbx_version || '\u2014'}</div>
              <div className="diag-mono-sm">Asterisk: {payload.meta?.asterisk_version || '\u2014'}</div>
            </div>
          </div>

          {payload.services && payload.services.length > 0 && (
            <div className="diag-section">
              <h3>Services</h3>
              <table className="diag-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>State</th>
                    <th>Enabled</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.services.map((svc, idx) => {
                    const s = getServiceRow(svc);
                    return (
                      <tr key={idx}>
                        <td>{s?.name ?? '\u2014'}</td>
                        <td>
                          <span className={pillClass(svcStateKind(s?.state))}>{s?.state || 'unknown'}</span>
                        </td>
                        <td>
                          <span className={pillClass(svcEnabledKind(s?.enabled))}>{s?.enabled || 'unknown'}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {payload.endpoints?.registered_ids && payload.endpoints.registered_ids.length > 0 && (
            <div className="diag-section">
              <h3>Registered Endpoints (sample)</h3>
              <div className="diag-mono-box">
                {payload.endpoints.registered_ids.slice(0, 50).join(', ')}
                {payload.endpoints.registered_ids.length > 50 ? ` \u2026 (+${payload.endpoints.registered_ids.length - 50} more)` : ''}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}