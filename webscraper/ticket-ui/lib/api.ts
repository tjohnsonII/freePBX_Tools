const BASE = process.env.NEXT_PUBLIC_TICKET_API_BASE || "http://127.0.0.1:8787";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error ${res.status}`);
  }
  return res.json();
}

export function artifactLink(path: string): string {
  return `${BASE}/artifacts?path=${encodeURIComponent(path)}`;
}
