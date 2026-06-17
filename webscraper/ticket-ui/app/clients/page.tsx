"use client";

import { useEffect, useState } from "react";
import { apiGet } from "../../lib/api";
import styles from "./clients.module.css";

type ClientHeartbeat = {
  client_id: string;
  status: string;
  vpn_connected: number;   // SQLite stores as 0/1
  vpn_ip: string | null;
  job_id: string | null;
  current_handle: string | null;
  handles_done: number | null;
  handles_total: number | null;
  last_seen_utc: string;
  first_seen_utc: string;
};

function secondsAgo(utc: string): number {
  return Math.floor((Date.now() - new Date(utc + (utc.endsWith("Z") ? "" : "Z")).getTime()) / 1000);
}

function relativeTime(utc: string): string {
  const s = secondsAgo(utc);
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function isStale(utc: string): boolean {
  return secondsAgo(utc) > 120;   // no heartbeat for 2+ minutes
}

export default function ClientsPage() {
  const [clients, setClients] = useState<ClientHeartbeat[]>([]);
  const [error, setError]     = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const data = await apiGet<{ items: ClientHeartbeat[] }>("/api/clients");
      setClients(data.items ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Scraper Clients</h1>

      {error && <p className={styles.error}>{error}</p>}
      {loading && <p className={styles.loading}>Loading…</p>}

      {!loading && clients.length === 0 && (
        <p className={styles.empty}>
          No clients have checked in yet. Start the Scrape Manager app on a laptop to see it here.
        </p>
      )}

      <div className={styles.grid}>
        {clients.map((c) => {
          const stale    = isStale(c.last_seen_utc);
          const vpnOn    = c.vpn_connected === 1;
          const progress = c.handles_done != null && c.handles_total != null && c.handles_total > 0
            ? Math.round((c.handles_done / c.handles_total) * 100)
            : null;

          return (
            <div key={c.client_id} className={`${styles.card} ${stale ? styles.stale : ""}`}>
              {/* Card header */}
              <div className={styles.cardHeader}>
                <span className={styles.clientId}>{c.client_id}</span>
                <span className={`${styles.statusBadge} ${styles["status_" + c.status]}`}>
                  {c.status}
                </span>
              </div>

              {/* VPN row */}
              <div className={styles.row}>
                <span className={`${styles.vpnDot} ${vpnOn ? styles.vpnOn : styles.vpnOff}`}>
                  ●
                </span>
                <span className={styles.rowLabel}>VPN</span>
                <span className={styles.rowValue}>
                  {vpnOn ? (c.vpn_ip ?? "connected") : "disconnected"}
                </span>
              </div>

              {/* Progress row */}
              {progress !== null && (
                <div className={styles.row}>
                  <span className={styles.rowLabel}>Progress</span>
                  <div className={styles.progressWrap}>
                    <div className={styles.progressBar} style={{ width: `${progress}%` }} />
                  </div>
                  <span className={styles.rowValue}>
                    {c.handles_done}/{c.handles_total} ({progress}%)
                  </span>
                </div>
              )}

              {/* Current handle */}
              {c.current_handle && (
                <div className={styles.row}>
                  <span className={styles.rowLabel}>Handle</span>
                  <span className={styles.rowValue}>{c.current_handle}</span>
                </div>
              )}

              {/* Job ID */}
              {c.job_id && (
                <div className={styles.row}>
                  <span className={styles.rowLabel}>Job</span>
                  <span className={`${styles.rowValue} ${styles.mono}`}>{c.job_id.slice(0, 8)}…</span>
                </div>
              )}

              {/* Last seen */}
              <div className={`${styles.row} ${styles.lastSeen} ${stale ? styles.staleText : ""}`}>
                {stale ? "⚠ " : ""}Last seen {relativeTime(c.last_seen_utc)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
