export function PipelineTimeline({ pipeline }: { pipeline: Record<string, any> }) {
  const stages = ['login_complete','cookies_loaded','auth_validated','handles_loaded','ticket_fetch_started','ticket_fetch_succeeded','db_updated','ui_read_succeeded'];
  return <div className="grid grid-cols-2 gap-2 text-xs">{stages.map((s) => <div key={s} className="rounded border border-slate-700 p-2"><div className="font-semibold">{s}</div><div>{pipeline?.[s]?.status || 'unknown'}</div><div>{pipeline?.[s]?.message || ''}</div></div>)}</div>;
}
