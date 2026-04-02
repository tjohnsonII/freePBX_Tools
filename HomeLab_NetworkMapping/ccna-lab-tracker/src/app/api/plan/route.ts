import { NextResponse } from "next/server";
import { getAllProgress, upsertProgress, type ProgressRow } from "@/lib/db";
import type { DayStatus } from "@/lib/types";

export async function GET() {
  try {
    const rows = getAllProgress();
    return NextResponse.json(rows);
  } catch (err) {
    console.error("GET /api/plan failed:", err);
    return NextResponse.json([], { status: 500 });
  }
}

export async function PUT(request: Request) {
  try {
    const body = await request.json();

    if (!Array.isArray(body)) {
      return NextResponse.json({ error: "Expected an array" }, { status: 400 });
    }

    const rows: ProgressRow[] = body
      .filter(
        (item): item is { day: number; status: DayStatus; notes: string } =>
          typeof item === "object" &&
          item !== null &&
          typeof item.day === "number" &&
          typeof item.status === "string" &&
          typeof item.notes === "string"
      )
      .map((item) => ({
        day: item.day,
        status: item.status as DayStatus,
        notes: item.notes,
      }));

    upsertProgress(rows);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("PUT /api/plan failed:", err);
    return NextResponse.json({ error: "Failed to save" }, { status: 500 });
  }
}