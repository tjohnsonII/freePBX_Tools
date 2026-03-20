import { NextRequest, NextResponse } from "next/server";

const API_TARGET = process.env.TICKET_API_PROXY_TARGET || "http://127.0.0.1:8788";

export const dynamic = "force-dynamic";

export async function GET(_request: NextRequest, context: { params: { jobId: string } }) {
  const jobId = encodeURIComponent(context.params.jobId);
  const url = `${API_TARGET}/jobs/${jobId}`;

  try {
    const upstream = await fetch(url, { cache: "no-store" });
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json({ error: "Proxy request failed", detail: String(error) }, { status: 502 });
  }
}
