'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { SectionCard } from '@/components/SectionCard';

type Action = 'deploy' | 'uninstall' | 'clean_deploy' | 'connect_only' | 'upload_only' | 'bundle';
type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

interface JobInfo {
  id: string;
  action: Action;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  return_code?: number | null;
  servers: string[];
}

const ACTION_LABELS: Record<Action, string> = {
  deploy: 'Deploy',
  uninstall: 'Uninstall',
  clean_deploy: 'Clean Deploy (uninstall + install)',
  connect_only: 'Connect-only (no changes)',
  upload_only: 'Upload-only (no install)',
  bundle: 'Build offline bundle (.zip)',
};

function statusColor(s: JobStatus): string {
  switch (s) {
    case 'succeeded': return 'text-green-400';
    case 'failed':    return 'text-red-400';
    case 'cancelled': return 'text-yellow-400';
    case 'running':   return 'text-blue-400';
    default:          return 'text-slate-500';
  }
}

function logLineColor(line: string): string {
  const l = line.toLowerCase();
  if (l.includes('[ok]') || l.includes('successful')) return 'text-green-400';
  if (l.includes('[warning]') || l.includes('warning')) return 'text-yellow-400';
  if (l.includes('[error]') || l.includes('[failed]') || l.includes('fatal error')) return 'text-red-400';
  return 'text-slate-300';
}

