import { getJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

export default async function SystemPage() {
  const [ports, processes, env, paths, diag] = await Promise.all([
    getJson<any>('/api/system/ports'),
    getJson<any>('/api/system/processes'),
    getJson<any>('/api/system/env'),
    getJson<any>('/api/system/paths'),
    getJson<any>('/api/diagnostics/system'),
  ]);
  return <div className="space-y-2"><SectionCard title="Ports"><DataPreviewTable rows={[ports]} /></SectionCard><SectionCard title="Processes"><DataPreviewTable rows={processes.processes || []} /></SectionCard><SectionCard title="Env"><DataPreviewTable rows={[env]} /></SectionCard><SectionCard title="Paths"><DataPreviewTable rows={[paths]} /></SectionCard><SectionCard title="System Diagnostics"><DataPreviewTable rows={[diag]} /></SectionCard></div>;
}
