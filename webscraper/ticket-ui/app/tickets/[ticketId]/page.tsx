"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiGet, artifactLink } from "../../../lib/api";

type Artifact = { artifact_type: string; path: string };
type Ticket = {
  ticket_id: string;
  handle: string;
  title?: string;
  status?: string;
  raw_json?: string;
  artifacts?: Artifact[];
};

export default function TicketDetailPage({ params }: { params: { ticketId: string } }) {
  const ticketId = decodeURIComponent(params.ticketId);
  const search = useSearchParams();
  const handle = search.get("handle") || "";
  const [ticket, setTicket] = useState<Ticket | null>(null);

  useEffect(() => {
    apiGet<Ticket>(`/tickets/${encodeURIComponent(ticketId)}?handle=${encodeURIComponent(handle)}`)
      .then(setTicket)
      .catch(() => setTicket(null));
  }, [ticketId, handle]);

  return (
    <main>
      <h2>Ticket {ticketId}</h2>
      <p>Handle: {ticket?.handle || handle} | Status: {ticket?.status || "-"}</p>
      <h3>Artifacts</h3>
      <ul>
        {(ticket?.artifacts || []).map((a) => (
          <li key={`${a.path}-${a.artifact_type}`}>
            <a href={artifactLink(a.path)} target="_blank">{a.artifact_type}: {a.path}</a>
          </li>
        ))}
      </ul>
      <h3>Raw JSON</h3>
      <pre>{ticket?.raw_json ? JSON.stringify(JSON.parse(ticket.raw_json), null, 2) : "No data"}</pre>
    </main>
  );
}
