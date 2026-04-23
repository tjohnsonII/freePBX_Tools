import {
  getFirstSilentHop,
  getLastRespondingHopIndex,
  getRespondingHops,
} from "./tracerouteInsights";
import { ProbeSpec, runTracerouteProbe, TracerouteResult } from "./tracerouteComparison";

export type ScenarioId =
  | "sip-blocked"
  | "web-allowed"
  | "udp-filtered"
  | "rtp-range"
  | "asymmetric-filtering";

export type ScenarioDefinition = {
  id: ScenarioId;
  title: string;
  description: string;
  probes: ProbeSpec[];
};

export type PolicyProbeSummary = {
  reachedDestination: boolean;
  lastRespondingHop: number | null;
  firstSilentHop: number | null;
  respondedCount: number;
  totalHops: number;
  elapsedSec?: number;
  error?: string;
};

export type PolicyFinding = {
  title: string;
  detail: string;
  severity: "good" | "warn" | "bad";
  confidence: "low" | "medium" | "high";
};

export type PolicyFindingsResult = {
  findings: PolicyFinding[];
  confidence: "low" | "medium" | "high";
  suggestedNextSteps: string[];
};

export type ScenarioOptions = {
  rtpPorts?: number[];
};

const DEFAULT_RTP_PORTS = [10000, 12000, 20000];

const buildProbeKey = (mode: ProbeSpec["mode"], port?: number) =>
  mode === "icmp" ? "icmp" : `${mode}:${port ?? ""}`;

const defaultProbeLabel = (mode: ProbeSpec["mode"], port?: number) => {
  if (mode === "icmp") {
    return "ICMP";
  }
  return `${mode.toUpperCase()} ${port ?? ""}`.trim();
};

const makeProbe = (mode: ProbeSpec["mode"], port?: number, label?: string): ProbeSpec => ({
  key: buildProbeKey(mode, port),
  label: label ?? defaultProbeLabel(mode, port),
  mode,
  port,
});

const getScenarioBaseDefinitions = (): Omit<ScenarioDefinition, "probes">[] => [
  {
    id: "sip-blocked",
    title: "SIP blocked?",
    description: "Compare SIP signaling (5060) against HTTPS and ICMP.",
  },
  {
    id: "web-allowed",
    title: "Web allowed?",
    description: "Check if HTTP/HTTPS path is open alongside ICMP.",
  },
  {
    id: "udp-filtered",
    title: "UDP filtered?",
    description: "Compare UDP traceroute against TCP 443 baseline.",
  },
  {
    id: "rtp-range",
    title: "RTP range sanity",
    description:
      "Probe RTP-style UDP ports. Traceroute cannot prove RTP is open end-to-end.",
  },
  {
    id: "asymmetric-filtering",
    title: "Asymmetric filtering",
    description:
      "Single-vantage screening for silent hops; future support for dual-probe validation.",
  },
];

const getScenarioProbes = (scenarioId: ScenarioId, options?: ScenarioOptions): ProbeSpec[] => {
  switch (scenarioId) {
    case "sip-blocked":
      return [
        makeProbe("tcp", 5060, "TCP 5060 (SIP)"),
        makeProbe("tcp", 443, "TCP 443"),
        makeProbe("icmp"),
      ];
    case "web-allowed":
      return [makeProbe("tcp", 80, "TCP 80"), makeProbe("tcp", 443, "TCP 443"), makeProbe("icmp")];
    case "udp-filtered":
      return [
        makeProbe("udp", 33434, "UDP 33434"),
        makeProbe("tcp", 443, "TCP 443"),
        makeProbe("icmp"),
      ];
    case "rtp-range": {
      const ports =
        options?.rtpPorts && options.rtpPorts.length > 0 ? options.rtpPorts : DEFAULT_RTP_PORTS;
      const udpProbes = ports.map(port => makeProbe("udp", port, `UDP ${port}`));
      return [...udpProbes, makeProbe("tcp", 443, "TCP 443 baseline")];
    }
    case "asymmetric-filtering":
      return [
        makeProbe("icmp"),
        makeProbe("tcp", 443, "TCP 443"),
        makeProbe("udp", 33434, "UDP 33434"),
      ];
    default:
      return [makeProbe("icmp"), makeProbe("tcp", 443, "TCP 443")];
  }
};

