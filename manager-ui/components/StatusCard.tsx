import { StatusBadge } from './StatusBadge';

export function StatusCard({ title, ok, summary }: { title: string; ok: boolean; summary: string }) {
  return (
    <div className="card">
      <div className="mb-2 flex items-center justify-between"><h3 className="text-xs uppercase text-slate-400">{title}</h3><StatusBadge ok={ok} /></div>
      <p className="text-sm">{summary}</p>
    </div>
  );
}
