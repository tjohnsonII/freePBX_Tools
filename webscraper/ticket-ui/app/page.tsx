"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import HandleDropdown from "./components/HandleDropdown";
import { apiGet, apiPost } from "../lib/api";

type HandleSummary = {
  handle: string;
  last_scrape_utc?: string;
  ticket_count: number;
  open_count: number;
  updated_latest_utc?: string;
};

type Ticket = {
  ticket_id: string;
  title?: string;
  status?: string;
  updated_utc?: string;
  created_utc?: string;
};

type TicketResponse = {
  items: Ticket[];
  totalCount: number;
  page: number;
  pageSize: number;
};

type ScrapeStatus = {
  jobId: string;
  status: string;
  handle: string;
  mode: "latest" | "full";
  logs: string[];
  progress: { completed: number; total: number };
  error?: string;
};

export default function HandlesPage() {
  const router = useRouter();
  const pathname = usePathname();

  const [handleFilter, setHandleFilter] = useState("");
  const [rows, setRows] = useState<HandleSummary[]>([]);
  const [offset, setOffset] = useState(0);
  const [hasMoreHandles, setHasMoreHandles] = useState(true);
  const [selectedHandle, setSelectedHandle] = useState("");
  const [selectedHandles, setSelectedHandles] = useState<Set<string>>(new Set());
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<ScrapeStatus[]>([]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const handleFromUrl = new URLSearchParams(window.location.search).get("handle") || "";
    if (handleFromUrl) {
      setSelectedHandle(handleFromUrl);
    }
  }, []);

  const fetchHandlePage = async (query: string, nextOffset: number, replace: boolean) => {
    try {
      setError(null);
      const list = await apiGet<HandleSummary[]>(
        `/api/handles/summary?q=${encodeURIComponent(query)}&limit=100&offset=${nextOffset}`,
      );
      setHasMoreHandles(list.length === 100);
      setOffset(nextOffset + list.length);
      setRows((prev) => (replace ? list : [...prev, ...list]));
      if (!selectedHandle && list.length > 0) {
        setSelectedHandle(list[0].handle);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
      setHasMoreHandles(false);
    }
  };

  useEffect(() => {
    fetchHandlePage(handleFilter, 0, true);
  }, [handleFilter]);

  useEffect(() => {
    if (!selectedHandle) {
      setTickets([]);
      return;
    }

    const nextParams = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
    nextParams.set("handle", selectedHandle);
    router.replace(`${pathname}?${nextParams.toString()}`);

    apiGet<TicketResponse>(`/api/tickets?handle=${encodeURIComponent(selectedHandle)}&page=1&pageSize=100&sort=newest`)
      .then((res) => {
        setError(null);
        setTickets(res.items);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setTickets([]);
      });
  }, [selectedHandle, pathname, router]);

  useEffect(() => {
    const activeJobs = jobs.filter((job) => job.status !== "completed" && job.status !== "failed");
    if (!activeJobs.length) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const updates = await Promise.all(activeJobs.map((job) => apiGet<ScrapeStatus>(`/api/scrape/${job.jobId}`)));
        setJobs((prev) => prev.map((existing) => updates.find((item) => item.jobId === existing.jobId) || existing));
      } catch (e) {
        setScrapeError(e instanceof Error ? e.message : String(e));
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [jobs]);

  const selectedSummary = useMemo(() => rows.find((row) => row.handle === selectedHandle), [rows, selectedHandle]);

  const toggleHandleSelection = (handle: string) => {
    setSelectedHandles((prev) => {
      const next = new Set(prev);
      if (next.has(handle)) {
        next.delete(handle);
      } else {
        next.add(handle);
      }
      return next;
    });
  };

  const startSingleScrape = async (mode: "latest" | "full") => {
    if (!selectedHandle) {
      setScrapeError("Select a handle first.");
      return;
    }
    try {
      setScrapeError(null);
      const payload = await apiPost<{ jobId: string; status: string }>("/api/scrape", {
        handle: selectedHandle,
        mode,
        limit: mode === "latest" ? 20 : undefined,
      });
      const status = await apiGet<ScrapeStatus>(`/api/scrape/${payload.jobId}`);
      setJobs((prev) => [status, ...prev]);
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
    }
  };

  const startBatchScrape = async (mode: "latest" | "full", scrapeAll: boolean) => {
    try {
      setScrapeError(null);
      const handles = scrapeAll ? null : Array.from(selectedHandles);
      const payload = await apiPost<{ jobIds: string[]; status: string }>("/api/scrape-batch", {
        handles,
        mode,
        limit: mode === "latest" ? 20 : undefined,
      });
      const statuses = await Promise.all(payload.jobIds.map((jobId) => apiGet<ScrapeStatus>(`/api/scrape/${jobId}`)));
      setJobs((prev) => [...statuses, ...prev]);
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <main>
      <h1>Ticket History</h1>

      <HandleDropdown
        rows={rows}
        selectedHandle={selectedHandle}
        search={handleFilter}
        onSearchChange={setHandleFilter}
        onSelect={setSelectedHandle}
      />

      {selectedSummary && (
        <p>
          Summary: {selectedSummary.ticket_count} tickets, {selectedSummary.open_count} open, last scrape {selectedSummary.last_scrape_utc || "-"},
          latest update {selectedSummary.updated_latest_utc || "-"}
        </p>
      )}

      <div>
        <button disabled={!selectedHandle} onClick={() => startSingleScrape("latest")}>Scrape latest</button>
        <button disabled={!selectedHandle} onClick={() => startSingleScrape("full")}>Scrape full</button>
        <button disabled={!selectedHandles.size} onClick={() => startBatchScrape("latest", false)}>Scrape latest (selected)</button>
        <button onClick={() => startBatchScrape("latest", true)}>Scrape latest (all)</button>
      </div>

      {hasMoreHandles && <button onClick={() => fetchHandlePage(handleFilter, offset, false)}>Load more handles</button>}

      {error && <p>{error}</p>}
      {scrapeError && <p>{scrapeError}</p>}

      <h2>Handle selection for batch scrape</h2>
      <ul>
        {rows.map((row) => (
          <li key={`batch-${row.handle}`}>
            <label>
              <input
                type="checkbox"
                checked={selectedHandles.has(row.handle)}
                onChange={() => toggleHandleSelection(row.handle)}
              />
              {row.handle} ({row.ticket_count})
            </label>
          </li>
        ))}
      </ul>

      {jobs.map((job) => (
        <div key={job.jobId}>
          <p>
            Job {job.jobId}: {job.status} ({job.progress.completed}/{job.progress.total}) for {job.handle} [{job.mode}]
          </p>
          {job.error && <p>{job.error}</p>}
          {job.logs?.length ? <pre>{job.logs.slice(-10).join("\n")}</pre> : null}
        </div>
      ))}

      <h2>{selectedHandle ? `Tickets for ${selectedHandle}` : "Select a handle"}</h2>
      <table>
        <thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Updated</th><th>Created</th></tr></thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={`${t.ticket_id}-${t.updated_utc}-${selectedHandle}`}>
              <td>{t.ticket_id}</td>
              <td>{t.title || "-"}</td>
              <td>{t.status || "-"}</td>
              <td>{t.updated_utc || "-"}</td>
              <td>{t.created_utc || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
