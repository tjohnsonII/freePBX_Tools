const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

function resolveUrl(path: string): string {
  if (API_BASE) return `${API_BASE}${path}`;
  if (typeof window === 'undefined') {
    const port = process.env.PORT ?? '3004';
    return `http://127.0.0.1:${port}${path}`;
  }
  return path;
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(resolveUrl(path), { cache: 'no-store' });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

/** Never throws — returns `fallback` on any error. Safe for SSR pages. */
export async function safeGetJson<T>(path: string, fallback: T): Promise<T> {
  try {
    return await getJson<T>(path);
  } catch {
    return fallback;
  }
}

export async function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  const res = await fetch(resolveUrl(path), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}
