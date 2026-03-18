import { getJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

export default async function DatabasePage() {
  const [summary, integrity, tickets] = await Promise.all([
    getJson<any>('/api/db/summary'),
    getJson<any>('/api/db/integrity'),
    getJson<any>('/api/db/tickets'),
  ]);
  return <div className="space-y-2"><SectionCard title="DB Metadata"><DataPreviewTable rows={[summary]} /></SectionCard><SectionCard title="Integrity"><DataPreviewTable rows={[integrity]} /></SectionCard><SectionCard title="Latest Inserts"><DataPreviewTable rows={tickets.rows || []} /></SectionCard></div>;
}