export default function DeployPage() {
  const [action, setAction]           = useState<Action>('clean_deploy');
  const [servers, setServers]         = useState('');
  const [workers, setWorkers]         = useState(1);
  const [username, setUsername]       = useState('123net');
  const [password, setPassword]       = useState('');
  const [rootPassword, setRootPassword] = useState('');
  const [bundleName, setBundleName]   = useState('freepbx-tools-bundle.zip');

  const [activeJob, setActiveJob]     = useState<JobInfo | null>(null);
  const [jobs, setJobs]               = useState<JobInfo[]>([]);
  const [logLines, setLogLines]       = useState<string[]>([]);
  const [busy, setBusy]               = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

  const logRef  = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const needsServers = action !== 'bundle';

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines]);

  const refreshJobs = useCallback(async () => {
    try {
      const r = await fetch('/deploy-api/jobs');
      if (r.ok) {
        const data: JobInfo[] = await r.json();
        setJobs(data.sort((a, b) => (a.created_at < b.created_at ? 1 : -1)));
        setBackendError(null);
      }
    } catch {
      setBackendError('Deploy backend unreachable — ensure the FastAPI server is running on port 8002');
    }
  }, []);

  useEffect(() => {
    refreshJobs();
    const t = setInterval(refreshJobs, 4000);
    return () => clearInterval(t);
  }, [refreshJobs]);

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const r = await fetch(`/deploy-api/jobs/${jobId}`);
      if (!r.ok) return;
      const data = await r.json();
      const job: JobInfo = data.job;
      const tail: string[] = data.tail;
      setActiveJob(job);
      setLogLines(tail);
      if (['succeeded', 'failed', 'cancelled'].includes(job.status)) {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        refreshJobs();
      }
    } catch { /* ignore */ }
  }, [refreshJobs]);

  function attachToJob(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollJob(jobId);
    pollRef.current = setInterval(() => pollJob(jobId), 500);
  }

  async function start() {
    setBusy(true);
    try {
      const r = await fetch('/deploy-api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          servers: needsServers ? servers : '',
          workers,
          username,
          password,
          root_password: rootPassword,
          bundle_name: bundleName,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const job: JobInfo = await r.json();
      attachToJob(job.id);
      refreshJobs();
    } catch (e) {
      setBackendError(`Failed to start job: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  async function cancelActive() {
    if (!activeJob) return;
    setBusy(true);
    try {
      await fetch(`/deploy-api/jobs/${activeJob.id}/cancel`, { method: 'POST' });
      refreshJobs();
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const inputCls = 'w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-slate-500';

  return (
    <div className="space-y-3">
      <header className="card flex items-start justify-between gap-4">
        <div>
          <h1 className="text-base font-semibold">FreePBX Tools Deploy</h1>
          <p className="text-xs text-slate-500 mt-0.5">SSH deployment manager — deploy, uninstall, or inspect FreePBX servers via VPN</p>
        </div>
        {activeJob && (
          <div className="flex items-center gap-2 text-xs shrink-0">
            <span className={statusColor(activeJob.status)}>●</span>
            <span className="text-slate-400 font-mono">{activeJob.id.slice(0, 8)}</span>
            <span className={statusColor(activeJob.status)}>{activeJob.status}</span>
          </div>
        )}
      </header>

      {backendError && (
        <div className="card border-red-900 text-xs text-red-400 font-mono">{backendError}</div>
      )}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <SectionCard title="Run">
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Action</label>
              <select
                value={action}
                onChange={e => setAction(e.target.value as Action)}
                className={inputCls}
              >
                {(Object.entries(ACTION_LABELS) as [Action, string][]).map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
            </div>

            {needsServers && (
              <div>
                <label className="block text-xs text-slate-400 mb-1">Servers (newline / comma / space separated)</label>
                <textarea
                  value={servers}
                  onChange={e => setServers(e.target.value)}
                  rows={3}
                  spellCheck={false}
                  placeholder={'69.39.69.102\n10.0.0.5'}
                  className={`${inputCls} font-mono resize-y`}
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Workers</label>
                <input
                  type="number" min={1} max={50}
                  value={workers}
                  onChange={e => setWorkers(Number(e.target.value))}
                  className={inputCls}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">SSH Username</label>
                <input
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">SSH Password (optional)</label>
                <input
                  type="password" autoComplete="off"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Root Password (for su root)</label>
                <input
                  type="password" autoComplete="off"
                  value={rootPassword}
                  onChange={e => setRootPassword(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>

            {!needsServers && (
              <div>
                <label className="block text-xs text-slate-400 mb-1">Bundle filename</label>
                <input
                  value={bundleName}
                  onChange={e => setBundleName(e.target.value)}
                  className={inputCls}
                />
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={start}
                disabled={busy}
                className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:bg-slate-800 disabled:text-slate-600 text-sm font-medium px-3 py-1.5 rounded transition-colors"
              >
                ▶ Start
              </button>
              <button
                onClick={cancelActive}
                disabled={busy || !activeJob || ['succeeded', 'failed', 'cancelled'].includes(activeJob?.status ?? '')}
                className="flex-1 bg-red-900 hover:bg-red-800 disabled:bg-slate-800 disabled:text-slate-600 text-sm font-medium px-3 py-1.5 rounded transition-colors"
              >
                ■ Cancel
              </button>
            </div>

            {jobs.length > 0 && (
              <div>
                <div className="text-xs text-slate-500 mb-1">Recent Jobs</div>
                <div className="space-y-0.5">
                  {jobs.slice(0, 8).map(j => (
                    <button
                      key={j.id}
                      onClick={() => attachToJob(j.id)}
                      className="w-full flex items-center justify-between px-2 py-1 rounded hover:bg-slate-800 transition-colors text-xs text-left"
                    >
                      <span className="flex items-center gap-1.5">
                        <span className={statusColor(j.status)}>●</span>
                        <span className="text-slate-300">{ACTION_LABELS[j.action] ?? j.action}</span>
                        {j.servers.length > 0 && (
                          <span className="text-slate-500 font-mono">{j.servers[0]}{j.servers.length > 1 ? ` +${j.servers.length - 1}` : ''}</span>
                        )}
                      </span>
                      <span className="text-slate-600 font-mono">{j.id.slice(0, 8)}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Live Output">
          <div
            ref={logRef}
            className="bg-slate-950 rounded p-2 h-[460px] overflow-y-auto font-mono text-xs leading-relaxed"
          >
            {logLines.length === 0 ? (
              <span className="text-slate-600">No output yet — start a job to see live logs.</span>
            ) : (
              logLines.map((line, i) => (
                <div key={i} className={logLineColor(line)}>{line || ' '}</div>
              ))
            )}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
