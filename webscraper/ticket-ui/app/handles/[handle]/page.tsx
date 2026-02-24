"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet } from "../../../lib/api";

type Ticket = { ticket_id: string; title?: string; status?: string; created_utc?: string; updated_utc?: string; ticket_url?: string };
type TicketResponse = { items: Ticket[] };
type HandleLatest = { handle: string; status?: string; error_message?: string; finished_utc?: string; artifacts_hint?: string };

export default function HandleDetailPage({ params }: { params: { handle: string } }) {
  const handle = decodeURIComponent(params.handle);
  const [meta, setMeta] = useState<HandleLatest | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);

  useEffect(() => {
    apiGet<HandleLatest>(`/api/handles/${encodeURIComponent(handle)}/latest`).then(setMeta).catch(() => setMeta(null));
    apiGet<TicketResponse>(`/api/handles/${encodeURIComponent(handle)}/tickets?status=any&limit=200`).then((res) => setTickets(res.items)).catch(() => setTickets([]));
  }, [handle]);

  return (
    <main>
      <h2>{handle}</h2>
      <p>Status: {meta?.status || "-"} | Error: {meta?.error_message || "-"} | Last Updated: {meta?.finished_utc || "-"}</p>
      <p>Artifacts Hint: <code>{meta?.artifacts_hint || "-"}</code></p>
      {tickets.length === 0 ? <p>No tickets in DB for this handle.</p> : null}
      <table>
        <thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Created</th><th>Updated</th><th>URL</th></tr></thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.ticket_id}>
              <td><Link href={`/tickets/${encodeURIComponent(t.ticket_id)}?handle=${encodeURIComponent(handle)}`}>{t.ticket_id}</Link></td>
              <td>{t.title || "-"}</td>
              <td>{t.status || "-"}</td>
              <td>{t.created_utc || "-"}</td>
              <td>{t.updated_utc || "-"}</td>
              <td>{t.ticket_url ? <a href={t.ticket_url} target="_blank">link</a> : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
