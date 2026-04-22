import { safeGetJson } from '@/lib/api';
import { SectionCard } from '@/components/SectionCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';

const NA = () => <p className="text-xs text-slate-500 font-mono">Manager API unreachable — retrying on next load</p>;

export default async function AuthPage() {
  const [status, cookies, history, diag] = await Promise.all([
    safeGetJson<any>('/api/auth/status',          null),
    safeGetJson<any>('/api/auth/cookies/detail',  null),
    safeGetJson<any>('/api/auth/history',         null),
    safeGetJson<any>('/api/diagnostics/auth',     null),
  ]);
  return (
    <div className="space-y-2">
      <SectionCard title="Auth Status">{status ? <DataPreviewTable rows={[status]} /> : <NA />}</SectionCard>
      <SectionCard title="Cookie Source Explorer">{cookies ? <DataPreviewTable rows={[cookies]} /> : <NA />}</SectionCard>
      <SectionCard title="Session Test History">{history ? <DataPreviewTable rows={history.events || []} /> : <NA />}</SectionCard>
      <SectionCard title="Auth Diagnostics">{diag ? <DataPreviewTable rows={[diag]} /> : <NA />}</SectionCard>
    </div>
  );
}
