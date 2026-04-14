import { useEffect, useMemo, useRef, useState } from 'react';
import './DiagnosticsTab.css';

// ── Diagnostics payload types ────────────────────────────────────────────

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

// ── Constants ─────────────────────────────────────────────────────────────

const DUMP_JSON_MARKER = '__FREEPBX_DUMP_JSON__:';

const TOOL_OPTIONS: { value: string; label: string }[] = [
  { value: 'freepbx-tc-status', label: 'TC Status — time condition states' },
  { value: 'freepbx-module-status', label: 'Module Status' },
  { value: 'freepbx-module-analyzer', label: 'Module Analyzer' },
  { value: 'freepbx-comprehensive-analyzer', label: 'Comprehensive Analyzer' },
  { value: 'freepbx-ascii-callflow', label: 'ASCII Call Flow' },
  { value: 'freepbx-paging-fax-analyzer', label: 'Paging / Fax Analyzer' },
  { value: 'freepbx-version-check', label: 'Version Check' },
  { value: 'freepbx-dump', label: 'FreePBX Dump (writes JSON snapshot)' },
  { value: 'asterisk-full-diagnostic.sh', label: 'Asterisk Full Diagnostic' },
];

// ── Helpers ───────────────────────────────────────────────────────────────

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

function logLineClass(line: string): string {
  const s = line.toLowerCase();
  if (s.includes('[ok]') || s.includes('successful') || s.includes('exit code: 0'))
    return 'diag-log-ok';
  if (s.includes('[warning]') || s.includes('warning') || s.includes('warn:'))
    return 'diag-log-warn';
  if (
    s.includes('[error]') ||
    s.includes('[failed]') ||
    s.includes('fatal error') ||
    s.startsWith('error:')
  )
    return 'diag-log-err';
  return '';
}

// ── Component ─────────────────────────────────────────────────────────────

