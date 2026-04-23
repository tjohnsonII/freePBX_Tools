'use client';
import { postJson } from '@/lib/api';

const actions = [
  ['Launch Login (isolated)', '/api/auth/seed'], ['Launch Debug Chrome', '/api/auth/sync/chrome'], ['Seed Auth (auto)', '/api/auth/seed'],
  ['Validate Auth', '/api/auth/validate'], ['Sync from Chrome', '/api/auth/sync/chrome'], ['Sync from Edge', '/api/auth/sync/edge'],
  ['Import Cookies', '/api/auth/import'], ['Clear Cookies', '/api/auth/clear']
] as const;

export function AuthPanel() {
  return <div className="space-y-2">{actions.map(([label, path]) => <button key={path + label} onClick={() => postJson(path, { browser: 'chrome', profile: 'Profile 1', domain: 'secure.123.net' })} className="block w-full rounded bg-slate-800 p-2 text-left text-xs">{label}</button>)}</div>;
}
