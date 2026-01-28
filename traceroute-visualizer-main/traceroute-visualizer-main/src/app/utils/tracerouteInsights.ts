import { classifyHop, Hop, HopClassification } from "./tracerouteClassification";

export type Insight = {
  severity: "info" | "warn" | "bad";
  title: string;
  detail: string;
};

export type TraceSummary = {
  reachedDestination: boolean;
  lastRespondingHop: number | null;
  firstSilentHop: number | null;
  respondedCount: number;
};

type RespondingHop = {
  hop: Hop;
  index: number;
  classification: HopClassification;
  latencyMs: number | null;
};

// Sample fixtures (unit-ish) to validate each rule quickly:
// Rule A (edge filter): hop 1 responds, >=70% no_response after.
// const hopsA = [
//   { hop: 1, ip: "10.0.0.1", hostname: "edge", latency: "1 ms", geo: { city: "", country: "" } },
//   { hop: 2, ip: "*", hostname: "*", latency: "*", geo: { city: "", country: "" } },
//   { hop: 3, ip: "*", hostname: "*", latency: "*", geo: { city: "", country: "" } },
// ];
// Rule B (stops at first public hop): first public responds, then silence.
// const hopsB = [
//   { hop: 1, ip: "10.0.0.1", hostname: "edge", latency: "2 ms", geo: { city: "", country: "" } },
//   { hop: 2, ip: "198.51.100.1", hostname: "isp", latency: "8 ms", geo: { city: "", country: "" } },
//   { hop: 3, ip: "*", hostname: "*", latency: "*", geo: { city: "", country: "" } },
// ];
// Rule C (RTT spike): jump >=50ms or >=2x and >=30ms.
// const hopsC = [
//   { hop: 1, ip: "10.0.0.1", hostname: "edge", latency: "5 ms", geo: { city: "", country: "" } },
//   { hop: 2, ip: "203.0.113.5", hostname: "core", latency: "12 ms", geo: { city: "", country: "" } },
//   { hop: 3, ip: "203.0.113.9", hostname: "handoff", latency: "70 ms", geo: { city: "", country: "" } },
// ];
// Rule D (destination reached): destination hop responds.
// const hopsD = [
//   { hop: 1, ip: "10.0.0.1", hostname: "edge", latency: "3 ms", geo: { city: "", country: "" } },
//   { hop: 2, ip: "93.184.216.34", hostname: "example.com", latency: "28 ms", geo: { city: "", country: "" } },
// ];

export function parseMs(value: string): number | null {
  if (!value) return null;
  const match = value.match(/-?\d+(\.\d+)?/);
  if (!match) return null;
  const parsed = Number(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getRespondingHops(hops: Hop[], target: string): RespondingHop[] {
  return hops
    .map((hop, index) => {
      const classification = classifyHop(hop, target);
      return {
        hop,
        index,
        classification,
        latencyMs: parseMs(hop.latency),
      };
    })
    .filter(entry => entry.classification.flags.responded);
}

export function getFirstSilentHop(hops: Hop[], target: string): number | null {
  for (const hop of hops) {
    if (classifyHop(hop, target).flags.no_response) {
      return hop.hop;
    }
  }
  return null;
}

export function getFirstPublicHopIndex(hops: Hop[], target: string): number | null {
  for (let index = 0; index < hops.length; index += 1) {
    const classification = classifyHop(hops[index], target);
    if (classification.flags.public_ip && classification.flags.responded) {
      return index;
    }
  }
  return null;
}

export function getLastRespondingHopIndex(hops: Hop[], target: string): number | null {
  for (let index = hops.length - 1; index >= 0; index -= 1) {
    if (classifyHop(hops[index], target).flags.responded) {
      return index;
    }
  }
  return null;
}

export function analyzeTrace(
  hops: Hop[],
  target: string,
  mode: string,
): { insights: Insight[]; summary: TraceSummary } {
  const insights: Insight[] = [];
  const probeNote = mode.toLowerCase() === "tcp" ? " TCP probes can be quieter." : "";
  const respondingHops = getRespondingHops(hops, target);
  const reachedDestination = respondingHops.some(entry => entry.classification.flags.destination);
  const lastRespondingHopIndex = getLastRespondingHopIndex(hops, target);
  const lastRespondingHop =
    lastRespondingHopIndex != null ? hops[lastRespondingHopIndex].hop : null;
  const firstSilentHop = getFirstSilentHop(hops, target);

  const summary: TraceSummary = {
    reachedDestination,
    lastRespondingHop,
    firstSilentHop,
    respondedCount: respondingHops.length,
  };

  if (hops.length > 1 && classifyHop(hops[0], target).flags.responded) {
    const tail = hops.slice(1);
    const silentCount = tail.filter(hop => classifyHop(hop, target).flags.no_response).length;
    const silentRatio = tail.length > 0 ? silentCount / tail.length : 0;
    if (silentRatio >= 0.7) {
      insights.push({
        severity: "warn",
        title: "Likely filtered after edge",
        detail: `Edge firewall / private network behavior (most hops silent after hop 1).${probeNote}`,
      });
    }
  }

  const firstPublicHopIndex = getFirstPublicHopIndex(hops, target);
  if (
    !reachedDestination &&
    firstPublicHopIndex != null &&
    lastRespondingHopIndex != null &&
    lastRespondingHopIndex >= firstPublicHopIndex &&
    lastRespondingHopIndex <= firstPublicHopIndex + 1 &&
    hops.length > lastRespondingHopIndex + 1
  ) {
    const firstPublicHop = hops[firstPublicHopIndex];
    insights.push({
      severity: "warn",
      title: "Upstream filtering near ISP boundary",
      detail: `Replies stop after hop ${firstPublicHop.hop} (first public IP), then silence.${probeNote}`,
    });
  }

  const respondingWithLatency = respondingHops.filter(entry => entry.latencyMs != null);
  let spike: {
    prev: RespondingHop;
    next: RespondingHop;
    delta: number;
  } | null = null;

  for (let index = 1; index < respondingWithLatency.length; index += 1) {
    const prev = respondingWithLatency[index - 1];
    const next = respondingWithLatency[index];
    const prevMs = prev.latencyMs ?? 0;
    const nextMs = next.latencyMs ?? 0;
    const delta = nextMs - prevMs;
    const ratioSpike = prevMs > 0 && nextMs >= prevMs * 2 && nextMs >= 30;
    const deltaSpike = delta >= 50;
    if (ratioSpike || deltaSpike) {
      if (!spike || delta > spike.delta) {
        spike = { prev, next, delta };
      }
    }
  }

  if (spike) {
    insights.push({
      severity: "warn",
      title: "Sudden latency increase",
      detail: `Latency jumped ~${Math.round(spike.delta)}ms between hop ${spike.prev.hop.hop} and hop ${spike.next.hop.hop} (possible congestion or handoff).`,
    });
  }

  if (reachedDestination) {
    insights.push({
      severity: "info",
      title: "Destination responded",
      detail: "Path likely OK even if intermediate hops are silent.",
    });
  }

  return { insights, summary };
}
