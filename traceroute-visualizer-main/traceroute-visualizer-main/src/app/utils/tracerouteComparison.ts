import { classifyHop, Hop } from "./tracerouteClassification";
import {
  getFirstSilentHop,
  getLastRespondingHopIndex,
  getRespondingHops,
} from "./tracerouteInsights";

export type ProbeSpec = {
  key: string;
  label: string;
  mode: "icmp" | "tcp" | "udp";
  port?: number;
};

export type TracerouteResult = {
  hops: Hop[];
  timed_out?: boolean;
  elapsed_sec?: number;
  error?: string;
  target?: string;
};

export type ProbeSummary = {
  reachedDestination: boolean;
  lastRespondingHop: number | null;
  firstSilentHop: number | null;
  respondedCount: number;
  totalHops: number;
  timed_out?: boolean;
  elapsed_sec?: number;
  error?: string;
};

export type HopMatrixRow = {
  hop: number;
  cells: Record<string, Hop | null>;
};

export type ComparisonResult = {
  perProbeSummary: Record<string, ProbeSummary>;
  insights: { title: string; detail: string }[];
  hopMatrix: HopMatrixRow[];
};

function hasHopsArray(value: unknown): value is { hops: unknown[] } {
  return (
    !!value &&
    typeof value === "object" &&
    "hops" in value &&
    Array.isArray((value as { hops: unknown }).hops)
  );
}

export async function runTracerouteProbe(
  target: string,
  probeSpec: ProbeSpec,
): Promise<TracerouteResult> {
  try {
    const res = await fetch("/api/traceroute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target,
        mode: probeSpec.mode,
        port: probeSpec.port,
      }),
    });
    if (!res.ok) {
      let msg = "Unknown error";
      try {
        const errData = await res.json();
        msg = errData.error || msg;
      } catch {}
      throw new Error(msg);
    }

    const data: unknown = await res.json();
    const hopsData: unknown[] | null = Array.isArray(data)
      ? data
      : hasHopsArray(data)
        ? data.hops
        : null;

    if (!hopsData) {
      throw new Error("Invalid response from traceroute server.");
    }

    return {
      hops: hopsData as Hop[],
      timed_out: (data as { timed_out?: boolean }).timed_out,
      elapsed_sec: (data as { elapsed_sec?: number }).elapsed_sec,
      target,
    };
  } catch (err) {
    return {
      hops: [],
      error: err instanceof Error ? err.message : String(err),
      target,
    };
  }
}

export function compareProbes(
  resultsByProbe: Record<string, TracerouteResult>,
): ComparisonResult {
  const perProbeSummary: Record<string, ProbeSummary> = {};
  const probeHopMaps: Record<string, Map<number, Hop>> = {};
  let maxHop = 0;

  Object.entries(resultsByProbe).forEach(([probeKey, result]) => {
    const target = result.target ?? "";
    const respondingHops = getRespondingHops(result.hops, target);
    const reachedDestination = respondingHops.some(entry =>
      entry.classification.flags.destination,
    );
    const lastRespondingHopIndex = getLastRespondingHopIndex(result.hops, target);
    const lastRespondingHop =
      lastRespondingHopIndex != null ? result.hops[lastRespondingHopIndex].hop : null;
    const firstSilentHop = getFirstSilentHop(result.hops, target);

    perProbeSummary[probeKey] = {
      reachedDestination,
      lastRespondingHop,
      firstSilentHop,
      respondedCount: respondingHops.length,
      totalHops: result.hops.length,
      timed_out: result.timed_out,
      elapsed_sec: result.elapsed_sec,
      error: result.error,
    };

    const hopMap = new Map<number, Hop>();
    result.hops.forEach(hop => {
      hopMap.set(hop.hop, hop);
      maxHop = Math.max(maxHop, hop.hop);
    });
    probeHopMaps[probeKey] = hopMap;
  });

  const hopMatrix: HopMatrixRow[] = [];
  for (let hop = 1; hop <= maxHop; hop += 1) {
    const cells: Record<string, Hop | null> = {};
    Object.keys(resultsByProbe).forEach(probeKey => {
      cells[probeKey] = probeHopMaps[probeKey]?.get(hop) ?? null;
    });
    hopMatrix.push({ hop, cells });
  }

  const insights: { title: string; detail: string }[] = [];
  const icmp = perProbeSummary["icmp"];
  const tcp80 = perProbeSummary["tcp:80"];
  const tcp443 = perProbeSummary["tcp:443"];
  const tcp5060 = perProbeSummary["tcp:5060"];
  const udp = perProbeSummary["udp:33434"];

  if (icmp && !icmp.reachedDestination && (tcp80?.reachedDestination || tcp443?.reachedDestination)) {
    insights.push({
      title: "ICMP likely blocked (policy), routing likely OK",
      detail: "ICMP probes stop short while TCP still reaches the destination, suggesting ICMP filtering.",
    });
  }

  if (tcp80 && tcp443 && !tcp80.reachedDestination && tcp443.reachedDestination) {
    insights.push({
      title: "Egress filtering / proxy rules",
      detail: "TCP 80 fails while TCP 443 succeeds, suggesting 80 blocked but 443 allowed.",
    });
  }

  if (tcp5060 && tcp443 && !tcp5060.reachedDestination && tcp443.reachedDestination) {
    insights.push({
      title: "SIP signaling may be filtered",
      detail: "TCP 5060 fails while TCP 443 succeeds, suggesting SIP signaling port filtering upstream.",
    });
  }

  if (udp && !udp.reachedDestination && (tcp80?.reachedDestination || tcp443?.reachedDestination)) {
    insights.push({
      title: "UDP probes likely filtered",
      detail: "UDP traceroute stops while TCP succeeds, which is consistent with MPLS or firewall filtering.",
    });
  }

  return { perProbeSummary, insights, hopMatrix };
}