export default function DiagnosticsTab() {
  // ── Diagnostics form state ─────────────────────────────────────────────
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

  // ── Tools panel state ──────────────────────────────────────────────────
  const [toolCmd, setToolCmd] = useState('freepbx-tc-status');
  const [logLines, setLogLines] = useState<string[]>([]);
  const [toolStatus, setToolStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [toolBusy, setToolBusy] = useState(false);
  const [dumpData, setDumpData] = useState<Record<string, unknown> | null>(null);
  const [dumpExpanded, setDumpExpanded] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const logLinesRef = useRef<string[]>([]);
  const isGrabDumpRef = useRef(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  // ── Diagnostics request body ───────────────────────────────────────────
  const requestBody = useMemo(() => {
    return {
      server,
      username,
      password,
      root_password: rootPassword || password,
      timeout_seconds: timeoutSec,
    };
  }, [server, username, password, rootPassword, timeoutSec]);

  // ── Auto-scroll log panel ──────────────────────────────────────────────
  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logLines]);

  // ── Diagnostics fetch ──────────────────────────────────────────────────
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

  // ── Tools helpers ──────────────────────────────────────────────────────

  function disconnectWs(): void {
    try {
      wsRef.current?.close();
    } catch {
      // ignore
    }
    wsRef.current = null;
  }

  function parseDumpFromLines(lines: string[]): void {
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (line.startsWith(DUMP_JSON_MARKER)) {
        const jsonStr = line.slice(DUMP_JSON_MARKER.length);
        try {
          const data = JSON.parse(jsonStr) as Record<string, unknown>;
          setDumpData(data);
          setDumpExpanded(true);
          return;
        } catch {
          // not valid JSON — keep scanning
        }
      }
    }
  }

  function attachToJob(jobId: string): void {
    disconnectWs();
    setLogLines([]);
    logLinesRef.current = [];
    setToolStatus('running');

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/api/jobs/${jobId}/ws`);
    wsRef.current = ws;

    ws.onmessage = (ev: MessageEvent) => {
      const text = String(ev.data);
      setLogLines((prev) => {
        const next = [...prev, text];
        const trimmed = next.length > 3000 ? next.slice(-3000) : next;
        logLinesRef.current = trimmed;
        return trimmed;
      });
    };

    ws.onclose = () => {
      wsRef.current = null;
      setToolStatus('done');
      setToolBusy(false);
      if (isGrabDumpRef.current) {
        parseDumpFromLines(logLinesRef.current);
        isGrabDumpRef.current = false;
      }
    };

    ws.onerror = () => {
      setToolStatus('error');
      setToolBusy(false);
    };

    // heartbeat
    const hb = setInterval(() => {
      try {
        ws.send('ping');
      } catch {
        // ignore
      }
    }, 15000);
    ws.addEventListener('close', () => clearInterval(hb));
  }

  async function installTools(): Promise<void> {
    setToolBusy(true);
    setDumpData(null);
    isGrabDumpRef.current = false;
    try {
      const res = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'deploy',
          servers: server,
          workers: 1,
          username,
          password,
          root_password: rootPassword || password,
          bundle_name: '',
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`Deploy failed (${res.status}): ${t.slice(0, 200)}`);
      }
      const job = (await res.json()) as { id: string };
      attachToJob(job.id);
    } catch (e) {
      setLastError(toErrorMessage(e));
      setToolBusy(false);
    }
  }

  async function runTool(): Promise<void> {
    setToolBusy(true);
    setDumpData(null);
    isGrabDumpRef.current = false;
    try {
      const res = await fetch('/api/remote/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server,
          username,
          password,
          root_password: rootPassword || password,
          command: toolCmd,
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`Run tool failed (${res.status}): ${t.slice(0, 200)}`);
      }
      const job = (await res.json()) as { id: string };
      attachToJob(job.id);
    } catch (e) {
      setLastError(toErrorMessage(e));
      setToolBusy(false);
    }
  }

  async function grabDump(): Promise<void> {
    setToolBusy(true);
    setDumpData(null);
    isGrabDumpRef.current = true;
    try {
      const res = await fetch('/api/remote/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server,
          username,
          password,
          root_password: rootPassword || password,
          command: 'freepbx-dump',
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`Grab dump failed (${res.status}): ${t.slice(0, 200)}`);
      }
      const job = (await res.json()) as { id: string };
      attachToJob(job.id);
    } catch (e) {
      setLastError(toErrorMessage(e));
      setToolBusy(false);
      isGrabDumpRef.current = false;
    }
  }

  const toolStatusLabel: Record<typeof toolStatus, string> = {
    idle: 'Idle',
    running: 'Running\u2026',
    done: 'Done',
    error: 'Error',
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="diag-root">
      <h2>Remote FreePBX Diagnostics</h2>
      <div className="diag-note">
        <b>Note:</b> This calls the local backend at <code>/api/diagnostics/summary</code> (Vite proxy &rarr; port 8002).
        Credentials are sent per-request and are not stored.
      </div>

      {/* ── Credentials form ── */}
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

      {/* ── Diagnostics payload ── */}
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

      {/* ══════════════════════════════════════════════════════════════════
          Tools Panel — install, run, and grab data from installed tools
          ══════════════════════════════════════════════════════════════════ */}
      <div className="diag-tools-section">
        <h3 className="diag-tools-heading">FreePBX Tools</h3>
        <p className="diag-tools-hint">
          Tools must be installed on the remote server first (use <b>Install Tools</b>).
          Credentials above are reused for SSH.
        </p>

        <div className="diag-tools-bar">
          {/* Install */}
          <button
            type="button"
            className="diag-btn diag-btn-install"
            onClick={() => void installTools()}
            disabled={toolBusy}
            title="Deploy freepbx-tools to the server via SSH"
          >
            Install Tools
          </button>

          {/* Run Tool */}
          <select
            className="diag-tool-select"
            value={toolCmd}
            onChange={(e) => setToolCmd(e.target.value)}
            disabled={toolBusy}
            aria-label="Select tool to run"
            title="Select tool to run"
          >
            {TOOL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="diag-btn diag-btn-run"
            onClick={() => void runTool()}
            disabled={toolBusy}
            title="SSH in and run the selected tool"
          >
            Run Tool
          </button>

          {/* Grab Dump */}
          <button
            type="button"
            className="diag-btn diag-btn-dump"
            onClick={() => void grabDump()}
            disabled={toolBusy}
            title="Run freepbx-dump and parse the resulting JSON snapshot"
          >
            Grab Dump
          </button>

          {/* Status badge */}
          {toolStatus !== 'idle' && (
            <span className={`diag-tool-status diag-tool-status-${toolStatus}`}>
              {toolStatusLabel[toolStatus]}
            </span>
          )}
        </div>

        {/* Log panel */}
        {logLines.length > 0 && (
          <div ref={logRef} className="diag-log">
            {logLines.map((line, idx) => (
              <span key={idx} className={logLineClass(line)}>
                {line}
              </span>
            ))}
          </div>
        )}

        {/* Dump data panel */}
        {dumpData && (
          <div className="diag-dump-panel">
            <div
              className="diag-dump-header"
              onClick={() => setDumpExpanded((v) => !v)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setDumpExpanded((v) => !v)}
            >
              <strong>FreePBX Dump JSON</strong>
              <span className="diag-dump-toggle">{dumpExpanded ? '\u25b2 Collapse' : '\u25bc Expand'}</span>
            </div>
            {dumpExpanded && (
              <pre className="diag-dump-pre">
                {JSON.stringify(dumpData, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}