import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import clsx from 'clsx'
import { FaServer, FaPlay, FaStop, FaBroom, FaCloudUploadAlt, FaLink, FaTrash, FaBox } from 'react-icons/fa'

import { cancelJob, createJob, getJob, listJobs } from './api'
import type { Action, JobInfo } from './types'

function statusColor(status: JobInfo['status']): string {
  switch (status) {
    case 'succeeded':
      return 'var(--ok)'
    case 'failed':
      return 'var(--bad)'
    case 'cancelled':
      return 'var(--warn)'
    case 'running':
      return 'var(--accent)'
    default:
      return 'var(--muted)'
  }
}

function actionLabel(a: Action): string {
  switch (a) {
    case 'deploy':
      return 'Deploy'
    case 'uninstall':
      return 'Uninstall'
    case 'clean_deploy':
      return 'Clean Deploy'
    case 'connect_only':
      return 'Connect-only'
    case 'upload_only':
      return 'Upload-only'
    case 'bundle':
      return 'Build Bundle'
  }
}

function iconForAction(a: Action) {
  switch (a) {
    case 'deploy':
      return <FaCloudUploadAlt />
    case 'uninstall':
      return <FaTrash />
    case 'clean_deploy':
      return <FaBroom />
    case 'connect_only':
      return <FaLink />
    case 'upload_only':
      return <FaCloudUploadAlt />
    case 'bundle':
      return <FaBox />
  }
}

