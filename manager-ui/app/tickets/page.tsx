import { safeGetJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

const NA = () => <p className="text-xs text-slate-500 font-mono">Manager API unreachable — retrying on next load</p>;

export default async function TicketsPage() {
  const [pipeline, recent, failures, diagnosis] = await Promise.all([
    safeGetJson<any>('/api/tickets/pipeline',               null),
    safeGetJson<any>('/api/tickets/recent',                 null),
    safeGetJson<any>('/api/tickets/failures',               null),
    safeGetJson<any>('/api/diagnostics/ticket-ingestion',   null),
  ]);
  return (
    <div className="space-y-2">
      <SectionCard title="Pipeline">{pipeline ? <DataPreviewTable rows={[pipeline]} /> : <NA />}</SectionCard>
      <SectionCard title="Recent Fetch Results">{recent ? <DataPreviewTable rows={recent.tickets || []} /> : <NA />}</SectionCard>
      <SectionCard title="Failed Requests">{failures ? <DataPreviewTable rows={failures.failures || []} /> : <NA />}</SectionCard>
      <SectionCard title="Empty Result Diagnosis">{diagnosis ? <DataPreviewTable rows={[diagnosis]} /> : <NA />}</SectionCard>
    </div>
  );
}
