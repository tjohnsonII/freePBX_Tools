export function CookieInventoryCard({ cookies }: { cookies: any }) {
  return <div className="space-y-1 text-xs"><div>source: {cookies.source}</div><div>file: {cookies.file_path || 'n/a'}</div><div>count: {cookies.cookie_count}</div><div>domains: {(cookies.domains || []).join(', ')}</div><div>missing required: {(cookies.missing_required_cookie_names || []).join(', ') || 'none'}</div></div>;
}
