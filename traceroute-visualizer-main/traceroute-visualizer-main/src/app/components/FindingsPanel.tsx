import { PolicyFinding } from "../utils/policyDetection";

type FindingsPanelProps = {
  findings: PolicyFinding[];
  confidence: "low" | "medium" | "high";
  suggestedNextSteps: string[];
};

const severityStyles: Record<PolicyFinding["severity"], string> = {
  good: "border-emerald-200 bg-emerald-50 text-emerald-900",
  warn: "border-amber-200 bg-amber-50 text-amber-900",
  bad: "border-red-200 bg-red-50 text-red-900",
};

export default function FindingsPanel({
  findings,
  confidence,
  suggestedNextSteps,
}: FindingsPanelProps) {
  return (
    <div className="space-y-3">
      <div className="rounded border border-slate-200 bg-white p-3">
        <div className="flex items-center justify-between text-sm font-semibold">
          <span>Likely policy findings</span>
          <span className="text-xs font-normal text-slate-500">
            Overall confidence: {confidence}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {findings.length > 0 ? (
            findings.map((finding, index) => (
              <div
                key={`${finding.title}-${index}`}
                className={`rounded border px-3 py-2 text-xs shadow-sm ${severityStyles[finding.severity]}`}
              >
                <div className="font-semibold">{finding.title}</div>
                <div className="opacity-80">{finding.detail}</div>
                <div className="mt-1 text-[10px] uppercase opacity-70">
                  Confidence: {finding.confidence}
                </div>
              </div>
            ))
          ) : (
            <div className="text-xs text-slate-500">No findings yet.</div>
          )}
        </div>
      </div>

      <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm">
        <div className="font-semibold mb-2">Suggested next steps</div>
        {suggestedNextSteps.length > 0 ? (
          <ul className="list-disc pl-5 text-slate-700 space-y-1">
            {suggestedNextSteps.map(step => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-slate-500">No suggested next steps yet.</div>
        )}
      </div>
    </div>
  );
}
