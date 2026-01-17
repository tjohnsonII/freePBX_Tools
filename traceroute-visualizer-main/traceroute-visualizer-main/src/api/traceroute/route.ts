export async function POST(req: Request) {
	try {
		const { target, mode } = await req.json();

		if (!target || typeof target !== "string") {
			return new Response(JSON.stringify({ error: "Missing or invalid 'target'" }), {
				status: 400,
				headers: { "Content-Type": "application/json" },
			});
		}

		const backendUrl = process.env.BACKEND_URL || "http://192.168.50.1:8000";
		const url = new URL(backendUrl);
		if (url.pathname === "/") url.pathname = "";
		url.searchParams.set("target", target);
		if (mode && (mode === "icmp" || mode === "tcp")) {
			url.searchParams.set("mode", mode);
		}

		const response = await fetch(url.toString(), {
			method: "GET",
			headers: { "Accept": "application/json" },
		});

		if (!response.ok) {
			const text = await response.text();
			throw new Error(`Traceroute backend responded ${response.status}: ${text}`);
		}

		const data: unknown = await response.json();

		const hasHopsArray = (value: unknown): value is { hops: unknown[] } => {
			return (
				!!value &&
				typeof value === "object" &&
				"hops" in value &&
				Array.isArray((value as { hops: unknown }).hops)
			);
		};

		const hops: unknown[] | null = Array.isArray(data)
			? data
			: hasHopsArray(data)
				? data.hops
				: null;

		if (hops === null) {
			throw new Error("Invalid response format from traceroute backend.");
		}

		return new Response(JSON.stringify({ hops }), {
			status: 200,
			headers: { "Content-Type": "application/json" },
		});
	} catch (err) {
		return new Response(
			JSON.stringify({ error: (err as Error).message || "Unknown error" }),
			{ status: 500, headers: { "Content-Type": "application/json" } }
		);
	}
}
