import { SectionCard } from '@/components/SectionCard';
import { ServicePanel } from '@/components/ServicePanel';

export default function ServicesPage() {
  return (
    <div className="space-y-3">
      <header className="card flex items-center justify-between">
        <div>
          <h1 className="text-base font-semibold">Services</h1>
          <p className="text-xs text-slate-400 mt-0.5">Live status and one-click restart for all web apps and system services.</p>
        </div>
      </header>
      <SectionCard title="All Services">
        <ServicePanel />
      </SectionCard>
    </div>
  );
}
