type EvidenceActionsProps = {
  onCopySummary: () => void;
  onExportJson: () => void;
  onToggleCompact: () => void;
  compactEnabled: boolean;
  copyStatus: "idle" | "copied" | "error";
  disabled?: boolean;
};

export default function EvidenceActions({
  onCopySummary,
  onExportJson,
  onToggleCompact,
  compactEnabled,
  copyStatus,
  disabled,
}: EvidenceActionsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={onCopySummary}
        disabled={disabled}
        className="rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white shadow-sm disabled:opacity-60"
      >
        Copy summary
      </button>
      <button
        type="button"
        onClick={onExportJson}
        disabled={disabled}
        className="rounded border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm disabled:opacity-60"
      >
        Export JSON
      </button>
      <button
        type="button"
        onClick={onToggleCompact}
        className="rounded border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm"
      >
        {compactEnabled ? "Exit screenshot view" : "Screenshot helper"}
      </button>
      {copyStatus === "copied" && (
        <span className="text-xs text-emerald-600">Summary copied.</span>
      )}
      {copyStatus === "error" && (
        <span className="text-xs text-red-600">Copy failed.</span>
      )}
      {compactEnabled && (
        <span className="text-xs text-slate-500">
          Compact view enabled for screenshots/print.
        </span>
      )}
    </div>
  );
}
