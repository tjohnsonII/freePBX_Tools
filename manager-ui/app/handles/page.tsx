import { getJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

export default async function HandlesPage() {
  const handles = await getJson<any>('/api/db/handles');
  return <div className="space-y-2"><SectionCard title="Handles Summary"><DataPreviewTable rows={[{count: handles.rows?.length || 0}]} /></SectionCard><SectionCard title="Handles Table"><DataPreviewTable rows={handles.rows || []} /></SectionCard></div>;
}
