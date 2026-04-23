export function ProcessTable({ processes }: { processes: any[] }) {
  return <div className="max-h-64 overflow-auto text-xs">{processes.slice(0, 15).map((p) => <div key={p.pid} className="border-b border-slate-800 py-1">{p.pid} {p.name} {p.status}</div>)}</div>;
}
