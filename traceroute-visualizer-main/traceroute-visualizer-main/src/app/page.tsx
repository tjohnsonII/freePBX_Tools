"use client";
import { Server } from 'lucide-react';
import dynamic from 'next/dynamic';

// Dynamically import TraceMap to avoid SSR issues with Leaflet
const TraceMap = dynamic(() => import('./components/TraceMap'), { ssr: false });
import { useMemo, useState } from "react";
import { classifyHop, Hop } from "./utils/tracerouteClassification";
import { analyzeTrace } from "./utils/tracerouteInsights";
import { getTargetValidationError } from "./utils/targetValidation";
import { TracerouteResult } from "./utils/tracerouteComparison";
import {
  buildMergedHopViews,
  MultiProbeResult,
  probeLabels,
  runAllProbes,
  summarizeProbeErrors,
} from "./utils/multiProbe";
import ScenarioPicker from "./components/ScenarioPicker";
import FindingsPanel from "./components/FindingsPanel";
import EvidenceActions from "./components/EvidenceActions";
import {
  deriveFindings,
  formatTicketSummary,
  getScenarioDefinition,
  getScenarioDefinitions,
  runScenario,
  ScenarioId,
  summarizeResults,
} from "./utils/policyDetection";

function hasHopsArray(value: unknown): value is { hops: unknown[] } {
  return (
    !!value &&
    typeof value === "object" &&
    "hops" in value &&
    Array.isArray((value as { hops: unknown }).hops)
  );
}

const multiProbeKeys = ["icmp", "tcp", "udp"] as const;

