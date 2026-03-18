import { getJson } from '@/lib/api';
import { AuthPanel } from '@/components/AuthPanel';
import { ControlPanel } from '@/components/ControlPanel';
import { CookieInventoryCard } from '@/components/CookieInventoryCard';
import { DataPreviewTable } from '@/components/DataPreviewTable';
import { DebugReportButton } from '@/components/DebugReportButton';
import { EventFeed } from '@/components/EventFeed';
import { LogViewer } from '@/components/LogViewer';
import { PipelineTimeline } from '@/components/PipelineTimeline';
import { PortTable } from '@/components/PortTable';
import { ProcessTable } from '@/components/ProcessTable';
import { SectionCard } from '@/components/SectionCard';
import { StatusCard } from '@/components/StatusCard';

export default async function DashboardPage() {
  const [summary, full, db, logs, ports, procs] = await Promise.all([
    getJson<any>('/api/status/summary'),
    getJson<any>('/api/status/full'),
    getJson<any>('/api/db/summary'),
    getJson<any>('/api/logs/recent'),
    getJson<any>('/api/system/ports'),
    getJson<any>('/api/system/processes'),
  ]);

  return (
    <div className="space-y-3">
      <header className="card flex items-center justify-between">
        <div className="text-sm">Webscraper NOC Dashboard • ENV DEV • Last refresh live</div>
        <div className="flex gap-2"><DebugReportButton /></div>
      </header>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-6">
        <StatusCard title="API Health" ok summary="FastAPI online" />
        <StatusCard title="Auth State" ok={summary.auth.authenticated} summary={summary.auth.validation.reason} />
        <StatusCard title="Cookie State" ok={summary.auth.cookie_count > 0} summary={`count ${summary.auth.cookie_count}`} />
        <StatusCard title="Scraper State" ok={!summary.worker.paused} summary={summary.worker.paused ? 'paused' : 'running'} />
        <StatusCard title="Ticket Fetch" ok={full.pipeline.ticket_fetch_succeeded.status === 'success'} summary={full.pipeline.ticket_fetch_succeeded.message} />
        <StatusCard title="Database" ok={db.file_exists} summary={db.db_path} />
      </div>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <SectionCard title="Control Panel"><ControlPanel /></SectionCard>
        <SectionCard title="Auth Operations"><AuthPanel /></SectionCard>
      </div>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <SectionCard title="Authentication State Details"><DataPreviewTable rows={[summary.auth]} /></SectionCard>
        <SectionCard title="Cookie Inventory"><CookieInventoryCard cookies={full.cookies} /></SectionCard>
      </div>

      <SectionCard title="Ticket Pipeline Diagnostics"><PipelineTimeline pipeline={full.pipeline} /></SectionCard>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <SectionCard title="Database Summary"><DataPreviewTable rows={[db]} /></SectionCard>
        <SectionCard title="Data Preview Tabs (starter)"><DataPreviewTable rows={logs.events.slice(-5)} /></SectionCard>
      </div>

      <SectionCard title="Live Logs"><LogViewer /></SectionCard>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <SectionCard title="Ports"><PortTable ports={ports} /></SectionCard>
        <SectionCard title="Processes"><ProcessTable processes={procs.processes} /></SectionCard>
      </div>

      <SectionCard title="Recent Events"><EventFeed /></SectionCard>
    </div>
  );
}
