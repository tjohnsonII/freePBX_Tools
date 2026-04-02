import type { DayPlan, DayStatus } from "@/lib/types";
import NotesBox from "@/components/NotesBox";
import StatusButtons from "@/components/StatusButtons";

type DayCardProps = {
  item: DayPlan;
  onStatusChange: (status: DayStatus) => void;
  onNotesChange: (notes: string) => void;
};

export default function DayCard({
  item,
  onStatusChange,
  onNotesChange,
}: DayCardProps) {
  return (
    <div className="border border-gray-700 rounded-lg p-4">
      <h3 className="text-xl font-semibold mb-2">
        Day {item.day}: {item.title}
      </h3>

      <ul className="list-disc ml-6 mb-3">
        {item.tasks.map((task, i) => (
          <li key={i}>{task}</li>
        ))}
      </ul>

      <StatusButtons onChange={onStatusChange} />

      <div className="mb-3">
        <span className="font-medium">Status:</span> {item.status}
      </div>

      <NotesBox value={item.notes} onChange={onNotesChange} />
    </div>
  );
}