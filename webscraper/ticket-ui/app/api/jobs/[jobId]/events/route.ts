import { NextRequest, NextResponse } from "next/server";

const API_TARGET = process.env.TICKET_API_PROXY_TARGET || "http://127.0.0.1:8788";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: { jobId: string } }
) {
  const jobId = encodeURIComponent(context.params.jobId);
  const limit = request.nextUrl.searchParams.get("limit") ?? "50";
  const url = `${API_TARGET}/api/jobs/${jobId}/events?limit=${encodeURIComponent(limit)}`;

  try {
    const upstream = await fetch(url, { cache: "no-store" });
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Proxy request failed", detail: String(error) },
      { status: 502 }
    );
  }
}
