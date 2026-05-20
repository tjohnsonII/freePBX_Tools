'use client';

import { useRef, useState } from 'react';

/* ── shared helpers ──────────────────────────────────────────────────── */

const inputCls =
  'w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-slate-500';

const btnCls = (color: 'blue' | 'amber' | 'green' | 'slate' = 'blue') =>
  ({
    blue:  'bg-blue-700 hover:bg-blue-600 disabled:bg-slate-800 disabled:text-slate-600',
    amber: 'bg-amber-700 hover:bg-amber-600 disabled:bg-slate-800 disabled:text-slate-600',
    green: 'bg-green-800 hover:bg-green-700 disabled:bg-slate-800 disabled:text-slate-600',
    slate: 'bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600',
  }[color] + ' text-sm font-medium px-3 py-1.5 rounded transition-colors');

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400">{title}</h2>
      {children}
    </div>
  );
}

function OutputBox({ text, minH = '160px' }: { text: string; minH?: string }) {
  return (
    <pre
      className="mt-2 overflow-auto rounded bg-slate-950 p-3 font-mono text-xs text-slate-300 leading-relaxed"
      style={{ minHeight: minH, maxHeight: '400px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
    >
      {text || <span className="text-slate-600">No output yet.</span>}
    </pre>
  );
}

function ErrBox({ msg }: { msg: string }) {
  return msg ? <p className="mt-1 text-xs text-red-400">{msg}</p> : null;
}

/* ── sub-tab switcher ────────────────────────────────────────────────── */

type Tab = 'webserver' | 'phoneconfig' | 'vpbxdb' | 'traceroute';

const TABS: { key: Tab; label: string }[] = [
  { key: 'webserver',   label: '🌐 Webserver' },
  { key: 'phoneconfig', label: '📱 Phone Config' },
  { key: 'vpbxdb',      label: '🗄️ VPBX DB' },
  { key: 'traceroute',  label: '🚀 Traceroute Helper' },
];

/* ── Webserver panel ─────────────────────────────────────────────────── */

const WEBSERVER_URL_LIST = [
  'https://123hostedtools.com',
  'https://auth.123hostedtools.com',
  'https://tools.123hostedtools.com',
  'https://grafana.123hostedtools.com',
  'https://prtg.timsablab.ddns.net',
  'https://freepbx.timsablab.ddns.net',
  'https://mail.timsablab.ddns.net',
];

const SSH_COMMANDS: { key: string; label: string }[] = [
  { key: 'apache_status',   label: 'Apache Status' },
  { key: 'vhost_list',      label: 'VHost List (apachectl -S)' },
  { key: 'config_test',     label: 'Config Test (apachectl configtest)' },
  { key: 'reload_apache',   label: 'Reload Apache' },
  { key: 'check_all_vhosts', label: 'Check All VHosts' },
  { key: 'tail_error_log',  label: 'Tail Error Log (60 lines)' },
  { key: 'tail_access_log', label: 'Tail Access Log (60 lines)' },
];

type UrlResult = { url: string; status: number; ok: boolean; ms: number; error?: string };

function WebserverPanel() {
  const [wsHost, setWsHost]   = useState('192.168.100.10');
  const [wsUser, setWsUser]   = useState('tim2');
  const [wsPass, setWsPass]   = useState('');
  const [cmdKey, setCmdKey]   = useState('apache_status');
  const [vhost,  setVhost]    = useState('');
  const [backend, setBackend] = useState('http://127.0.0.1');

  const [urlResults, setUrlResults] = useState<UrlResult[]>([]);
  const [sshOut,  setSshOut]  = useState('');
  const [vhostOut, setVhostOut] = useState('');
  const [err,     setErr]     = useState('');
  const [busy,    setBusy]    = useState<string | null>(null);

  async function checkUrls() {
    setBusy('urls'); setErr(''); setUrlResults([]);
    try {
      const r = await fetch('/diag-api/webserver/check-urls', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: WEBSERVER_URL_LIST }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.error || 'Request failed'); return; }
      setUrlResults(d.results ?? []);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  }

  async function runSsh() {
    setBusy('ssh'); setErr(''); setSshOut('');
    try {
      const r = await fetch('/diag-api/webserver/ssh-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: wsHost, username: wsUser, password: wsPass, command: cmdKey }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.error || 'SSH failed'); return; }
      setSshOut(d.output ?? '');
    } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  }

  async function checkVhost() {
    if (!vhost.trim()) { setErr('vhost name required'); return; }
    setBusy('vhost'); setErr(''); setVhostOut('');
    try {
      const r = await fetch('/diag-api/webserver/check-one-vhost', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: wsHost, username: wsUser, password: wsPass, vhost, backend }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.error || 'Request failed'); return; }
      setVhostOut(d.output ?? '');
    } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  }

  return (
    <div className="space-y-4">
      {/* SSH credentials shared across sections */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Webserver Host</label>
          <input value={wsHost} onChange={e => setWsHost(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Username</label>
          <input value={wsUser} onChange={e => setWsUser(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Password</label>
          <input type="password" value={wsPass} onChange={e => setWsPass(e.target.value)} className={inputCls} autoComplete="off" />
        </div>
      </div>

      <ErrBox msg={err} />

      {/* URL health checks */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-slate-300">URL Health Checks</span>
          <button onClick={checkUrls} disabled={busy !== null} className={btnCls('blue')}>
            {busy === 'urls' ? '…' : 'Check All URLs'}
          </button>
        </div>
        {urlResults.length > 0 && (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800">
                <th className="text-left pb-1 font-normal">URL</th>
                <th className="text-right pb-1 font-normal">Status</th>
                <th className="text-right pb-1 font-normal">ms</th>
              </tr>
            </thead>
            <tbody>
              {urlResults.map(r => (
                <tr key={r.url} className="border-b border-slate-800/50">
                  <td className="py-1 text-slate-300 font-mono">{r.url}</td>
                  <td className={`py-1 text-right font-mono ${r.ok ? 'text-green-400' : 'text-red-400'}`}>
                    {r.error ? 'ERR' : r.status}
                  </td>
                  <td className="py-1 text-right text-slate-500">{r.ms ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* SSH command runner */}
      <div>
        <div className="flex items-end gap-3 mb-2">
          <div className="flex-1">
            <label className="block text-xs text-slate-400 mb-1">SSH Command</label>
            <select value={cmdKey} onChange={e => setCmdKey(e.target.value)} className={inputCls}>
              {SSH_COMMANDS.map(c => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </div>
          <button onClick={runSsh} disabled={busy !== null} className={btnCls('amber')}>
            {busy === 'ssh' ? '…' : '▶ Run'}
          </button>
        </div>
        <OutputBox text={sshOut} />
      </div>

      {/* Single vhost check */}
      <div>
        <div className="flex items-end gap-3 mb-2">
          <div className="flex-1">
            <label className="block text-xs text-slate-400 mb-1">VHost Name</label>
            <input value={vhost} onChange={e => setVhost(e.target.value)} placeholder="e.g. 123hostedtools.com" className={inputCls} />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-slate-400 mb-1">Backend URL</label>
            <input value={backend} onChange={e => setBackend(e.target.value)} className={inputCls} />
          </div>
          <button onClick={checkVhost} disabled={busy !== null} className={btnCls('green')}>
            {busy === 'vhost' ? '…' : 'Check VHost'}
          </button>
        </div>
        <OutputBox text={vhostOut} />
      </div>
    </div>
  );
}

/* ── Phone Config Analyzer ───────────────────────────────────────────── */

function PhoneConfigPanel() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState('');
  const [err,    setErr]    = useState('');
  const [busy,   setBusy]   = useState(false);

  async function analyze() {
    const file = fileRef.current?.files?.[0];
    if (!file) { setErr('Select a config file first'); return; }
    setBusy(true); setErr(''); setResult('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/diag-api/phone-config/analyze', { method: 'POST', body: fd });
      const d = await r.json();
      if (!r.ok) { setErr(d.error || 'Analysis failed'); return; }
      setResult(JSON.stringify(d, null, 2));
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">Upload a Polycom / Yealink XML config file to analyze it.</p>
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="block text-xs text-slate-400 mb-1">Config File</label>
          <input ref={fileRef} type="file" accept=".cfg,.xml,.txt" className={inputCls} />
        </div>
        <button onClick={analyze} disabled={busy} className={btnCls('blue')}>
          {busy ? 'Analyzing…' : '🔍 Analyze'}
        </button>
      </div>
      <ErrBox msg={err} />
      <OutputBox text={result} minH="300px" />
    </div>
  );
}

/* ── VPBX Database ───────────────────────────────────────────────────── */

const QUERY_TYPES = [
  { key: 'yealink_companies', label: 'Yealink Companies (top N)' },
  { key: 'model_search',      label: 'Model Search' },
  { key: 'vendor_stats',      label: 'Vendor Stats' },
  { key: 'security_issues',   label: 'Security Issues' },
];

function VpbxDbPanel() {
  const [queryType, setQueryType] = useState('yealink_companies');
  const [limit,     setLimit]     = useState(20);
  const [model,     setModel]     = useState('');
  const [rows,      setRows]      = useState<Record<string, unknown>[]>([]);
  const [cols,      setCols]      = useState<string[]>([]);
  const [err,       setErr]       = useState('');
  const [busy,      setBusy]      = useState(false);

  async function runQuery() {
    setBusy(true); setErr(''); setRows([]); setCols([]);
    const params: Record<string, unknown> = {};
    if (queryType === 'yealink_companies') params.limit = limit;
    if (queryType === 'model_search')      params.model = model;
    try {
      const r = await fetch('/diag-api/vpbx/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_type: queryType, params }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.error || 'Query failed'); return; }
      const results: Record<string, unknown>[] = d.results ?? [];
      setRows(results);
      setCols(results.length > 0 ? Object.keys(results[0]) : []);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="block text-xs text-slate-400 mb-1">Query</label>
          <select value={queryType} onChange={e => setQueryType(e.target.value)} className={inputCls}>
            {QUERY_TYPES.map(q => <option key={q.key} value={q.key}>{q.label}</option>)}
          </select>
        </div>
        {queryType === 'yealink_companies' && (
          <div className="w-24">
            <label className="block text-xs text-slate-400 mb-1">Limit</label>
            <input type="number" min={1} max={500} value={limit}
              onChange={e => setLimit(Number(e.target.value))} className={inputCls} />
          </div>
        )}
        {queryType === 'model_search' && (
          <div className="flex-1">
            <label className="block text-xs text-slate-400 mb-1">Model</label>
            <input value={model} onChange={e => setModel(e.target.value)}
              placeholder="e.g. T46" className={inputCls} />
          </div>
        )}
        <button onClick={runQuery} disabled={busy} className={btnCls('blue')}>
          {busy ? '…' : '▶ Run'}
        </button>
      </div>
      <ErrBox msg={err} />
      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700">
                {cols.map(c => (
                  <th key={c} className="pb-1 pr-4 text-left font-normal text-slate-500 uppercase text-[0.6rem] tracking-wider">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  {cols.map(c => (
                    <td key={c} className="py-1 pr-4 text-slate-300 font-mono">
                      {String(row[c] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-slate-600">{rows.length} rows</p>
        </div>
      ) : (
        !busy && !err && <p className="text-xs text-slate-600">Run a query to see results.</p>
      )}
    </div>
  );
}

/* ── Traceroute Helper ───────────────────────────────────────────────── */

function TraceroutePanel() {
  const [trHost,      setTrHost]      = useState('192.168.50.1');
  const [trUser,      setTrUser]      = useState('tjohnson');
  const [trPass,      setTrPass]      = useState('');
  const [trRemoteDir, setTrRemoteDir] = useState('.');
  const [out,         setOut]         = useState('');
  const [err,         setErr]         = useState('');
  const [busy,        setBusy]        = useState(false);

  async function push() {
    setBusy(true); setErr(''); setOut('');
    try {
      const r = await fetch('/diag-api/traceroute/push-helper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host: trHost, username: trUser, password: trPass, remote_dir: trRemoteDir,
        }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.error || 'Push failed'); return; }
      setOut(d.message ?? JSON.stringify(d, null, 2));
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Upload <code className="text-slate-400">traceroute_server_ctl.sh</code> to a remote host and chmod +x it.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Target Host</label>
          <input value={trHost} onChange={e => setTrHost(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Username</label>
          <input value={trUser} onChange={e => setTrUser(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Password</label>
          <input type="password" value={trPass} onChange={e => setTrPass(e.target.value)} className={inputCls} autoComplete="off" />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Remote Directory</label>
          <input value={trRemoteDir} onChange={e => setTrRemoteDir(e.target.value)} className={inputCls} />
        </div>
      </div>
      <button onClick={push} disabled={busy} className={btnCls('amber')}>
        {busy ? 'Pushing…' : '🚀 Push Script'}
      </button>
      <ErrBox msg={err} />
      <OutputBox text={out} />
    </div>
  );
}

/* ── Page root ───────────────────────────────────────────────────────── */

export default function DiagnosticPage() {
  const [tab, setTab] = useState<Tab>('webserver');

  return (
    <div className="space-y-3">
      <header className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-base font-semibold">Diagnostic Tools</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Webserver SSH, phone config analysis, VPBX DB queries — requires web_manager on port 5000
          </p>
        </div>
        <span className="text-xs text-slate-600 font-mono">→ localhost:5000</span>
      </header>

      {/* Sub-tab bar */}
      <div className="flex gap-1 border-b border-slate-800 pb-0">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-xs font-medium rounded-t transition-colors ${
              tab === t.key
                ? 'bg-slate-800 text-slate-100 border-b-2 border-blue-500'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <SectionCard title={TABS.find(t => t.key === tab)?.label ?? ''}>
        {tab === 'webserver'   && <WebserverPanel />}
        {tab === 'phoneconfig' && <PhoneConfigPanel />}
        {tab === 'vpbxdb'      && <VpbxDbPanel />}
        {tab === 'traceroute'  && <TraceroutePanel />}
      </SectionCard>
    </div>
  );
}
