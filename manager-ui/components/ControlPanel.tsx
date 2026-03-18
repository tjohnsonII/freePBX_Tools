'use client';
import { postJson } from '@/lib/api';

const actions = [
  ['Start Stack', '/api/manager/start'], ['Stop Stack', '/api/manager/stop'], ['Restart Stack', '/api/manager/restart'],
  ['Doctor', '/api/manager/doctor'], ['Smoke Test', '/api/manager/test-smoke'], ['Pause Worker', '/api/manager/pause-worker'], ['Resume Worker', '/api/manager/resume-worker']
] as const;

export function ControlPanel() {
  return <div className="grid grid-cols-2 gap-2">{actions.map(([label, path]) => <button key={path} onClick={() => postJson(path)} className="rounded bg-slate-800 p-2 text-xs">{label}</button>)}</div>;
}
