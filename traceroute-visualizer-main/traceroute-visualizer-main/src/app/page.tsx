"use client";
import { Server } from 'lucide-react';
import dynamic from 'next/dynamic';

// Dynamically import TraceMap to avoid SSR issues with Leaflet
const TraceMap = dynamic(() => import('./components/TraceMap'), { ssr: false });
import { useMemo, useState } from "react";
import { classifyHop, Hop } from "./utils/tracerouteClassification";
import { analyzeTrace } from "./utils/tracerouteInsights";
import {
  compareProbes,
  ProbeSpec,
  runTracerouteProbe,
  TracerouteResult,
} from "./utils/tracerouteComparison";
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

const probePresets: ProbeSpec[] = [
  { key: "icmp", label: "ICMP", mode: "icmp" },
  { key: "udp:33434", label: "UDP 33434", mode: "udp", port: 33434 },
  { key: "tcp:80", label: "TCP 80", mode: "tcp", port: 80 },
  { key: "tcp:443", label: "TCP 443", mode: "tcp", port: 443 },
  { key: "tcp:5060", label: "TCP 5060 (SIP)", mode: "tcp", port: 5060 },
];

const defaultMultiProbeSelection = new Set([
  "icmp",
  "tcp:80",
  "tcp:443",
  "tcp:5060",
]);

