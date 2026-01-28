import { ScenarioDefinition, ScenarioId } from "../utils/policyDetection";

type ScenarioPickerProps = {
  scenarios: ScenarioDefinition[];
  selectedScenarioId: ScenarioId;
  onSelect: (scenarioId: ScenarioId) => void;
  disabled?: boolean;
  rtpPortsInput: string;
  onRtpPortsInputChange: (value: string) => void;
  rtpPortsError?: string;
};

export default function ScenarioPicker({
  scenarios,
  selectedScenarioId,
  onSelect,
  disabled,
  rtpPortsInput,
  onRtpPortsInputChange,
  rtpPortsError,
}: ScenarioPickerProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {scenarios.map(scenario => {
        const isSelected = scenario.id === selectedScenarioId;
        return (
          <button
            key={scenario.id}
            type="button"
            onClick={() => onSelect(scenario.id)}
            disabled={disabled}
            className={`flex flex-col gap-2 rounded border p-3 text-left text-sm shadow-sm transition ${
              isSelected
                ? "border-blue-400 bg-blue-50"
                : "border-slate-200 bg-white hover:border-blue-300"
            } ${disabled ? "opacity-70 cursor-not-allowed" : ""}`}
          >
            <div className="font-semibold">{scenario.title}</div>
            <div className="text-xs text-slate-600">{scenario.description}</div>
            <div className="text-xs text-slate-500">
              Probes: {scenario.probes.map(probe => probe.label).join(", ")}
            </div>
            {scenario.id === "rtp-range" && isSelected && (
              <div className="mt-2 space-y-1">
                <label className="text-xs font-medium text-slate-700">
                  RTP ports (comma-separated)
                </label>
                <input
                  type="text"
                  value={rtpPortsInput}
                  onChange={event => onRtpPortsInputChange(event.target.value)}
                  className="w-full rounded border border-slate-200 px-2 py-1 text-xs"
                  placeholder="10000, 12000, 20000"
                />
                {rtpPortsError && (
                  <div className="text-[11px] text-red-600">{rtpPortsError}</div>
                )}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
