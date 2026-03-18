import { LogViewer } from '@/components/LogViewer';
import { SectionCard } from '@/components/SectionCard';

export default function LogsPage() {
  return <SectionCard title="Streaming Logs"><LogViewer /></SectionCard>;
}
