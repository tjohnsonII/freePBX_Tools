export function StatusBadge({ ok }: { ok: boolean }) {
  return <span className={`rounded px-2 py-0.5 text-xs ${ok ? 'bg-emerald-700' : 'bg-rose-700'}`}>{ok ? 'OK' : 'FAIL'}</span>;
}
