import { classifyHop, Hop, HopClassification } from "./tracerouteClassification";
import { ProbeSpec, runTracerouteProbe } from "./tracerouteComparison";

export type ProbeKey = "icmp" | "tcp" | "udp";

export type MultiProbeResult = Record<ProbeKey, Hop[] | { error: string }>;

export type HopMatch = {
  hop: Hop;
  classification: HopClassification;
  probe: ProbeKey;
  replySummary: string;
};

export type MergedHopView = {
  hopNumber: number;
  bestIp?: string;
  bestHostname?: string;
  bestLatency?: string;
  bestHop?: HopMatch;
  perProbe: Partial<Record<ProbeKey, HopMatch>>;
  state: "responsive" | "filtered" | "unreachable";
  reasonParts: string[];
};

const probeOrder: ProbeKey[] = ["icmp", "tcp", "udp"];

export const probeLabels: Record<ProbeKey, string> = {
  icmp: "ICMP",
  tcp: "TCP",
  udp: "UDP",
};

const baseProbeSpecs: Record<ProbeKey, ProbeSpec> = {
  icmp: { key: "icmp", label: "ICMP", mode: "icmp" },
  tcp: { key: "tcp", label: "TCP 80", mode: "tcp", port: 80 },
  udp: { key: "udp", label: "UDP 33434", mode: "udp", port: 33434 },
};

function isErrorResult(value: Hop[] | { error: string }): value is { error: string } {
  return !Array.isArray(value);
}

function coerceReplyValue(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") return value;
  if (typeof value === "number") return value.toString();
  return null;
}

function inferReplySummary(hop: Hop, classification: HopClassification): string {
  const candidates = [
    coerceReplyValue(hop.reply),
    coerceReplyValue(hop.type),
    coerceReplyValue(hop.icmpType),
    coerceReplyValue(hop.message),
    coerceReplyValue(hop.status),
  ].filter(Boolean) as string[];

  const normalized = candidates.join(" ").toLowerCase();
  if (normalized.includes("time exceeded") || normalized.includes("ttl")) {
    return "Responded (TTL-expired reply received)";
  }
  if (normalized.includes("unreachable")) {
    return "Responded (destination unreachable reply received)";
  }
  if (normalized.includes("timeout") || normalized.includes("no reply")) {
    return "No reply (timeout)";
  }
  if (classification.flags.responded) {
    return "Responded (TTL-expired reply received)";
  }
  return "No reply (timeout)";
}

export async function runAllProbes(target: string, port?: number): Promise<MultiProbeResult> {
  const probeSpecs: Record<ProbeKey, ProbeSpec> = {
    ...baseProbeSpecs,
    tcp: { ...baseProbeSpecs.tcp, port: port ?? baseProbeSpecs.tcp.port },
  };

  const entries = await Promise.allSettled(
    probeOrder.map(probeKey => runTracerouteProbe(target, probeSpecs[probeKey])),
  );

  const results: MultiProbeResult = {
    icmp: { error: "Probe not run." },
    tcp: { error: "Probe not run." },
    udp: { error: "Probe not run." },
  };

  entries.forEach((entry, index) => {
    const probeKey = probeOrder[index];
    if (entry.status === "fulfilled") {
      if (entry.value.error) {
        results[probeKey] = { error: entry.value.error };
      } else {
        results[probeKey] = entry.value.hops;
      }
    } else {
      const reason = entry.reason instanceof Error ? entry.reason.message : String(entry.reason);
      results[probeKey] = { error: reason };
    }
  });

  return results;
}