export default function Page() {
  const [target, setTarget] = useState("");
  const [probe, setProbe] = useState("icmp"); // icmp or tcp
  const [loading, setLoading] = useState(false);
  const [hops, setHops] = useState<Hop[]>([]);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"traceroute" | "policy">("traceroute");
  const [multiProbeEnabled, setMultiProbeEnabled] = useState(false);
  const [multiProbeRunning, setMultiProbeRunning] = useState(false);
  const [multiProbeProgress, setMultiProbeProgress] = useState("");
  const [multiProbeResults, setMultiProbeResults] = useState<MultiProbeResult | null>(null);
  const [policyScenarioId, setPolicyScenarioId] = useState<ScenarioId>("sip-blocked");
  const [policyResults, setPolicyResults] = useState<Record<string, TracerouteResult>>({});
  const [policyRunning, setPolicyRunning] = useState(false);
  const [policyTimestamp, setPolicyTimestamp] = useState<string | null>(null);
  const [policyCompact, setPolicyCompact] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle");
  const [rtpPortsInput, setRtpPortsInput] = useState("10000, 12000, 20000");
  const analysis = analyzeTrace(hops, target, probe);
  const filteringInsightTitles = new Set([
    "Likely filtered after edge",
    "Upstream filtering near ISP boundary",
  ]);
  const hasFilteringInsight = analysis.insights.some(insight =>
    filteringInsightTitles.has(insight.title),
  );
  const mergedMultiProbe = useMemo(() => {
    if (!multiProbeResults) return null;
    return buildMergedHopViews(multiProbeResults, target);
  }, [multiProbeResults, target]);
  const multiProbeErrors = useMemo(() => {
    if (!multiProbeResults) return [];
    return summarizeProbeErrors(multiProbeResults);
  }, [multiProbeResults]);
  const parsedRtpPorts = useMemo(() => {
    const ports = rtpPortsInput
      .split(",")
      .map(part => Number(part.trim()))
      .filter(port => Number.isFinite(port) && port > 0 && port <= 65535);
    return Array.from(new Set(ports));
  }, [rtpPortsInput]);
  const rtpPortsError =
    policyScenarioId === "rtp-range" && parsedRtpPorts.length === 0
      ? "Enter at least one valid UDP port (1-65535)."
      : "";
  const scenarioDefinitions = useMemo(
    () => getScenarioDefinitions({ rtpPorts: parsedRtpPorts }),
    [parsedRtpPorts],
  );
  const activeScenario = useMemo(
    () => getScenarioDefinition(policyScenarioId, { rtpPorts: parsedRtpPorts }),
    [policyScenarioId, parsedRtpPorts],
  );
  const policySummaries = useMemo(() => summarizeResults(policyResults), [policyResults]);
  const policyFindings = useMemo(() => deriveFindings(policyResults), [policyResults]);
  const hopStateStyles: Record<
    "responsive" | "filtered" | "unreachable",
    { border: string; badge: string; label: string }
  > = {
    responsive: {
      border: "border-emerald-500",
      badge: "bg-emerald-100 text-emerald-800 border-emerald-200",
      label: "🟢 Responsive",
    },
    filtered: {
      border: "border-amber-500",
      badge: "bg-amber-100 text-amber-800 border-amber-200",
      label: "🟡 Filtered",
    },
    unreachable: {
      border: "border-red-500",
      badge: "bg-red-100 text-red-800 border-red-200",
      label: "🔴 Unreachable",
    },
  };

  const handleSubmit = async () => {
    const validationError = getTargetValidationError(target);
    if (validationError) {
      setError(validationError);
      return;
    }
    setLoading(true);
    setError("");
    setHops([]);

    try {
      const endpoint = "/api/traceroute";
      const fetchOptions: RequestInit = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, mode: probe }),
      };
      const res = await fetch(endpoint, fetchOptions);
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

      if (hopsData !== null) {
        setHops(hopsData as Hop[]);
      } else {
        setError("Invalid response from traceroute server.");
        setHops([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setHops([]);
    }
    setLoading(false);
  };

  const handleMultiProbeRun = async () => {
    const validationError = getTargetValidationError(target);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError("");
    setHops([]);
    setMultiProbeResults(null);
    setMultiProbeRunning(true);
    setMultiProbeProgress("Running multi-probe (ICMP/TCP/UDP)...");

    const results = await runAllProbes(target);
    setMultiProbeResults(results);
    setMultiProbeRunning(false);
    setMultiProbeProgress("Multi-probe run complete.");
  };

  const handlePolicyRun = async () => {
    const validationError = getTargetValidationError(target);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (rtpPortsError) {
      setError(rtpPortsError);
      return;
    }

    setError("");
    setPolicyResults({});
    setPolicyRunning(true);
    setCopyStatus("idle");

    try {
      const results = await runScenario(target, policyScenarioId, { rtpPorts: parsedRtpPorts });
      setPolicyResults(results);
      setPolicyTimestamp(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPolicyRunning(false);
    }
  };

  const handleCopySummary = async () => {
    try {
      const summary = formatTicketSummary(policyFindings.findings, policyResults);
      await navigator.clipboard.writeText(summary);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("error");
    }
  };

  const handleExportJson = () => {
    const payload = {
      target,
      scenarioId: policyScenarioId,
      scenarioTitle: activeScenario.title,
      timestamp: policyTimestamp,
      resultsByProbe: policyResults,
      summaries: policySummaries,
      findings: policyFindings.findings,
      suggestedNextSteps: policyFindings.suggestedNextSteps,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `policy-detection-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const handleToggleCompact = () => {
    setPolicyCompact(prev => !prev);
  };

  return (
    <div className={`p-4 ${policyCompact ? "policy-compact" : ""}`}>
      <h1 className="text-2xl font-bold mb-4">Traceroute Visualizer</h1>
      <div className="mb-4 flex flex-wrap items-center gap-3 policy-controls">
        <div className="flex rounded border border-slate-200 bg-white text-sm shadow-sm">
          <button
            type="button"
            onClick={() => {
              setViewMode("traceroute");
              setError("");
              setPolicyCompact(false);
            }}
            className={`px-4 py-2 font-semibold ${
              viewMode === "traceroute" ? "bg-blue-600 text-white" : "text-slate-700"
            }`}
          >
            Traceroute
          </button>
          <button
            type="button"
            onClick={() => {
              setViewMode("policy");
              setError("");
            }}
            className={`px-4 py-2 font-semibold ${
              viewMode === "policy" ? "bg-blue-600 text-white" : "text-slate-700"
            }`}
          >
            Policy Detection
          </button>
        </div>
        <div className="text-xs text-gray-600">Backend: configured via BACKEND_URL (.env.local)</div>
      </div>

      {viewMode === "traceroute" && (
        <>
          <div className="mb-2 flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <input
                id="multi-probe-toggle"
                type="checkbox"
                className="h-4 w-4"
                checked={multiProbeEnabled}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  setMultiProbeEnabled(enabled);
                  setError("");
                  setMultiProbeProgress("");
                  if (enabled) {
                    setHops([]);
                    setMultiProbeResults(null);
                  } else {
                    setMultiProbeResults(null);
                  }
                }}
              />
              <label htmlFor="multi-probe-toggle" className="font-medium">
                Run multi-probe (icmp/tcp/udp)
              </label>
            </div>
          </div>
          {!multiProbeEnabled && (
            <div className="mb-2 flex items-center space-x-4">
              <div>
                <label htmlFor="probe-select" className="mr-2 font-medium">Probe:</label>
                <select
                  id="probe-select"
                  value={probe}
                  onChange={(e) => setProbe(e.target.value)}
                  className="border p-1 rounded"
                >
                  <option value="icmp">ICMP (recommended)</option>
                  <option value="tcp">TCP (port 80)</option>
                </select>
              </div>
            </div>
          )}
        </>
      )}
      <textarea
        className="border w-full p-2 mb-2"
        rows={3}
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        placeholder="Enter a hostname or IP (e.g. google.com)"
      />
      {viewMode === "traceroute" && !multiProbeEnabled ? (
        <button
          onClick={handleSubmit}
          className="bg-blue-600 text-white px-4 py-2 rounded"
          disabled={loading}
        >
          {loading ? "Running traceroute..." : "Visualize"}
        </button>
      ) : viewMode === "traceroute" ? (
        <div className="mb-2">
          <button
            onClick={handleMultiProbeRun}
            className="mt-3 bg-blue-600 text-white px-4 py-2 rounded"
            disabled={multiProbeRunning}
          >
            {multiProbeRunning ? "Running probes..." : "Run"}
          </button>
          {multiProbeProgress && (
            <div className="mt-2 text-sm text-slate-600">{multiProbeProgress}</div>
          )}
        </div>
      ) : (
        <div className="space-y-3 policy-print">
          <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 policy-controls">
            Policy Detection runs multiple probes and interprets filtering patterns for VoIP/NOC
            tickets. UDP findings are directional only (traceroute cannot prove RTP is open).
          </div>
          <ScenarioPicker
            scenarios={scenarioDefinitions}
            selectedScenarioId={policyScenarioId}
            onSelect={setPolicyScenarioId}
            disabled={policyRunning}
            rtpPortsInput={rtpPortsInput}
            onRtpPortsInputChange={setRtpPortsInput}
            rtpPortsError={rtpPortsError}
          />
          <div className="flex flex-wrap items-center gap-3 policy-controls">
            <button
              onClick={handlePolicyRun}
              className="bg-blue-600 text-white px-4 py-2 rounded"
              disabled={policyRunning}
            >
              {policyRunning ? "Running policy detection..." : "Run scenario"}
            </button>
            {policyRunning && (
              <span className="text-xs text-slate-500">Running {activeScenario.title}...</span>
            )}
          </div>
        </div>
      )}

      {error && <p className="text-red-600 mt-4">{error}</p>}

      {viewMode === "traceroute" && !multiProbeEnabled && (
        <>
          {hops.length > 0 ? (
            <>
              <div className="mt-6">
                <h2 className="text-lg font-semibold mb-4">Route:</h2>
                <div className="mb-4 rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                  <div className="font-semibold mb-1">Legend / What this means</div>
                  <ul className="list-disc pl-5 space-y-1">
                    <li>Responded hops = we got TTL-expired reply</li>
                    <li>No response hops = filtered/silent hop, path may still be fine</li>
                    <li>Only worry if the destination never responds AND there’s no evidence of reachability</li>
                  </ul>
                </div>
                <div className="mb-4 rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-900">
                  <div className="font-semibold mb-2">Insights</div>
                  {analysis.insights.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {analysis.insights.map((insight, index) => {
                        const badgeStyle =
                          insight.severity === "bad"
                            ? "border-red-200 bg-red-100 text-red-900"
                            : insight.severity === "warn"
                            ? "border-amber-200 bg-amber-100 text-amber-900"
                            : "border-blue-200 bg-blue-100 text-blue-900";
                        return (
                          <div
                            key={`${insight.title}-${index}`}
                            className={`rounded-lg border px-3 py-2 text-xs shadow-sm ${badgeStyle}`}
                            title={insight.detail}
                          >
                            <div className="font-semibold">{insight.title}</div>
                            <div className="opacity-80">{insight.detail}</div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-xs text-slate-500">No notable patterns detected yet.</div>
                  )}
                </div>
                <div className="flex overflow-x-auto space-x-4 pb-4">
                  {hops.map((hop, idx) => {
                    const classification = classifyHop(hop, target);
                    const isNoResponse = classification.flags.no_response;
                    const latencyLabel = isNoResponse
                      ? hasFilteringInsight
                        ? "⚠ Likely filtered"
                        : "No reply"
                      : hop.latency;
                    return (
                    <div key={idx} className="flex items-center space-x-2">
                      <div className="flex flex-col items-center">
                        <div className="relative group">
                          <Server className="text-blue-600 w-6 h-6 mb-1 cursor-pointer" />
                          <div className="absolute z-10 hidden group-hover:block bg-black text-white text-xs rounded px-2 py-1 bottom-full mb-1 whitespace-nowrap shadow-md transition-opacity duration-200 opacity-90">
                            {hop.hostname} ({hop.ip})
                          </div>
                        </div>
                        <div className="bg-white border border-gray-300 shadow-md rounded-lg px-4 py-2 text-center min-w-[180px]">
                          <div className="font-bold text-sm">Hop {hop.hop}</div>
                          <div className="text-gray-700 text-xs">{hop.hostname}</div>
                          <div className="text-gray-500 text-xs">{hop.ip}</div>
                          {classification.ownership && (
                            <div className="text-gray-500 text-xs">
                              📍 {classification.ownership.label}
                              {classification.ownership.city
                                ? ` (${classification.ownership.city})`
                                : ""}
                            </div>
                          )}
                          <div
                            className={`font-medium ${
                              isNoResponse
                                ? 'text-gray-500'
                                : !isNaN(parseFloat(hop.latency)) && parseFloat(hop.latency) > 100
                                ? 'text-red-600'
                                : !isNaN(parseFloat(hop.latency)) && parseFloat(hop.latency) > 20
                                ? 'text-yellow-600'
                                : !isNaN(parseFloat(hop.latency))
                                ? 'text-green-600'
                                : 'text-blue-600'
                            }`}
                          >
                            {latencyLabel}
                            {isNoResponse && (
                              <span
                                className="ml-1 inline-block cursor-help text-gray-400"
                                title={
                                  hasFilteringInsight
                                    ? "Silence after the edge hop looks like filtering, but the path can still be reachable."
                                    : "Routers/firewalls often drop TTL-expired TCP/ICMP replies. This does not automatically mean the path is unreachable."
                                }
                              >
                                ⓘ
                              </span>
                            )}
                          </div>
                          {!isNoResponse && classification.explanation && (
                            <div className="text-xs text-gray-500">{classification.explanation}</div>
                          )}
                          <div className="text-xs text-gray-500">{hop.geo.city}{hop.geo.city && hop.geo.country ? ', ' : ''}{hop.geo.country}</div>
                        </div>
                      </div>
                      {idx < hops.length - 1 && (
                        classifyHop(hops[idx + 1], target).flags.no_response ? (
                          <div className="w-10 border-t border-dashed border-gray-400 opacity-50 h-1 flex-shrink-0" />
                        ) : (
                          <div className="w-10 h-1 bg-gray-400 flex-shrink-0" />
                        )
                      )}
                    </div>
                    );
                  })}
                </div>
              </div>
              <div className="mt-8 h-[500px]">
                <TraceMap hops={hops} target={target} />
              </div>
            </>
          ) : (
            error === '' && !loading && (
              <div className="mt-6 text-gray-500">No hops to display.</div>
            )
          )}
        </>
      )}

      {viewMode === "traceroute" && multiProbeEnabled && mergedMultiProbe && (
        <div className="mt-8 space-y-4">
          <h2 className="text-lg font-semibold">Multi-probe view</h2>
          <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
            <div className="font-semibold">Bottom line</div>
            <div className="text-base font-semibold text-slate-900">
              {mergedMultiProbe.bottomLine}
            </div>
          </div>
          {multiProbeErrors.length > 0 && (
            <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <div className="font-semibold">Probe errors</div>
              <ul className="list-disc pl-5">
                {multiProbeErrors.map(errorLine => (
                  <li key={errorLine}>{errorLine}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex overflow-x-auto space-x-4 pb-4">
            {mergedMultiProbe.mergedHops.map(hopView => {
              const style = hopStateStyles[hopView.state];
              const bestLabel = hopView.bestIp ? `${hopView.bestIp}` : "No reply";
              const bestLatency = hopView.bestLatency ?? "";
              const tooltip = hopView.reasonParts.join(" ");
              const bestHop = hopView.bestHop;
              return (
                <div key={hopView.hopNumber} className="flex items-center space-x-2">
                  <div className="flex flex-col items-center">
                    <div className="relative group">
                      <Server className="text-blue-600 w-6 h-6 mb-1 cursor-pointer" />
                      {bestHop && (
                        <div className="absolute z-10 hidden group-hover:block bg-black text-white text-xs rounded px-2 py-1 bottom-full mb-1 whitespace-nowrap shadow-md transition-opacity duration-200 opacity-90">
                          {bestHop.hop.hostname} ({bestHop.hop.ip})
                        </div>
                      )}
                    </div>
                    <div
                      className={`bg-white border border-gray-200 shadow-md rounded-lg px-4 py-2 text-center min-w-[200px] border-l-4 ${style.border}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-bold text-sm">Hop {hopView.hopNumber}</div>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${style.badge}`}
                          title={tooltip}
                        >
                          {style.label}
                        </span>
                      </div>
                      <div className="text-gray-700 text-xs">{hopView.bestHostname || "—"}</div>
                      <div className="text-gray-500 text-xs">{bestLabel}</div>
                      {bestHop?.classification.ownership && (
                        <div className="text-gray-500 text-xs">
                          📍 {bestHop.classification.ownership.label}
                          {bestHop.classification.ownership.city
                            ? ` (${bestHop.classification.ownership.city})`
                            : ""}
                        </div>
                      )}
                      <div className="mt-1 text-xs text-slate-600">
                        {multiProbeKeys.map(key => {
                          const match = hopView.perProbe[key];
                          const label = probeLabels[key];
                          const summary = match?.classification.flags.responded
                            ? `${match.hop.ip} (${match.hop.latency})`
                            : "No reply";
                          return (
                            <div key={`${hopView.hopNumber}-${key}`}>
                              <span className="font-semibold">{label}:</span> {summary}
                            </div>
                          );
                        })}
                      </div>
                      {bestLatency && (
                        <div className="mt-1 text-xs text-gray-500">Best RTT: {bestLatency}</div>
                      )}
                    </div>
                  </div>
                  {hopView.hopNumber < mergedMultiProbe.mergedHops.length && (
                    hopView.state === "responsive" ? (
                      <div className="w-10 h-1 bg-gray-400 flex-shrink-0" />
                    ) : (
                      <div className="w-10 border-t border-dashed border-gray-400 opacity-50 h-1 flex-shrink-0" />
                    )
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-8 h-[500px]">
            <TraceMap hops={[]} target={target} hopViews={mergedMultiProbe.mergedHops} />
          </div>
        </div>
      )}

      {viewMode === "policy" && Object.keys(policyResults).length > 0 && (
        <div className="mt-8 space-y-4 policy-print">
          <h2 className="text-lg font-semibold">Results Summary</h2>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {activeScenario.probes.map(probe => {
              const summary = policySummaries[probe.key];
              return (
                <div
                  key={probe.key}
                  className="rounded border border-slate-200 bg-white p-3 text-sm shadow-sm"
                >
                  <div className="font-semibold">{probe.label}</div>
                  {summary?.error ? (
                    <div className="mt-1 text-xs text-red-600">Error: {summary.error}</div>
                  ) : (
                    <>
                      <div className="mt-1 text-xs text-slate-600">
                        Destination: {summary?.reachedDestination ? "Reached" : "Not reached"}
                      </div>
                      <div className="text-xs text-slate-600">
                        First silent hop: {summary?.firstSilentHop ?? "None"}
                      </div>
                      <div className="text-xs text-slate-600">
                        Last responding hop: {summary?.lastRespondingHop ?? "None"}
                      </div>
                      <div className="text-xs text-slate-600">
                        Elapsed: {summary?.elapsedSec != null ? `${summary.elapsedSec}s` : "—"}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>

          <FindingsPanel
            findings={policyFindings.findings}
            confidence={policyFindings.confidence}
            suggestedNextSteps={policyFindings.suggestedNextSteps}
          />

          <div className="rounded border border-slate-200 bg-white p-3">
            <div className="text-sm font-semibold mb-2">Evidence actions</div>
            <EvidenceActions
              onCopySummary={handleCopySummary}
              onExportJson={handleExportJson}
              onToggleCompact={handleToggleCompact}
              compactEnabled={policyCompact}
              copyStatus={copyStatus}
              disabled={policyRunning}
            />
          </div>
        </div>
      )}
    </div>
  );
}