export default function Page() {
  const [target, setTarget] = useState("");
  const [probe, setProbe] = useState("icmp"); // icmp or tcp
  const [loading, setLoading] = useState(false);
  const [hops, setHops] = useState<Hop[]>([]);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"traceroute" | "policy">("traceroute");
  const [multiProbeEnabled, setMultiProbeEnabled] = useState(false);
  const [multiProbeSelections, setMultiProbeSelections] = useState<Record<string, boolean>>(() => {
    return Object.fromEntries(
      probePresets.map(probePreset => [
        probePreset.key,
        defaultMultiProbeSelection.has(probePreset.key),
      ]),
    );
  });
  const [multiProbeRunning, setMultiProbeRunning] = useState(false);
  const [multiProbeProgress, setMultiProbeProgress] = useState("");
  const [multiProbeResults, setMultiProbeResults] = useState<Record<string, TracerouteResult>>({});
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
  const comparison = useMemo(() => compareProbes(multiProbeResults), [multiProbeResults]);
  const probeLabelMap = useMemo(() => {
    return Object.fromEntries(probePresets.map(probePreset => [probePreset.key, probePreset.label]));
  }, []);
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

  const handleSubmit = async () => {
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
    const selectedProbes = probePresets.filter(
      probePreset => multiProbeSelections[probePreset.key],
    );

    if (!target.trim()) {
      setError("Please enter a hostname or IP before running probes.");
      return;
    }

    if (selectedProbes.length === 0) {
      setError("Select at least one probe preset to run.");
      return;
    }

    setError("");
    setHops([]);
    setMultiProbeResults({});
    setMultiProbeRunning(true);
    setMultiProbeProgress("");

    const nextResults: Record<string, TracerouteResult> = {};
    for (let index = 0; index < selectedProbes.length; index += 1) {
      const probePreset = selectedProbes[index];
      setMultiProbeProgress(
        `Running ${probePreset.label} (${index + 1}/${selectedProbes.length})...`,
      );
      // eslint-disable-next-line no-await-in-loop
      const result = await runTracerouteProbe(target, probePreset);
      nextResults[probePreset.key] = result;
      setMultiProbeResults({ ...nextResults });
    }

    setMultiProbeRunning(false);
    setMultiProbeProgress("Multi-probe run complete.");
  };

  const handlePolicyRun = async () => {
    if (!target.trim()) {
      setError("Please enter a hostname or IP before running policy detection.");
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

  const comparisonProbeKeys = probePresets
    .map(probePreset => probePreset.key)
    .filter(probeKey => multiProbeResults[probeKey]);

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
                  }
                }}
              />
              <label htmlFor="multi-probe-toggle" className="font-medium">
                Run multi-probe
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
          <div className="grid gap-2 rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-900 sm:grid-cols-2 lg:grid-cols-3">
            {probePresets.map(probePreset => (
              <label key={probePreset.key} className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={!!multiProbeSelections[probePreset.key]}
                  onChange={(event) =>
                    setMultiProbeSelections(prev => ({
                      ...prev,
                      [probePreset.key]: event.target.checked,
                    }))
                  }
                  disabled={multiProbeRunning}
                />
                <span>{probePreset.label}</span>
              </label>
            ))}
          </div>
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

      {viewMode === "traceroute" && multiProbeEnabled && comparisonProbeKeys.length > 0 && (
        <div className="mt-8 space-y-4">
          <h2 className="text-lg font-semibold">Comparison</h2>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {comparisonProbeKeys.map(probeKey => {
                      const summary = comparison.perProbeSummary[probeKey];
                      const label = probeLabelMap[probeKey] ?? probeKey;
                      const status = summary?.reachedDestination ? "Reached" : "Not reached";
              return (
                <div
                  key={probeKey}
                  className="rounded border border-slate-200 bg-white p-3 text-sm shadow-sm"
                >
                  <div className="font-semibold">{label}</div>
                  {summary?.error ? (
                    <div className="text-xs text-red-600 mt-1">Error: {summary.error}</div>
                  ) : (
                    <>
                      <div className="text-xs text-slate-600 mt-1">Destination: {status}</div>
                      <div className="text-xs text-slate-600">
                        First silent hop: {summary?.firstSilentHop ?? "None"}
                      </div>
                      <div className="text-xs text-slate-600">
                        Last responding hop: {summary?.lastRespondingHop ?? "None"}
                      </div>
                      <div className="text-xs text-slate-600">
                        Responded: {summary?.respondedCount ?? 0}/{summary?.totalHops ?? 0}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>

          <div className="rounded border border-slate-200 bg-slate-50 p-3">
            <div className="font-semibold mb-2 text-sm">Insights</div>
            {comparison.insights.length > 0 ? (
              <ul className="list-disc pl-5 text-sm text-slate-700 space-y-1">
                {comparison.insights.map((insight, index) => (
                  <li key={`${insight.title}-${index}`}>
                    <span className="font-semibold">{insight.title}:</span> {insight.detail}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-xs text-slate-500">No multi-probe insights yet.</div>
            )}
          </div>

          <div className="overflow-x-auto rounded border border-slate-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-100 text-slate-700">
                <tr>
                  <th className="px-3 py-2 text-left">Hop</th>
                  {comparisonProbeKeys.map(probeKey => (
                    <th key={probeKey} className="px-3 py-2 text-left">
                      {probeLabelMap[probeKey] ?? probeKey}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.hopMatrix.map(row => (
                  <tr key={row.hop} className="border-t border-slate-200">
                    <td className="px-3 py-2 font-medium">{row.hop}</td>
                    {comparisonProbeKeys.map(probeKey => {
                      const cell = row.cells[probeKey];
                      const summary = comparison.perProbeSummary[probeKey];
                      const targetForProbe = multiProbeResults[probeKey]?.target ?? "";
                      const isFirstSilentHop =
                        summary?.firstSilentHop != null && summary.firstSilentHop === row.hop;
                      if (!cell) {
                        return (
                          <td
                            key={`${probeKey}-${row.hop}`}
                            className="px-3 py-2 text-slate-400"
                          >
                            —
                          </td>
                        );
                      }
                      const classification = classifyHop(cell, targetForProbe);
                      const responded = classification.flags.responded;
                      const cellLabel = responded ? `${cell.ip} (${cell.latency})` : "—";
                      return (
                        <td
                          key={`${probeKey}-${row.hop}`}
                          className={`px-3 py-2 ${isFirstSilentHop ? "bg-amber-50" : ""}`}
                        >
                          <div className={responded ? "text-slate-900" : "text-slate-400"}>
                            {cellLabel}
                          </div>
                          {isFirstSilentHop && (
                            <div className="text-[10px] uppercase text-amber-600">
                              Silence starts
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
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
