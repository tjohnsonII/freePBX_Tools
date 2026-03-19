const BASE = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "");

export type ApiErrorKind = "network" | "timeout" | "http" | "unknown";

export class ApiRequestError extends Error {
  kind: ApiErrorKind;
  status?: number;
  detail?: string;
  constructor(message: string, kind: ApiErrorKind, status?: number, detail?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

type ApiOptions = RequestInit & { timeoutMs?: number };
let lastApiCall: { url: string; status: number | null; ms: number; count?: number } | null = null;

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const started = Date.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 30000);
  try {
    const hasContentType = Boolean(options.headers && new Headers(options.headers).has("Content-Type"));
    const res = await fetch(`${BASE}${path}`, {
      cache: "no-store",
      ...options,
      signal: controller.signal,
      headers: {
        ...(hasContentType ? {} : { "Content-Type": "application/json" }),
        ...(options.headers || {}),
      },
    });

    const text = await res.text();
    let payload: any = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null;
    }

    if (!res.ok) {
      lastApiCall = { url: `${BASE}${path}`, status: res.status, ms: Date.now() - started };
      const detailRaw = payload?.detail ?? payload?.message ?? text ?? "Unknown API error";
      const detail = typeof detailRaw === "string" ? detailRaw : JSON.stringify(detailRaw);
      throw new ApiRequestError(`HTTP ${res.status}: ${detail}`, "http", res.status, detail);
    }
    const count = Array.isArray(payload?.items) ? payload.items.length : undefined;
    lastApiCall = { url: `${BASE}${path}`, status: res.status, ms: Date.now() - started, count };
    return payload as T;
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error;
    }
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiRequestError("Request timed out while contacting API", "timeout");
    }
    if (error instanceof Error && error.message.includes("Failed to fetch")) {
      throw new ApiRequestError("Failed to fetch API (network/proxy unreachable).", "network", undefined, error.message);
    }
    if (error instanceof Error) {
      throw new ApiRequestError(error.message, "unknown", undefined, error.message);
    }
    throw new ApiRequestError("Unknown fetch error", "unknown");
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

export async function apiPostText<T>(path: string, body: string, contentType = "text/plain"): Promise<T> {
  return apiRequest<T>(path, { method: "POST", body, headers: { "Content-Type": contentType } });
}

export function artifactLink(path: string): string {
  return `${BASE}/api/artifacts?path=${encodeURIComponent(path)}`;
}

export function apiBaseInfo(): { browserBase: string; proxyTarget: string } {
  return {
    browserBase: BASE || "(same-origin via Next rewrite)",
    proxyTarget: process.env.NEXT_PUBLIC_TICKET_API_PROXY_TARGET || "http://127.0.0.1:8788",
  };
}

export function getLastApiCall() {
  return lastApiCall;
}


export async function apiPostForm<T>(path: string, body: FormData): Promise<T> {
  return apiRequest<T>(path, { method: "POST", body, headers: {} });
}
