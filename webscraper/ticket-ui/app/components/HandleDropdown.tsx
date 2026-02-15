"use client";

type HandleSummary = {
  handle: string;
  ticket_count: number;
  open_count: number;
  last_scrape_utc?: string;
  updated_latest_utc?: string;
};

type Props = {
  rows: HandleSummary[];
  selectedHandle: string;
  search: string;
  onSearchChange: (next: string) => void;
  onSelect: (handle: string) => void;
};

export default function HandleDropdown({ rows, selectedHandle, search, onSearchChange, onSelect }: Props) {
  return (
    <section>
      <label>
        Search handles
        <input
          value={search}
          placeholder="Filter handles..."
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </label>

      <label>
        Handle
        <select value={selectedHandle} onChange={(e) => onSelect(e.target.value)}>
          <option value="">Select a handle</option>
          {rows.map((row) => (
            <option key={row.handle} value={row.handle}>
              {row.handle} ({row.ticket_count} tickets, {row.open_count} open)
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
