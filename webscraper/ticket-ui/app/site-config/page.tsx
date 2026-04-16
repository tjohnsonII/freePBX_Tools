"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, ApiRequestError } from "../../lib/api";
import styles from "./site-config.module.css";

type SiteConfig = {
  handle: string;
  vpbx_id: string;
  detail_url: string;
  site_config: string;
  last_seen_utc: string;
};

type VpbxRecord = {
  handle: string;
  name: string;
  account_status: string;
};

export default function SiteConfigPage() {
  // ── Loaded data ────────────────────────────────────────────────────────────
  const [vpbxRecords, setVpbxRecords] = useState<VpbxRecord[]>([]);
  const [siteConfigs, setSiteConfigs] = useState<SiteConfig[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  // ── Handle selection + config display ─────────────────────────────────────
  const [selectedHandle, setSelectedHandle] = useState<string>("");
  const [handleFilter, setHandleFilter] = useState<string>("");
  const [siteConfigRaw, setSiteConfigRaw] = useState<string | null>(null);
  const [siteConfigLoading, setSiteConfigLoading] = useState(false);
  const [siteConfigError, setSiteConfigError] = useState<string | null>(null);
  const [siteConfigMeta, setSiteConfigMeta] = useState<SiteConfig | null>(null);

  // ── Scrape job state ───────────────────────────────────────────────────────
  const [scraping, setScraping] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);

  // Load all vpbx records + existing site configs on mount
  const loadData = async () => {
    setDataLoading(true);
    setDataError(null);
    try {
      const [vpbxRes, scRes] = await Promise.all([
        apiGet<{ items: VpbxRecord[] }>("/api/vpbx/records"),
        apiGet<{ items: SiteConfig[] }>("/api/vpbx/site-configs"),
      ]);
      setVpbxRecords(Array.isArray(vpbxRes?.items) ? vpbxRes.items : []);
      setSiteConfigs(Array.isArray(scRes?.items) ? scRes.items : []);
    } catch (e) {
      setDataError(e instanceof Error ? e.message : String(e));
    } finally {
      setDataLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  // Build a map for quick lookup: handle → SiteConfig
  const siteConfigMap = useMemo(() => {
    const m: Record<string, SiteConfig> = {};
    for (const sc of siteConfigs) m[sc.handle.toUpperCase()] = sc;
    return m;
  }, [siteConfigs]);

  // Build a map: handle → VpbxRecord
  const vpbxMap = useMemo(() => {
    const m: Record<string, VpbxRecord> = {};
    for (const r of vpbxRecords) m[r.handle.toUpperCase()] = r;
    return m;
  }, [vpbxRecords]);

  // Sorted unique handles from vpbx records (handles known to the system)
  const allHandles = useMemo(
    () => [...vpbxRecords].sort((a, b) => a.handle.localeCompare(b.handle)),
    [vpbxRecords]
  );

  const filteredHandles = useMemo(() => {
    const q = handleFilter.trim().toUpperCase();
    if (!q) return allHandles;
    return allHandles.filter(
      (r) => r.handle.toUpperCase().includes(q) || r.name.toUpperCase().includes(q)
    );
  }, [allHandles, handleFilter]);

  // Load site config for a selected handle
  const loadSiteConfig = async (handle: string) => {
    if (!handle) return;
    setSiteConfigLoading(true);
    setSiteConfigError(null);
    setSiteConfigRaw(null);
    setSiteConfigMeta(null);
    try {
      const data = await apiGet<SiteConfig>(`/api/vpbx/site-configs/${handle}`);
      setSiteConfigRaw(data.site_config || "");
      setSiteConfigMeta(data);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 404) {
        // Not yet scraped — show empty state
        setSiteConfigRaw(null);
      } else {
        setSiteConfigError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setSiteConfigLoading(false);
    }
  };

  const handleSelectHandle = (handle: string) => {
    setSelectedHandle(handle);
    setScrapeStatus(null);
    setScrapeError(null);
    loadSiteConfig(handle);
  };

  // Poll a job until done/error
  const pollJob = async (
    job_id: string,
    onStatus?: (msg: string) => void,
  ): Promise<void> => {
    for (let i = 0; i < 600; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const [job, evts] = await Promise.all([
        apiGet<{ current_state: string; error_message?: string }>(`/api/jobs/${job_id}`),
        apiGet<{ events: { message: string }[] }>(`/api/jobs/${job_id}/events?limit=1`).catch(() => ({ events: [] })),
      ]);
      if (onStatus && evts.events.length > 0) {
        onStatus(evts.events[0].message.replace(/^vpbx[^:]*:/, "").trim());
      }
      if (job.current_state === "done") return;
      if (job.current_state === "error") {
        throw new Error(job.error_message || "Scrape job failed");
      }
    }
    throw new Error("Timed out waiting for scrape job");
  };

  const handleRefresh = async (handle: string) => {
    setScraping(true);
    setScrapeError(null);
    setScrapeStatus(`Starting scrape for ${handle}…`);
    try {
      const { job_id } = await apiPost<{ job_id: string }>(
        "/api/vpbx/site-configs/refresh",
        { handles: [handle] }
      );
      await pollJob(job_id, (msg) => setScrapeStatus(msg));
      setScrapeStatus(`Done — site config updated for ${handle}.`);
      await loadData();
      await loadSiteConfig(handle);
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
      setScrapeStatus(null);
    } finally {
      setScraping(false);
    }
  };

  const handleScrapeAll = async () => {
    setScraping(true);
    setScrapeError(null);
    setScrapeStatus("Scraping all site configs — this will take a while…");
    try {
      const { job_id } = await apiPost<{ job_id: string }>(
        "/api/vpbx/site-configs/refresh",
        {}
      );
      await pollJob(job_id, (msg) => setScrapeStatus(msg));
      setScrapeStatus("Done — all site configs updated.");
      await loadData();
      if (selectedHandle) await loadSiteConfig(selectedHandle);
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
      setScrapeStatus(null);
    } finally {
      setScraping(false);
    }
  };

  const selectedVpbx = selectedHandle ? vpbxMap[selectedHandle.toUpperCase()] : null;

  return (
    <main className={styles.main}>
      {/* ── Header + scrape all ──────────────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.headerRow}>
          <h2 className={styles.title}>
            Site Config
            {siteConfigs.length > 0 && (
              <span className={styles.count}> — {siteConfigs.length} handles scraped</span>
            )}
          </h2>
          <div className={styles.controls}>
            <button
              type="button"
              className={styles.refreshBtn}
              onClick={handleScrapeAll}
              disabled={scraping}
            >
              {scraping ? "Waiting for browser…" : "Scrape All Site Configs"}
            </button>
          </div>
        </div>
        {scrapeStatus && <p className={styles.subtle}>↻ {scrapeStatus}</p>}
        {scrapeError && <p className={styles.error}>{scrapeError}</p>}
        {!scrapeStatus && !scrapeError && (
          <p className={styles.subtle}>
            Select a handle from the list below to view its site-specific config. Use &ldquo;Scrape All&rdquo; to fetch every handle, or use the per-handle refresh button.
          </p>
        )}
        {dataError && <p className={styles.error}>{dataError}</p>}
      </section>

      <div className={styles.layout}>
        {/* ── Handle list ───────────────────────────────────────────────── */}
        <section className={`${styles.section} ${styles.handleList}`}>
          <div className={styles.headerRow}>
            <h3 className={styles.subtitle}>Handles</h3>
          </div>
          <input
            type="search"
            className={styles.searchInput}
            placeholder="Filter handles…"
            value={handleFilter}
            onChange={(e) => setHandleFilter(e.target.value)}
          />
          {dataLoading && <p className={styles.subtle}>Loading…</p>}
          {!dataLoading && allHandles.length === 0 && (
            <p className={styles.subtle}>No VPBX records found. Scrape VPBX first.</p>
          )}
          <ul className={styles.handleUl}>
            {filteredHandles.map((r) => {
              const hasConfig = Boolean(siteConfigMap[r.handle.toUpperCase()]);
              return (
                <li
                  key={r.handle}
                  className={`${styles.handleItem} ${selectedHandle === r.handle ? styles.handleItemSelected : ""}`}
                  onClick={() => handleSelectHandle(r.handle)}
                  title={r.name}
                >
                  <span className={styles.handleCode}>{r.handle}</span>
                  <span className={styles.handleName}>{r.name || "—"}</span>
                  {hasConfig && <span className={styles.configBadge}>✓</span>}
                </li>
              );
            })}
            {filteredHandles.length === 0 && !dataLoading && (
              <li className={styles.emptyItem}>No handles match.</li>
            )}
          </ul>
        </section>

        {/* ── Config viewer ─────────────────────────────────────────────── */}
        <section className={`${styles.section} ${styles.configViewer}`}>
          {!selectedHandle && (
            <p className={styles.emptyState}>Select a handle on the left to view its site config.</p>
          )}

          {selectedHandle && (
            <>
              {/* Metadata bar */}
              <div className={styles.metaBar}>
                <div className={styles.metaGroup}>
                  <span className={styles.metaLabel}>Handle</span>
                  <span className={styles.metaValue}>{selectedHandle}</span>
                </div>
                {selectedVpbx && (
                  <>
                    <div className={styles.metaGroup}>
                      <span className={styles.metaLabel}>Company</span>
                      <span className={styles.metaValue}>{selectedVpbx.name || "—"}</span>
                    </div>
                    <div className={styles.metaGroup}>
                      <span className={styles.metaLabel}>Status</span>
                      <span className={
                        selectedVpbx.account_status.toLowerCase().includes("active")
                          ? styles.statusActive
                          : styles.statusOther
                      }>
                        {selectedVpbx.account_status || "—"}
                      </span>
                    </div>
                  </>
                )}
                {siteConfigMeta && (
                  <div className={styles.metaGroup}>
                    <span className={styles.metaLabel}>Last Scraped</span>
                    <span className={styles.metaMono}>
                      {siteConfigMeta.last_seen_utc ? siteConfigMeta.last_seen_utc.slice(0, 19).replace("T", " ") : "—"}
                    </span>
                  </div>
                )}
                <button
                  type="button"
                  className={styles.refreshBtn}
                  onClick={() => handleRefresh(selectedHandle)}
                  disabled={scraping}
                  style={{ marginLeft: "auto" }}
                >
                  {scraping ? "Waiting…" : "Refresh Site Config"}
                </button>
              </div>

              <h3 className={styles.configLabel}>Site Config</h3>

              {siteConfigLoading && <p className={styles.subtle}>Loading site config…</p>}
              {siteConfigError && <p className={styles.error}>{siteConfigError}</p>}

              {!siteConfigLoading && !siteConfigError && siteConfigRaw === null && (
                <div className={styles.emptyConfig}>
                  <p>No site config scraped yet for <strong>{selectedHandle}</strong>.</p>
                  <button
                    type="button"
                    className={styles.refreshBtn}
                    onClick={() => handleRefresh(selectedHandle)}
                    disabled={scraping}
                  >
                    {scraping ? "Waiting for browser…" : "Scrape Site Config Now"}
                  </button>
                </div>
              )}

              {!siteConfigLoading && !siteConfigError && siteConfigRaw !== null && (
                <textarea
                  className={styles.configTextarea}
                  readOnly
                  value={siteConfigRaw || "(empty config returned)"}
                  rows={30}
                  spellCheck={false}
                />
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}