export const getScenarioDefinitions = (options?: ScenarioOptions): ScenarioDefinition[] => {
  return getScenarioBaseDefinitions().map(definition => ({
    ...definition,
    probes: getScenarioProbes(definition.id, options),
  }));
};

export const getScenarioDefinition = (
  scenarioId: ScenarioId,
  options?: ScenarioOptions,
): ScenarioDefinition => {
  const definition = getScenarioBaseDefinitions().find(item => item.id === scenarioId);
  if (!definition) {
    return {
      id: "sip-blocked",
      title: "SIP blocked?",
      description: "Compare SIP signaling (5060) against HTTPS and ICMP.",
      probes: getScenarioProbes("sip-blocked", options),
    };
  }
  return {
    ...definition,
    probes: getScenarioProbes(definition.id, options),
  };
};

export const describeProbeKey = (probeKey: string): string => {
  if (probeKey === "icmp") {
    return "ICMP";
  }
  const [mode, port] = probeKey.split(":");
  if (!mode) return probeKey;
  const upper = mode.toUpperCase();
  return port ? `${upper} ${port}` : upper;
};

export const summarizeResults = (
  resultsByProbe: Record<string, TracerouteResult>,
): Record<string, PolicyProbeSummary> => {
  const summaries: Record<string, PolicyProbeSummary> = {};
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

    summaries[probeKey] = {
      reachedDestination,
      lastRespondingHop,
      firstSilentHop,
      respondedCount: respondingHops.length,
      totalHops: result.hops.length,
      elapsedSec: result.elapsed_sec,
      error: result.error,
    };
  });

  return summaries;
};

const addNextStep = (steps: string[], step: string) => {
  if (!steps.includes(step)) {
    steps.push(step);
  }
};

export const deriveFindings = (
  resultsByProbe: Record<string, TracerouteResult>,
): PolicyFindingsResult => {
  const summaries = summarizeResults(resultsByProbe);
  const findings: PolicyFinding[] = [];
  const nextSteps: string[] = [];

  const tcp443 = summaries["tcp:443"];
  const tcp5060 = summaries["tcp:5060"];
  const icmp = summaries["icmp"];
  const tcpReached = Object.entries(summaries).some(
    ([key, summary]) => key.startsWith("tcp:") && summary.reachedDestination,
  );
  const udpEntries = Object.entries(summaries).filter(([key]) => key.startsWith("udp:"));
  const udpFailure = udpEntries.some(([, summary]) => !summary.reachedDestination);

  if (tcp443?.reachedDestination && tcp5060 && !tcp5060.reachedDestination) {
    findings.push({
      title: "SIP port likely blocked upstream (5060 filtered)",
      detail: "TCP 443 reaches the destination while TCP 5060 does not, so routing likely OK.",
      severity: "bad",
      confidence: "medium",
    });
    addNextStep(nextSteps, "Allow outbound TCP/5060 to SIP provider or SIPStation IP ranges.");
    addNextStep(nextSteps, "Disable SIP ALG if enabled on the firewall.");
  }

  if (icmp && !icmp.reachedDestination && tcpReached) {
    findings.push({
      title: "ICMP likely blocked (policy)",
      detail: "TCP probes succeed while ICMP fails, so silent hops may be normal.",
      severity: "warn",
      confidence: "medium",
    });
    addNextStep(nextSteps, "Document ICMP filtering and rely on TCP probes for reachability.");
  }

  if (udpFailure && tcpReached) {
    findings.push({
      title: "UDP probes likely filtered",
      detail:
        "UDP traceroute stops while TCP succeeds. UDP filtering is common; traceroute cannot prove RTP reachability.",
      severity: "warn",
      confidence: "medium",
    });
    addNextStep(nextSteps, "Validate UDP reachability with a UDP pinger or STUN/ICE test.");
    addNextStep(nextSteps, "Review NAT timeouts and RTP keepalive intervals.");
  }

  const silentHopCounts = new Map<number, number>();
  Object.values(summaries).forEach(summary => {
    if (summary.firstSilentHop != null) {
      silentHopCounts.set(
        summary.firstSilentHop,
        (silentHopCounts.get(summary.firstSilentHop) ?? 0) + 1,
      );
    }
  });
  let consistentSilentHop: number | null = null;
  let consistentSilentCount = 0;
  silentHopCounts.forEach((count, hop) => {
    if (count > consistentSilentCount) {
      consistentSilentCount = count;
      consistentSilentHop = hop;
    }
  });

  if (consistentSilentHop != null && consistentSilentCount >= 2) {
    findings.push({
      title: `Filtering likely begins at/after hop ${consistentSilentHop}`,
      detail: "Multiple probes go silent at the same hop, suggesting a policy boundary.",
      severity: "warn",
      confidence: "medium",
    });
    addNextStep(nextSteps, `Share hop ${consistentSilentHop} evidence with ISP or edge firewall team.`);
  }

  const edgeOnlyResponses = Object.values(summaries).filter(
    summary => summary.respondedCount === 1 && summary.lastRespondingHop === 1,
  );
  if (edgeOnlyResponses.length >= 2) {
    findings.push({
      title: "Edge firewall may drop TTL-expired replies",
      detail:
        "Only hop 1 responds across probes, then silence. Path may still be reachable beyond the edge.",
      severity: "warn",
      confidence: "low",
    });
    addNextStep(
      nextSteps,
      "Check edge firewall ACLs that drop TTL-expired responses while allowing sessions.",
    );
  }

  if (findings.length === 0) {
    findings.push({
      title: "No strong policy blocks detected",
      detail: "Results do not show a consistent policy pattern. Consider endpoint tests.",
      severity: "good",
      confidence: "low",
    });
    addNextStep(nextSteps, "Run endpoint tests (HTTPS/SIP) from the same source host.");
  }

  const confidenceOrder = ["low", "medium", "high"] as const;
  const overallConfidence =
    findings
      .map(finding => finding.confidence)
      .sort((a, b) => confidenceOrder.indexOf(b) - confidenceOrder.indexOf(a))[0] ?? "low";

  return {
    findings,
    confidence: overallConfidence,
    suggestedNextSteps: nextSteps,
  };
};

