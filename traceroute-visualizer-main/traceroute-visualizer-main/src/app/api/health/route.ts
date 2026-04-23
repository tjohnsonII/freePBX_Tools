export async function GET() {
  try {
    const backendUrl = process.env.BACKEND_URL || "http://192.168.50.1:8000";
    const url = new URL(backendUrl);
    if (url.pathname === "/") url.pathname = "";
    // Use a fast internal target if available, else 8.8.8.8
    const defaultTarget = process.env.HEALTH_TARGET || "8.8.8.8";
    url.searchParams.set("target", defaultTarget);

    const response = await fetch(url.toString(), { method: "GET" });
    const ok = response.ok;
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }

    return new Response(JSON.stringify({ ok, backend: backendUrl, body }), {
      status: ok ? 200 : 502,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ ok: false, error: (err as Error).message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}