export function buildMergedHopViews(
  results: MultiProbeResult,
  target: string,
): { mergedHops: MergedHopView[]; reachedDestination: boolean; bottomLine: string } {
  const probeMaps: Record<ProbeKey, Map<number, Hop>> = {
    icmp: new Map(),
    tcp: new Map(),
    udp: new Map(),
  };
  let maxHop = 0;

  probeOrder.forEach(probeKey => {
    const entry = results[probeKey];
    if (Array.isArray(entry)) {
      entry.forEach(hop => {
        probeMaps[probeKey].set(hop.hop, hop);
        maxHop = Math.max(maxHop, hop.hop);
      });
    }
  });

  const respondingHopNumbers = new Set<number>();
  let reachedDestination = false;

  for (let hopNumber = 1; hopNumber <= maxHop; hopNumber += 1) {
    probeOrder.forEach(probeKey => {
      const hop = probeMaps[probeKey].get(hopNumber);
      if (!hop) return;
      const classification = classifyHop(hop, target);
      if (classification.flags.responded) {
        respondingHopNumbers.add(hopNumber);
      }
      if (classification.flags.destination) {
        reachedDestination = true;
      }
    });
  }

  const responsiveByHop: boolean[] = Array.from({ length: maxHop + 2 }, () => false);
  respondingHopNumbers.forEach(hopNumber => {
    responsiveByHop[hopNumber] = true;
  });

  const hasLaterResponse: boolean[] = Array.from({ length: maxHop + 2 }, () => false);
  let laterResponsive = false;
  for (let hopNumber = maxHop; hopNumber >= 1; hopNumber -= 1) {
    hasLaterResponse[hopNumber] = laterResponsive;
    if (responsiveByHop[hopNumber]) {
      laterResponsive = true;
    }
  }

  const mergedHops: MergedHopView[] = [];
  for (let hopNumber = 1; hopNumber <= maxHop; hopNumber += 1) {
    const perProbe: Partial<Record<ProbeKey, HopMatch>> = {};
    probeOrder.forEach(probeKey => {
      const hop = probeMaps[probeKey].get(hopNumber);
      if (!hop) return;
      const classification = classifyHop(hop, target);
      const replySummary = inferReplySummary(hop, classification);
      perProbe[probeKey] = { hop, classification, probe: probeKey, replySummary };
    });

    const bestMatch =
      probeOrder.map(probeKey => perProbe[probeKey]).find(match => match?.classification.flags.responded) ??
      probeOrder.map(probeKey => perProbe[probeKey]).find(Boolean);

    const progressedAtHop = responsiveByHop[hopNumber];
    const state = progressedAtHop
      ? "responsive"
      : hasLaterResponse[hopNumber] || reachedDestination
        ? "filtered"
        : "unreachable";

    const reasonParts: string[] = [];
    if (state === "responsive") {
      reasonParts.push("At least one probe responded at this hop.");
    } else if (state === "filtered") {
      reasonParts.push("No reply at this hop, but later hops responded.");
    } else {
      reasonParts.push("No reply and trace did not progress beyond this hop.");
    }

    probeOrder.forEach(probeKey => {
      const match = perProbe[probeKey];
      const label = probeLabels[probeKey];
      const summary = match?.classification.flags.responded
        ? match.replySummary
        : "No reply (timeout)";
      reasonParts.push(`${label}: ${summary}`);
    });

    if (bestMatch) {
      if (bestMatch.classification.flags.private_ip) {
        reasonParts.push("Private IP (RFC1918)");
      } else if (bestMatch.classification.flags.public_ip) {
        reasonParts.push("Public IP");
      }
      if (bestMatch.classification.flags.destination) {
        reasonParts.push("Destination hop");
      }
      if (bestMatch.classification.ownership?.label) {
        const location = bestMatch.classification.ownership.city
          ? ` (${bestMatch.classification.ownership.city})`
          : "";
        reasonParts.push(`Ownership: ${bestMatch.classification.ownership.label}${location}`);
      }
    }

    mergedHops.push({
      hopNumber,
      bestIp: bestMatch?.hop.ip,
      bestHostname: bestMatch?.hop.hostname,
      bestLatency: bestMatch?.hop.latency,
      bestHop: bestMatch,
      perProbe,
      state,
      reasonParts,
    });
  }

  const hasFiltered = mergedHops.some(hop => hop.state === "filtered");
  const hasResponsive = mergedHops.some(hop => hop.state === "responsive");
  const bottomLine = reachedDestination
    ? "Destination reached"
    : hasFiltered && hasResponsive
      ? "Silent-but-progressing"
      : "Unreachable / no progression";

  return { mergedHops, reachedDestination, bottomLine };
}

export function summarizeProbeErrors(results: MultiProbeResult): string[] {
  return probeOrder.flatMap(probeKey => {
    const entry = results[probeKey];
    if (!isErrorResult(entry)) {
      return [];
    }
    return `${probeLabels[probeKey]}: ${entry.error}`;
  });
}
