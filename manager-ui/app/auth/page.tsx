import { getJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

export default async function AuthPage() {
  const [status, cookies, history, diag] = await Promise.all([
    getJson<any>('/api/auth/status'),
    getJson<any>('/api/auth/cookies/detail'),
    getJson<any>('/api/auth/history'),
    getJson<any>('/api/diagnostics/auth'),
  ]);
  return <div className="space-y-2"><SectionCard title="Auth Status"><DataPreviewTable rows={[status]} /></SectionCard><SectionCard title="Cookie Source Explorer"><DataPreviewTable rows={[cookies]} /></SectionCard><SectionCard title="Session Test History"><DataPreviewTable rows={history.events || []} /></SectionCard><SectionCard title="Auth Diagnostics"><DataPreviewTable rows={[diag]} /></SectionCard></div>;
}
