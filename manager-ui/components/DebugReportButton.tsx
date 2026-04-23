'use client';
import { getJson } from '@/lib/api';

export function DebugReportButton() {
  return <button className="rounded bg-indigo-700 px-2 py-1 text-xs" onClick={async () => navigator.clipboard.writeText(JSON.stringify(await getJson('/api/debug/report'), null, 2))}>Copy Debug Report</button>;
}
