import Database from "better-sqlite3";
import path from "path";
import type { DayStatus } from "@/lib/types";

const DB_PATH = path.join(process.cwd(), "ccna-plan.db");

let db: Database.Database;

function getDb(): Database.Database {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma("journal_mode = WAL");
    db.exec(`
      CREATE TABLE IF NOT EXISTS plan_progress (
        day   INTEGER PRIMARY KEY,
        status TEXT    NOT NULL DEFAULT 'not_started',
        notes  TEXT    NOT NULL DEFAULT ''
      )
    `);
  }
  return db;
}

export type ProgressRow = {
  day: number;
  status: DayStatus;
  notes: string;
};

export function getAllProgress(): ProgressRow[] {
  return getDb()
    .prepare("SELECT day, status, notes FROM plan_progress ORDER BY day")
    .all() as ProgressRow[];
}

export function upsertProgress(rows: ProgressRow[]): void {
  const stmt = getDb().prepare(
    "INSERT INTO plan_progress (day, status, notes) VALUES (@day, @status, @notes) ON CONFLICT(day) DO UPDATE SET status = @status, notes = @notes"
  );
  const upsertMany = getDb().transaction((items: ProgressRow[]) => {
    for (const item of items) stmt.run(item);
  });
  upsertMany(rows);
}