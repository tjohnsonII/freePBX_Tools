import { ControlPanel } from '@/components/ControlPanel';
import { DashboardStatus } from '@/components/DashboardStatus';
import { DebugReportButton } from '@/components/DebugReportButton';
import { EventFeed } from '@/components/EventFeed';
import { InfraPanel } from '@/components/InfraPanel';
import { LogViewer } from '@/components/LogViewer';
import { SectionCard } from '@/components/SectionCard';
import { ServicePanel } from '@/components/ServicePanel';
import { WebscraperStatus } from '@/components/WebscraperStatus';

export default function DashboardPage() {
  return (
    <div className="space-y-3">
      <header className="card flex items-center justify-between">
        <div className="text-sm font-medium">123 Hosted Tools — Manager Dashboard</div>
        <div className="flex gap-2"><DebugReportButton /></div>
      </header>

      {/* All client components — page renders instantly, data loads async */}
      <DashboardStatus />

      <SectionCard title="Services — Live Control"><ServicePanel /></SectionCard>

      <SectionCard title="Scrape Control"><ControlPanel /></SectionCard>

      <SectionCard title="Live Logs"><LogViewer /></SectionCard>

      <SectionCard title="Infrastructure"><InfraPanel /></SectionCard>

      <SectionCard title="Recent Events"><EventFeed /></SectionCard>

      <SectionCard title="Webscraper — Live Stats &amp; Health"><WebscraperStatus /></SectionCard>
    </div>
  );
}