const formatSummaryLine = (probeLabel: string, summary?: PolicyProbeSummary) => {
  if (!summary) {
    return `${probeLabel}: no data`;
  }
  if (summary.error) {
    return `${probeLabel}: error (${summary.error})`;
  }
  const reachedLabel = summary.reachedDestination ? "reached dest ✅" : "not reached ❌";
  const silentLabel =
    summary.firstSilentHop != null ? `silent begins hop ${summary.firstSilentHop}` : "no silence";
  return `${probeLabel}: ${reachedLabel} (${silentLabel})`;
};

export const formatTicketSummary = (
  findings: PolicyFinding[],
  resultsByProbe: Record<string, TracerouteResult>,
): string => {
  const summaries = summarizeResults(resultsByProbe);
  const timestamp = new Date().toLocaleString();
  const target = Object.values(resultsByProbe)[0]?.target ?? "Unknown target";

  const probeLines = Object.keys(summaries).map(key =>
    formatSummaryLine(describeProbeKey(key), summaries[key]),
  );
  const findingLines = findings.map(finding => `- ${finding.title}: ${finding.detail}`);

  const nextSteps = deriveFindings(resultsByProbe).suggestedNextSteps;
  const nextStepsLines = nextSteps.map(step => `- ${step}`);

  return [
    `Target: ${target}`,
    "",
    `Date/time: ${timestamp}`,
    "",
    "Probes run:",
    ...probeLines.map(line => `- ${line}`),
    "",
    "Findings:",
    ...(findingLines.length > 0 ? findingLines : ["- None"]),
    "",
    "Suggested next steps:",
    ...(nextStepsLines.length > 0 ? nextStepsLines : ["- None"]),
  ].join("\n");
};

export const runScenario = async (
  target: string,
  scenarioId: ScenarioId,
  options?: ScenarioOptions,
): Promise<Record<string, TracerouteResult>> => {
  const scenario = getScenarioDefinition(scenarioId, options);
  const results: Record<string, TracerouteResult> = {};

  for (const probe of scenario.probes) {
    // eslint-disable-next-line no-await-in-loop
    const result = await runTracerouteProbe(target, probe);
    results[probe.key] = result;
  }

  return results;
};
