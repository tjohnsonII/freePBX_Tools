"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet } from "../../../lib/api";

type Ticket = {
  ticket_id: string;
  title?: string;
  status?: string;
  created_utc?: string;
  updated_utc?: string;
  ticket_url?: string;
};

type TicketResponse = {
  items: Ticket[];
};

type Handle = {
  handle: string;
  last_scrape_utc?: string;
  last_status?: string;
};

export default function HandleDetailPage({ params }: { params: { handle: string } }) {
  const handle = decodeURIComponent(params.handle);
  const [meta, setMeta] = useState<Handle | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    apiGet<Handle>(`/api/handles/${encodeURIComponent(handle)}`).then(setMeta).catch(() => setMeta(null));
  }, [handle]);

  useEffect(() => {
    const path = `/handles/${encodeURIComponent(handle)}/tickets?status=${encodeURIComponent(status)}&q=${encodeURIComponent(q)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&limit=200`;
    apiGet<TicketResponse>(`/api${path}`).then((res) => setTickets(res.items)).catch(() => setTickets([]));
  }, [handle, q, status, from, to]);

  return (
    <main>
      <h2>{handle}</h2>
      <p>Last scrape: {meta?.last_scrape_utc || "-"} | Status: {meta?.last_status || "-"}</p>
      <div>
        <input placeholder="keyword" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="ticket_detail">ticket_detail</option>
          <option value="open">open</option>
          <option value="closed">closed</option>
        </select>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
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
