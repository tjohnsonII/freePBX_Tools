import { getJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

export default async function TicketsPage() {
  const [pipeline, recent, failures, diagnosis] = await Promise.all([
    getJson<any>('/api/tickets/pipeline'),
    getJson<any>('/api/tickets/recent'),
    getJson<any>('/api/tickets/failures'),
    getJson<any>('/api/diagnostics/ticket-ingestion'),
  ]);
  return <div className="space-y-2"><SectionCard title="Pipeline"><DataPreviewTable rows={[pipeline]} /></SectionCard><SectionCard title="Recent Fetch Results"><DataPreviewTable rows={recent.tickets || []} /></SectionCard><SectionCard title="Failed Requests"><DataPreviewTable rows={failures.failures || []} /></SectionCard><SectionCard title="Empty Result Diagnosis"><DataPreviewTable rows={[diagnosis]} /></SectionCard></div>;
}
