"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet } from "../lib/api";

type Handle = {
  handle: string;
  last_scrape_utc?: string;
  last_status?: string;
  ticket_count?: number;
  last_ticket_utc?: string;
};

export default function HandlesPage() {
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<Handle[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Handle[]>(`/handles?search=${encodeURIComponent(search)}&limit=100`)
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, [search]);

  return (
    <main>
      <input placeholder="Search handles" value={search} onChange={(e) => setSearch(e.target.value)} />
      {error && <p>{error}</p>}
      <table>
        <thead>
          <tr><th>Handle</th><th>Tickets</th><th>Last Ticket</th><th>Last Scrape</th><th>Status</th></tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.handle}>
              <td><Link href={`/handles/${encodeURIComponent(h.handle)}`}>{h.handle}</Link></td>
              <td>{h.ticket_count ?? 0}</td>
              <td>{h.last_ticket_utc || "-"}</td>
              <td>{h.last_scrape_utc || "-"}</td>
              <td>{h.last_status || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
