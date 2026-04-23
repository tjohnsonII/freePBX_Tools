export type DayStatus = "not_started" | "in_progress" | "done" | "blocked";

export type DayPlan = {
  day: number;
  week: number;
  title: string;
  tasks: string[];
  status: DayStatus;
  notes: string;
};