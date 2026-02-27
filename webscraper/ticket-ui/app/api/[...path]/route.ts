import { NextRequest, NextResponse } from "next/server";

const API_TARGET = process.env.TICKET_API_PROXY_TARGET || "http://127.0.0.1:8787";
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
]);

export const dynamic = "force-dynamic";

function buildTargetUrl(path: string[], search: string): string {
  const normalized = path.map((segment) => encodeURIComponent(segment)).join("/");
  return `${API_TARGET}/api/${normalized}${search}`;
}

function filteredHeaders(headers: Headers): Headers {
  const out = new Headers();
  for (const [key, value] of headers.entries()) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      out.set(key, value);
    }
  }
  return out;
}

function isConnectionRefused(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const msg = `${error.message} ${(error as { cause?: { code?: string } }).cause?.code || ""}`.toLowerCase();
  return msg.includes("econnrefused") || msg.includes("fetch failed") || msg.includes("networkerror");
}

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const url = buildTargetUrl(path, request.nextUrl.search);

  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers: filteredHeaders(request.headers),
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
    });

    const responseHeaders = filteredHeaders(upstream.headers);
    return new Response(await upstream.arrayBuffer(), {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    if (isConnectionRefused(error)) {
      return NextResponse.json(
        {
          error: "API unavailable",
          target: API_TARGET,
          hint: "API still starting or crashed",
        },
        { status: 503 },
      );
    }
    return NextResponse.json({ error: "Proxy request failed", detail: String(error) }, { status: 502 });
  }
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path || []);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path || []);
}

export async function PUT(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path || []);
}

export async function PATCH(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path || []);
}

export async function DELETE(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path || []);
}

export async function OPTIONS(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path || []);
}

export async function HEAD(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path || []);
}
