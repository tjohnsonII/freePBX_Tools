import { safeGetJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

const NA = () => <p className="text-xs text-slate-500 font-mono">Manager API unreachable — retrying on next load</p>;

export default async function DatabasePage() {
  const [summary, integrity, tickets] = await Promise.all([
    safeGetJson<any>('/api/db/summary',   null),
    safeGetJson<any>('/api/db/integrity', null),
    safeGetJson<any>('/api/db/tickets',   null),
  ]);
  return (
    <div className="space-y-2">
      <SectionCard title="DB Metadata">{summary ? <DataPreviewTable rows={[summary]} /> : <NA />}</SectionCard>
      <SectionCard title="Integrity">{integrity ? <DataPreviewTable rows={[integrity]} /> : <NA />}</SectionCard>
      <SectionCard title="Latest Inserts">{tickets ? <DataPreviewTable rows={tickets.rows || []} /> : <NA />}</SectionCard>
    </div>
  );
}
