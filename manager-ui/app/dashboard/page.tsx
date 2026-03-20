import { getJson } from '@/lib/api';
import { ControlPanel } from '@/components/ControlPanel';
import { DataPreviewTable } from '@/components/DataPreviewTable';
import { DebugReportButton } from '@/components/DebugReportButton';
import { EventFeed } from '@/components/EventFeed';
import { LogViewer } from '@/components/LogViewer';
import { PortTable } from '@/components/PortTable';
import { ProcessTable } from '@/components/ProcessTable';
import { SectionCard } from '@/components/SectionCard';
import { StatusCard } from '@/components/StatusCard';
import { WebscraperStatus } from '@/components/WebscraperStatus';

export default async function DashboardPage() {
  const [summary, db, dbIntegrity, ports, procs] = await Promise.all([
    getJson<any>('/api/status/summary'),
    getJson<any>('/api/db/summary'),
    getJson<any>('/api/db/integrity'),
    getJson<any>('/api/system/ports'),
    getJson<any>('/api/system/processes'),
  ]);

  return (
    <div className="space-y-3">
      <header className="card flex items-center justify-between">
        <div className="text-sm">Webscraper Hosted Dashboard • ENV DEV • Last refresh live</div>
        <div className="flex gap-2"><DebugReportButton /></div>
      </header>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <StatusCard title="API Health" ok summary="FastAPI online" />
        <StatusCard title="Scraper Worker" ok={!summary.worker.paused} summary={summary.worker.paused ? 'paused' : 'running'} />
        <StatusCard title="Database" ok={db.file_exists} summary={db.file_exists ? `${db.tickets_count ?? 0} tickets` : 'not found'} />
        <StatusCard title="DB Integrity" ok={dbIntegrity.ok} summary={dbIntegrity.result ?? dbIntegrity.message ?? 'unknown'} />
      </div>

      <SectionCard title="Control Panel"><ControlPanel /></SectionCard>

      <SectionCard title="Database Summary"><DataPreviewTable rows={[db]} /></SectionCard>

      <SectionCard title="Live Logs"><LogViewer /></SectionCard>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <SectionCard title="Ports"><PortTable ports={ports} /></SectionCard>
        <SectionCard title="Processes"><ProcessTable processes={procs.processes} /></SectionCard>
      </div>

      <SectionCard title="Recent Events"><EventFeed /></SectionCard>

      <SectionCard title="Webscraper — Live Stats &amp; Health"><WebscraperStatus /></SectionCard>
    </div>
  );
}
