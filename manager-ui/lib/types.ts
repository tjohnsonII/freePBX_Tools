export type AnyObj = Record<string, unknown>;
export type EventItem = { timestamp: string; level: string; category: string; event_type: string; message: string; details?: AnyObj };
