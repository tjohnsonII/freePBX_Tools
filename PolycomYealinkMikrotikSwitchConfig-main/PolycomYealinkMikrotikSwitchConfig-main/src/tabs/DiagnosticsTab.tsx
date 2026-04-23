import { useEffect, useMemo, useRef, useState } from 'react';
import './DiagnosticsTab.css';
import CallFlowGraph from './CallFlowGraph';
import TerminalPanel from './TerminalPanel';
import type { TerminalHandle } from './TerminalPanel';
import type { FreePBXDump } from './callflowTransform';

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

// ── Tool config types ────────────────────────────────────────────────────

type ParamDef = {
  label: string;
  placeholder: string;
  defaultValue: string;
};

type SubOption = {
  value: string;
  label: string;
  params: ParamDef[];
};

type ToolConfig = {
  value: string;
  label: string;
  /** For options that need a top-level param but no sub-menu (e.g. option 3). */
  topLevelParams?: ParamDef[];
  /** For options with interactive sub-menus. */
  subOptions?: SubOption[];
  /** Default sub-option value (falls back to first item). */
  defaultSub?: string;
};

const TOOL_CONFIG: ToolConfig[] = [
  { value: '1',  label: '1 — Refresh DB snapshot' },
  { value: '2',  label: '2 — Show inventory + list DIDs' },
  {
    value: '3',
    label: '3 — Generate call-flow for specific DID(s)',
    topLevelParams: [
      { label: 'DID indexes', placeholder: '1,3,5-8 or *', defaultValue: '*' },
    ],
  },
  { value: '4',  label: '4 — Generate call-flows for ALL DIDs' },
  { value: '5',  label: '5 — Generate call-flows ALL DIDs (skip OPEN label)' },
  { value: '6',  label: '6 — Time-Condition status' },
  { value: '7',  label: '7 — Module analysis' },
  { value: '8',  label: '8 — Paging / overhead / fax analysis' },
  { value: '9',  label: '9 — Comprehensive component analysis' },
  {
    value: '10',
    label: '10 — ASCII art call-flows',
    defaultSub: '5',
    subOptions: [
      { value: '5', label: 'Generate flows for ALL DIDs', params: [] },
      { value: '1', label: 'Generate flow for specific DID(s)', params: [
        { label: 'DID indexes', placeholder: '1,3 or all', defaultValue: 'all' },
      ]},
      { value: '2', label: 'Data collection summary', params: [] },
      { value: '3', label: 'Detailed config data', params: [] },
      { value: '4', label: 'Export all data to JSON', params: [] },
    ],
  },
  { value: '12', label: '12 — Full Asterisk diagnostic' },
  { value: '13', label: '13 — Automated log analysis' },
  {
    value: '14',
    label: '14 — Error map & quick reference',
    defaultSub: '2',
    subOptions: [
      { value: '2', label: 'Asterisk error codes', params: [] },
      { value: '3', label: 'FreePBX error reference', params: [] },
      { value: '4', label: 'Common issues & solutions', params: [] },
      { value: '1', label: 'SIP code lookup', params: [
        { label: 'SIP code (optional)', placeholder: '408', defaultValue: '' },
      ]},
    ],
  },
  {
    value: '15',
    label: '15 — Network diagnostics & packet capture',
    defaultSub: '1',
    subOptions: [
      { value: '1',  label: 'Port & firewall check', params: [] },
      { value: '2',  label: 'SIP connectivity test', params: [] },
      { value: '3',  label: 'Asterisk network stats', params: [] },
      { value: '4',  label: 'RTP port range test', params: [] },
      { value: '5',  label: 'Ping test', params: [
        { label: 'Host', placeholder: '8.8.8.8', defaultValue: '8.8.8.8' },
      ]},
      { value: '6',  label: 'Traceroute', params: [
        { label: 'Host', placeholder: '8.8.8.8', defaultValue: '8.8.8.8' },
      ]},
      { value: '7',  label: 'DNS lookup', params: [
        { label: 'Domain', placeholder: 'google.com', defaultValue: 'google.com' },
      ]},
      { value: '8',  label: 'Packet capture', params: [
        { label: 'Duration (seconds)', placeholder: '60', defaultValue: '60' },
        { label: 'Port filter (optional)', placeholder: '5060', defaultValue: '' },
        { label: 'Host filter (optional)', placeholder: '1.2.3.4', defaultValue: '' },
      ]},
      { value: '9',  label: 'Current connections', params: [] },
      { value: '10', label: 'SIP packet capture', params: [
        { label: 'Duration (seconds)', placeholder: '30', defaultValue: '30' },
      ]},
      { value: '11', label: 'Bandwidth monitor', params: [
        { label: 'Duration (seconds)', placeholder: '30', defaultValue: '30' },
      ]},
      { value: '12', label: 'QoS/DSCP settings', params: [] },
      { value: '13', label: 'NAT/firewall detection', params: [] },
      { value: '14', label: 'Network interface info', params: [] },
    ],
  },
  {
    value: '16',
    label: '16 — Enhanced log analysis (dmesg/journal)',
    defaultSub: '1',
    subOptions: [
      { value: '1', label: 'Recent errors', params: [
        { label: 'Last N hours', placeholder: '1', defaultValue: '1' },
      ]},
      { value: '2', label: 'Warning summary', params: [
        { label: 'Last N hours', placeholder: '1', defaultValue: '1' },
      ]},
      { value: '3', label: 'Call pattern analysis', params: [] },
      { value: '4', label: 'Security scan', params: [
        { label: 'Last N hours', placeholder: '1', defaultValue: '1' },
      ]},
      { value: '5', label: 'Regex pattern search', params: [
        { label: 'Regex pattern', placeholder: 'error|fail', defaultValue: 'error' },
        { label: 'Log file (optional)', placeholder: '/var/log/asterisk/full', defaultValue: '' },
      ]},
      { value: '6', label: 'Registration failures', params: [] },
      { value: '7', label: 'SIP debug summary', params: [] },
      { value: '8', label: 'SIP code lookup', params: [
        { label: 'SIP code', placeholder: '408', defaultValue: '' },
      ]},
    ],
  },
  {
    value: '17',
    label: '17 — CDR/CEL call log analysis',
    defaultSub: '1',
    subOptions: [
      { value: '1',  label: 'Call summary', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '2',  label: 'Failed calls', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '3',  label: 'Long calls', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '4',  label: 'Calls by extension', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '5',  label: 'Calls by DID', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '6',  label: 'Peak hours analysis', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '7',  label: 'Call duration stats', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '8',  label: 'International calls', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '9',  label: 'Queue call analysis', params: [{ label: 'Last N hours', placeholder: '24', defaultValue: '24' }] },
      { value: '10', label: 'Export to CSV', params: [
        { label: 'Last N hours', placeholder: '24', defaultValue: '24' },
        { label: 'Filename (optional)', placeholder: 'auto-generated', defaultValue: '' },
      ]},
    ],
  },
  {
    value: '18',
    label: '18 — Phone/endpoint analysis',
    defaultSub: '1',
    subOptions: [
      { value: '1', label: 'All phone status', params: [] },
      { value: '2', label: 'Registered phones', params: [] },
      { value: '3', label: 'Unregistered phones', params: [] },
      { value: '4', label: 'Firmware info', params: [] },
      { value: '5', label: 'Extension config', params: [] },
      { value: '6', label: 'Codec analysis', params: [] },
      { value: '7', label: 'NAT/firewall for phones', params: [] },
      { value: '8', label: 'Phone health check', params: [] },
    ],
  },
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
  const [toolCmd, setToolCmd] = useState('6');
  const [subChoice, setSubChoice] = useState('');
  const [extraParams, setExtraParams] = useState<string[]>([]);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [toolStatus, setToolStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [toolBusy, setToolBusy] = useState(false);
  const [dumpData, setDumpData] = useState<Record<string, unknown> | null>(null);
  const [dumpExpanded, setDumpExpanded] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const logLinesRef = useRef<string[]>([]);
  const isGrabDumpRef = useRef(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  // ── Terminal mode (xterm.js) — used when Run Tool streams raw terminal output ──
  const [terminalMode, setTerminalMode] = useState(false);
  const isTerminalModeRef = useRef(false);
  const xtermRef = useRef<TerminalHandle | null>(null);

  // ── Computed tool config ───────────────────────────────────────────────
  const currentConfig = useMemo(
    () => TOOL_CONFIG.find((c) => c.value === toolCmd),
    [toolCmd],
  );
  const currentSubConfig = useMemo(
    () => currentConfig?.subOptions?.find((s) => s.value === subChoice),
    [currentConfig, subChoice],
  );
  // Params to render: sub-option params (when sub-menu active), top-level params, or none
  const activeParams: ParamDef[] =
    currentSubConfig?.params ?? currentConfig?.topLevelParams ?? [];

  // Reset sub-choice and extra-params whenever the top-level tool changes
  useEffect(() => {
    const cfg = TOOL_CONFIG.find((c) => c.value === toolCmd);
    if (cfg?.subOptions?.length) {
      const def = cfg.defaultSub ?? cfg.subOptions[0].value;
      setSubChoice(def);
      const sub = cfg.subOptions.find((s) => s.value === def);
      setExtraParams(sub?.params.map((p) => p.defaultValue) ?? []);
    } else if (cfg?.topLevelParams?.length) {
      setSubChoice('');
      setExtraParams(cfg.topLevelParams.map((p) => p.defaultValue));
    } else {
      setSubChoice('');
      setExtraParams([]);
    }
  }, [toolCmd]);

  function handleSubChoiceChange(newSub: string): void {
    setSubChoice(newSub);
    const sub = currentConfig?.subOptions?.find((s) => s.value === newSub);
    setExtraParams(sub?.params.map((p) => p.defaultValue) ?? []);
  }

  function updateExtraParam(idx: number, value: string): void {
    setExtraParams((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  }

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
    // In terminal mode the xterm buffer IS the log; don't reset logLines here.
    if (!isTerminalModeRef.current) {
      setLogLines([]);
      logLinesRef.current = [];
    }
    setToolStatus('running');

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/api/jobs/${jobId}/ws`);
    wsRef.current = ws;

    ws.onmessage = (ev: MessageEvent) => {
      const text = String(ev.data);
      if (isTerminalModeRef.current) {
        // Route raw output (including ANSI codes) directly into xterm.js.
        // Append \n so each WS message starts on its own line; xterm's
        // convertEol:true converts \n → \r\n for correct rendering.
        xtermRef.current?.write(text + '\n');
      } else {
        setLogLines((prev) => {
          const next = [...prev, text];
          const trimmed = next.length > 3000 ? next.slice(-3000) : next;
          logLinesRef.current = trimmed;
          return trimmed;
        });
      }
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
    isTerminalModeRef.current = false;
    setTerminalMode(false);
    setLogLines([]);
    logLinesRef.current = [];
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
    // Switch to xterm.js terminal mode for raw freepbx-callflows output.
    isTerminalModeRef.current = true;
    setTerminalMode(true);
    // Clear previous run; safe even if xtermRef is null (first call before mount).
    xtermRef.current?.clear();
    try {
      const res = await fetch('/api/remote/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server,
          username,
          password,
          root_password: rootPassword || password,
          menu_choice: toolCmd,
          sub_choice: subChoice,
          extra_params: extraParams,
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
    isTerminalModeRef.current = false;
    setTerminalMode(false);
    setLogLines([]);
    logLinesRef.current = [];
    try {
      const res = await fetch('/api/remote/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server,
          username,
          password,
          root_password: rootPassword || password,
          menu_choice: '1',
          grab_dump: true,
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
            {TOOL_CONFIG.map((o) => (
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

        {/* Sub-option panel — shown for tools with sub-menus or top-level params */}
        {(currentConfig?.subOptions || currentConfig?.topLevelParams) && (
          <div className="diag-suboption-panel">
            {currentConfig.subOptions && (
              <div className="diag-suboption-row">
                <label className="diag-suboption-label" htmlFor="diag-subchoice">
                  Sub-option
                </label>
                <select
                  id="diag-subchoice"
                  className="diag-tool-select"
                  value={subChoice}
                  onChange={(e) => handleSubChoiceChange(e.target.value)}
                  disabled={toolBusy}
                >
                  {currentConfig.subOptions.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {activeParams.length > 0 && (
              <div className="diag-suboption-params">
                {activeParams.map((p, i) => (
                  <div key={i} className="diag-suboption-param">
                    <label className="diag-suboption-label">{p.label}</label>
                    <input
                      className="diag-suboption-input"
                      value={extraParams[i] ?? p.defaultValue}
                      onChange={(e) => updateExtraParam(i, e.target.value)}
                      placeholder={p.placeholder}
                      disabled={toolBusy}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Terminal panel (xterm.js) — shown when Run Tool is active */}
        {terminalMode && (
          <TerminalPanel ref={xtermRef} />
        )}

        {/* Plain log panel — shown for Install Tools and Grab Dump */}
        {!terminalMode && logLines.length > 0 && (
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

        {/* Call Flow Graph — rendered from dump JSON */}
        {dumpData && (
          <CallFlowGraph dump={dumpData as FreePBXDump} />
        )}
      </div>
    </div>
  );
}