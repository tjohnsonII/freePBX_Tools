import type { DayPlan, DayStatus } from "@/lib/types";
import DayCard from "@/components/DayCard";

type WeekSectionProps = {
  week: number;
  days: DayPlan[];
  onStatusChange: (day: number, status: DayStatus) => void;
  onNotesChange: (day: number, notes: string) => void;
};

export default function WeekSection({
  week,
  days,
  onStatusChange,
  onNotesChange,
}: WeekSectionProps) {
  return (
    <section>
      <h2 className="text-2xl font-semibold mb-4 border-b border-gray-800 pb-2">
        Week {week}
      </h2>

      <div className="space-y-4">
        {days.map((item) => (
          <DayCard
            key={item.day}
            item={item}
            onStatusChange={(status) => onStatusChange(item.day, status)}
            onNotesChange={(notes) => onNotesChange(item.day, notes)}
          />
        ))}
      </div>
    </section>
  );
}