export default function App() {
  const [action, setAction] = useState<Action>('clean_deploy')
  const [servers, setServers] = useState('69.39.69.102')
  const [workers, setWorkers] = useState(1)
  const [username, setUsername] = useState('123net')
  const [password, setPassword] = useState('')
  const [rootPassword, setRootPassword] = useState('')
  const [bundleName, setBundleName] = useState('freepbx-tools-bundle.zip')

  const [activeJob, setActiveJob] = useState<JobInfo | null>(null)
  const [jobs, setJobs] = useState<JobInfo[]>([])
  const [logLines, setLogLines] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const logRef = useRef<HTMLDivElement | null>(null)

  const needsServers = useMemo(() => action !== 'bundle', [action])

  async function refreshJobs() {
    try {
      const j = await listJobs()
      setJobs(j.sort((a, b) => (a.created_at < b.created_at ? 1 : -1)))
    } catch {
      // ignore in MVP
    }
  }

  useEffect(() => {
    refreshJobs()
    const t = setInterval(refreshJobs, 4000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    // auto scroll
    const el = logRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [logLines])

  function disconnectWs() {
    try {
      wsRef.current?.close()
    } catch {
      // ignore
    }
    wsRef.current = null
  }

  async function attachToJob(jobId: string) {
    disconnectWs()

    const info = await getJob(jobId)
    setActiveJob(info.job)
    setLogLines(info.tail)

    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/jobs/${jobId}/ws`)
    wsRef.current = ws

    ws.onmessage = (ev: MessageEvent) => {
      const text = String(ev.data)
      setLogLines((prev: string[]) => {
        const next = [...prev, text]
        return next.length > 5000 ? next.slice(-5000) : next
      })
    }

    ws.onclose = () => {
      // keep UI stable
      wsRef.current = null
    }

    // heartbeat so backend can detect disconnects
    const hb = setInterval(() => {
      try {
        ws.send('ping')
      } catch {
        // ignore
      }
    }, 15000)

    ws.addEventListener('close', () => clearInterval(hb))
  }

  async function start() {
    setBusy(true)
    try {
      const job = await createJob({
        action,
        servers: needsServers ? servers : '',
        workers,
        username,
        password,
        root_password: rootPassword,
        bundle_name: bundleName,
      })
      await attachToJob(job.id)
      await refreshJobs()
    } finally {
      setBusy(false)
    }
  }

  async function cancelActive() {
    if (!activeJob) return
    setBusy(true)
    try {
      await cancelJob(activeJob.id)
      await refreshJobs()
    } finally {
      setBusy(false)
    }
  }

  const status = activeJob?.status ?? 'queued'

  return (
    <div className="container">
      <div className="header">
        <div className="title">
          <h1>FreePBX Tools Deploy UI</h1>
          <p>React/Vite frontend + FastAPI backend; wraps existing deploy scripts.</p>
        </div>
        <div className="badge">
          <span style={{ color: statusColor(status) }}>●</span>
          <strong>{activeJob ? `Job ${activeJob.id.slice(0, 8)}` : 'No active job'}</strong>
          <span>{activeJob ? actionLabel(activeJob.action) : ''}</span>
        </div>
      </div>

      <div className="grid">
        <div className="card">
          <h2>Run</h2>

          <div className="field">
            <label>Action</label>
            <select value={action} onChange={(e: ChangeEvent<HTMLSelectElement>) => setAction(e.target.value as Action)}>
              <option value="deploy">Deploy</option>
              <option value="uninstall">Uninstall</option>
              <option value="clean_deploy">Clean Deploy (uninstall + install)</option>
              <option value="connect_only">Connect-only (no changes)</option>
              <option value="upload_only">Upload-only (no install)</option>
              <option value="bundle">Build offline bundle (.zip)</option>
            </select>
          </div>

          {needsServers && (
            <div className="field">
              <label>
                Servers (newline / comma / space separated) <FaServer style={{ marginLeft: 6 }} />
              </label>
              <textarea
                value={servers}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setServers(e.target.value)}
                spellCheck={false}
              />
            </div>
          )}

          <div className="row">
            <div className="field">
              <label>Workers</label>
              <input
                type="number"
                min={1}
                max={50}
                value={workers}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setWorkers(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label>SSH Username</label>
              <input value={username} onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)} />
            </div>
          </div>

          <div className="row">
            <div className="field">
              <label>SSH Password (optional)</label>
              <input
                type="password"
                value={password}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="field">
              <label>Root Password (for su root)</label>
              <input
                type="password"
                value={rootPassword}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setRootPassword(e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>

          {!needsServers && (
            <div className="field">
              <label>Bundle name</label>
              <input value={bundleName} onChange={(e: ChangeEvent<HTMLInputElement>) => setBundleName(e.target.value)} />
            </div>
          )}

          <div className="btnRow">
            <button className="primary" onClick={start} disabled={busy}>
              <FaPlay style={{ marginRight: 8 }} /> Start
            </button>
            <button className="danger" onClick={cancelActive} disabled={busy || !activeJob}>
              <FaStop style={{ marginRight: 8 }} /> Cancel
            </button>
          </div>

          <div style={{ marginTop: 14 }}>
            <h2>Recent Jobs</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {jobs.slice(0, 8).map((j) => (
                <button
                  key={j.id}
                  onClick={() => attachToJob(j.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                    background: 'rgba(15,23,42,0.6)',
                  }}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ color: statusColor(j.status) }}>●</span>
                    <span style={{ opacity: 0.9 }}>{iconForAction(j.action)}</span>
                    <span>{actionLabel(j.action)}</span>
                  </span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted)' }}>{j.id.slice(0, 8)}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Live Output</h2>
          <div ref={logRef} className="log">
            {logLines.length === 0 ? (
              <span style={{ color: 'var(--muted)' }}>No output yet. Start a job to see logs.</span>
            ) : (
              logLines.map((l, idx) => {
                const s = l.toLowerCase()
                const cls =
                  s.includes('[ok]') || s.includes('successful')
                    ? 'logLineOk'
                    : s.includes('[warning]') || s.includes('warning')
                      ? 'logLineWarn'
                      : s.includes('[error]') || s.includes('[failed]') || s.includes('fatal error')
                        ? 'logLineErr'
                        : ''
                return (
                  <span key={idx} className={clsx(cls)}>
                    {l}
                  </span>
                )
              })
            )}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 18, color: 'var(--muted)', fontSize: 12 }}>
        Tip: Keep the backend bound to <code>127.0.0.1</code> unless you add authentication.
      </div>
    </div>
  )
}
