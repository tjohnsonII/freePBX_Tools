const BASE = process.env.NEXT_PUBLIC_API_BASE || "";

type ApiOptions = RequestInit & { timeoutMs?: number };

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 30000);
  try {
    const res = await fetch(`${BASE}${path}`, {
      cache: "no-store",
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    const text = await res.text();
    const payload = text ? JSON.parse(text) : null;

    if (!res.ok) {
      const detail = payload?.detail || payload?.message || text || "Unknown API error";
      throw new Error(`HTTP ${res.status}: ${detail}`);
    }

    return payload as T;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("Request timed out while contacting API");
    }
    if (error instanceof Error) {
      throw error;
    }
    throw new Error("Unknown fetch error");
  } finally {
    clearTimeout(timeout);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function artifactLink(path: string): string {
  return `${BASE}/api/artifacts?path=${encodeURIComponent(path)}`;
}
