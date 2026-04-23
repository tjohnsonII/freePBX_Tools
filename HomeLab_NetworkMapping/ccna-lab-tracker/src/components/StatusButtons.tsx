import type { DayStatus } from "@/lib/types";

type StatusButtonsProps = {
  onChange: (status: DayStatus) => void;
};

export default function StatusButtons({ onChange }: StatusButtonsProps) {
  return (
    <div className="flex flex-wrap gap-2 mb-3">
      <button
        type="button"
        onClick={() => onChange("not_started")}
        className="px-3 py-1 rounded bg-gray-700"
      >
        Not Started
      </button>
      <button
        type="button"
        onClick={() => onChange("in_progress")}
        className="px-3 py-1 rounded bg-blue-700"
      >
        In Progress
      </button>
      <button
        type="button"
        onClick={() => onChange("done")}
        className="px-3 py-1 rounded bg-green-700"
      >
        Done
      </button>
      <button
        type="button"
        onClick={() => onChange("blocked")}
        className="px-3 py-1 rounded bg-red-700"
      >
        Blocked
      </button>
    </div>
  );
}