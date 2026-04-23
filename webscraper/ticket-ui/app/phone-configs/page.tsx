"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost, ApiRequestError } from "../../lib/api";
import styles from "./phone-configs.module.css";

type DeviceConfig = {
  device_id: string;
  vpbx_id: string;
  handle: string;
  directory_name: string;
  extension: string;
  mac: string;
  make: string;
  model: string;
  site_code: string;
  device_properties: string;
  arbitrary_attributes: string;
  bulk_config: string;
  view_config: string;
  last_seen_utc: string;
};

const PLACEHOLDER_STRINGS = new Set(["place holder text", "placeholder text", "placeholder"]);
function isPlaceholder(s: string): boolean {
  return PLACEHOLDER_STRINGS.has(s.trim().toLowerCase());
}

/** Return the best available config text for a device, in priority order.
 *  Filters out known FreePBX placeholder strings. */
function bestConfig(d: DeviceConfig): string {
  const candidates = [d.view_config, d.arbitrary_attributes, d.bulk_config];
  for (const c of candidates) {
    if (c && !isPlaceholder(c)) return c;
  }
  return "";
}

type VpbxRecord = {
  handle: string;
  name: string;
  account_status: string;
};

type SiteConfig = {
  handle: string;
  vpbx_id: string;
  detail_url: string;
  site_config: string;
  last_seen_utc: string;
};

type HandleSummary = {
  handle: string;
  name: string;
  account_status: string;
  device_count: number;
  last_seen_utc: string;
};

export default function PhoneConfigsPage() {
  // ── Scraper state ─────────────────────────────────────────────────────────
  const [scrapeHandleInput, setScrapeHandleInput] = useState("");
  const [scraping, setScraping] = useState(false);
  const [forceRescraping, setForceRescraping] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState<string | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);

  // ── Summary table state ───────────────────────────────────────────────────
  const [allDevices, setAllDevices] = useState<DeviceConfig[]>([]);
  const [vpbxRecords, setVpbxRecords] = useState<VpbxRecord[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [handleFilter, setHandleFilter] = useState("");

  // ── Expanded handle state (summary table) ─────────────────────────────────
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null);
  const [expandedDevice, setExpandedDevice] = useState<string | null>(null);
  const [scrapingHandle, setScrapingHandle] = useState<string | null>(null);
  const [scrapeDeviceStatus, setScrapeDeviceStatus] = useState<string | null>(null);
  const [scrapeDeviceError, setScrapeDeviceError] = useState<string | null>(null);

  // ── Phone Config Generator state ──────────────────────────────────────────
  // selectedHandle / selectedDevice drive the generator independently from the summary table
  const [genHandle, setGenHandle] = useState<string>("");
  const [genDevice, setGenDevice] = useState<string>("");

  const [siteConfigRaw, setSiteConfigRaw] = useState<string | null>(null);
  const [siteConfigLoading, setSiteConfigLoading] = useState(false);
  const [siteConfigError, setSiteConfigError] = useState<string | null>(null);
  const [siteConfigMeta, setSiteConfigMeta] = useState<SiteConfig | null>(null);

  const [phoneConfigRaw, setPhoneConfigRaw] = useState<string | null>(null);
  const [phoneConfigLoading, setPhoneConfigLoading] = useState(false);
  const [phoneConfigError, setPhoneConfigError] = useState<string | null>(null);
  const [phoneConfigMeta, setPhoneConfigMeta] = useState<DeviceConfig | null>(null);

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollJob = async (
    job_id: string,
    label: string,
    onStatus?: (msg: string) => void,
  ): Promise<void> => {
    let consecutiveErrors = 0;
    const MAX_CONSECUTIVE_ERRORS = 15; // ~30s of 503s before giving up

    for (let i = 0; i < 3600; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const [job, evts] = await Promise.all([
          apiGet<{ current_state: string; error_message?: string }>(`/api/jobs/${job_id}`),
          apiGet<{ events: { message: string }[] }>(`/api/jobs/${job_id}/events?limit=1`).catch(() => ({ events: [] })),
        ]);
        consecutiveErrors = 0; // reset on success
        if (onStatus && evts.events.length > 0) {
          onStatus(evts.events[0].message.replace(/^vpbx[^:]*:/, "").trim());
        }
        if (job.current_state === "done") return;
        if (job.current_state === "error") {
          throw new Error(job.error_message || `${label} failed`);
        }
      } catch (e) {
        // Re-throw definitive job errors (not network/503 errors)
        if (e instanceof Error && !e.message.includes("503") && !e.message.includes("502") && !e.message.includes("fetch") && !e.message.includes("network") && !e.message.includes("unavailable")) {
          throw e;
        }
        consecutiveErrors++;
        if (onStatus) {
          onStatus(`API unavailable — retrying… (${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS})`);
        }
        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          throw new Error(`${label}: backend unreachable after ${MAX_CONSECUTIVE_ERRORS} retries. The scrape may still be running — refresh the page to check status.`);
        }
      }
    }
  };

  const loadAll = async () => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const [devRes, vpbxRes] = await Promise.all([
        apiGet<{ items: DeviceConfig[] }>("/api/vpbx/device-configs"),
        apiGet<{ items: VpbxRecord[] }>("/api/vpbx/records"),
      ]);
      setAllDevices(Array.isArray(devRes?.items) ? devRes.items : []);
      setVpbxRecords(Array.isArray(vpbxRes?.items) ? vpbxRes.items : []);
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : String(e));
    } finally {
      setSummaryLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    pollTimer.current = setInterval(() => loadAll().catch(() => undefined), 30000);
    return () => { if (pollTimer.current) clearInterval(pollTimer.current); };
  }, []);

  // Build summary rows: group device configs by handle, join company name from vpbx records
  const summaryRows = useMemo<HandleSummary[]>(() => {
    const nameMap: Record<string, VpbxRecord> = {};
    for (const r of vpbxRecords) nameMap[r.handle.toUpperCase()] = r;

    const grouped: Record<string, { devices: DeviceConfig[]; last_seen: string }> = {};
    for (const d of allDevices) {
      const key = d.handle.toUpperCase();
      if (!grouped[key]) grouped[key] = { devices: [], last_seen: "" };
      grouped[key].devices.push(d);
      if (!grouped[key].last_seen || d.last_seen_utc > grouped[key].last_seen) {
        grouped[key].last_seen = d.last_seen_utc;
      }
    }

    return Object.entries(grouped)
      .map(([key, g]) => {
        const vpbx = nameMap[key];
        return {
          handle: g.devices[0].handle,
          name: vpbx?.name || "—",
          account_status: vpbx?.account_status || "—",
          device_count: g.devices.length,
          last_seen_utc: g.last_seen,
        };
      })
      .sort((a, b) => a.handle.localeCompare(b.handle));
  }, [allDevices, vpbxRecords]);

  const filteredSummary = useMemo(() => {
    const q = handleFilter.trim().toUpperCase();
    if (!q) return summaryRows;
    return summaryRows.filter(
      (r) => r.handle.toUpperCase().includes(q) || r.name.toUpperCase().includes(q)
    );
  }, [summaryRows, handleFilter]);

  // Devices for selected handle (summary table expansion)
  const selectedDevices = useMemo(() => {
    if (!selectedHandle) return [];
    return allDevices.filter((d) => d.handle.toUpperCase() === selectedHandle.toUpperCase());
  }, [allDevices, selectedHandle]);

  // Devices for the Phone Config Generator's selected handle
  const genDevices = useMemo(() => {
    if (!genHandle) return [];
    return allDevices.filter((d) => d.handle.toUpperCase() === genHandle.toUpperCase());
  }, [allDevices, genHandle]);

  // Sorted unique handles available for the generator dropdown
  const genHandleOptions = useMemo(
    () => [...summaryRows].sort((a, b) => a.handle.localeCompare(b.handle)),
    [summaryRows]
  );

  const vpbxMap = useMemo(() => {
    const m: Record<string, VpbxRecord> = {};
    for (const r of vpbxRecords) m[r.handle.toUpperCase()] = r;
    return m;
  }, [vpbxRecords]);

  // ── Generator: handle change ───────────────────────────────────────────────
  const handleGenHandleChange = async (handle: string) => {
    setGenHandle(handle);
    // Clear device state whenever handle changes
    setGenDevice("");
    setPhoneConfigRaw(null);
    setPhoneConfigMeta(null);
    setPhoneConfigError(null);
    // Clear previous site config
    setSiteConfigRaw(null);
    setSiteConfigMeta(null);
    setSiteConfigError(null);

    if (!handle) return;

    setSiteConfigLoading(true);
    try {
      const data = await apiGet<SiteConfig>(`/api/vpbx/site-configs/${handle}`);
      setSiteConfigRaw(data.site_config || "");
      setSiteConfigMeta(data);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 404) {
        // Not yet scraped — show empty state instead of error
        setSiteConfigRaw(null);
      } else {
        setSiteConfigError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setSiteConfigLoading(false);
    }
  };

  // ── Generator: device change ───────────────────────────────────────────────
  const handleGenDeviceChange = (deviceId: string) => {
    setGenDevice(deviceId);
    setPhoneConfigError(null);
    setPhoneConfigLoading(false);

    if (!deviceId) {
      setPhoneConfigRaw(null);
      setPhoneConfigMeta(null);
      return;
    }

    // config is already loaded — no extra API call needed
    const device = allDevices.find((d) => d.device_id === deviceId);
    if (device) {
      const cfg = bestConfig(device);
      setPhoneConfigRaw(cfg || null);
      setPhoneConfigMeta(device);
    } else {
      setPhoneConfigRaw(null);
      setPhoneConfigMeta(null);
    }
  };

  const handleScrapePhoneConfigs = async () => {
    setScraping(true);
    setScrapeError(null);
    const handle = scrapeHandleInput.trim().toUpperCase() || null;
    setScrapeStatus(handle ? `Scraping ${handle}…` : "Scraping all handles — this will take a while…");
    try {
      const { job_id } = await apiPost<{ job_id: string }>(
        "/api/vpbx/device-configs/refresh",
        handle ? { handles: [handle] } : {}
      );
      await pollJob(job_id, "Phone configs", (msg) => setScrapeStatus(msg));
      setScrapeStatus(handle ? `Done — configs saved for ${handle}.` : "Done — all phone configs updated.");
      await loadAll();
      if (handle) setSelectedHandle(handle);
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
      setScrapeStatus(null);
    } finally {
      setScraping(false);
    }
  };

  const handleForceRescrapeAll = async () => {
    setForceRescraping(true);
    setScrapeError(null);
    setScrapeStatus("Force re-scraping ALL handles — ignoring existing data…");
    try {
      const { job_id } = await apiPost<{ job_id: string }>(
        "/api/vpbx/device-configs/refresh",
        { force: true }
      );
      await pollJob(job_id, "Force re-scrape", (msg) => setScrapeStatus(msg));
      setScrapeStatus("Done — all phone configs force re-scraped.");
      await loadAll();
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
      setScrapeStatus(null);
    } finally {
      setForceRescraping(false);
    }
  };

  const handleRescrapeIncomplete = async () => {
    setForceRescraping(true);
    setScrapeError(null);
    setScrapeStatus("Re-scraping devices with blank or single-line configs…");
    try {
      const { job_id } = await apiPost<{ job_id: string }>(
        "/api/vpbx/device-configs/refresh",
        { incomplete_only: true }
      );
      await pollJob(job_id, "Re-scrape incomplete", (msg) => setScrapeStatus(msg));
      setScrapeStatus("Done — incomplete configs re-scraped.");
      await loadAll();
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : String(e));
      setScrapeStatus(null);
    } finally {
      setForceRescraping(false);
    }
  };

  const handleScrapeDevices = async (handle: string) => {
    setScrapingHandle(handle);
    setScrapeDeviceError(null);
    setScrapeDeviceStatus(null);
    try {
      const { job_id } = await apiPost<{ job_id: string }>(
        "/api/vpbx/device-configs/refresh",
        { handles: [handle] }
      );
      await pollJob(job_id, `Device configs for ${handle}`, (msg) => setScrapeDeviceStatus(msg));
      await loadAll();
    } catch (e) {
      setScrapeDeviceError(e instanceof Error ? e.message : String(e));
    } finally {
      setScrapingHandle(null);
      setScrapeDeviceStatus(null);
    }
  };

  const handleSelectRow = (handle: string) => {
    if (selectedHandle === handle) {
      setSelectedHandle(null);
      setExpandedDevice(null);
    } else {
      setSelectedHandle(handle);
      setExpandedDevice(null);
    }
  };

  const genVpbx = genHandle ? vpbxMap[genHandle.toUpperCase()] : null;

  return (
    <main className={styles.main}>
      {/* ── Phone Config Scraper ─────────────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.headerRow}>
          <h2 className={styles.title}>Phone Config Scraper</h2>
          <div className={styles.controls}>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Handle (blank = all handles)"
              value={scrapeHandleInput}
              onChange={(e) => setScrapeHandleInput(e.target.value.toUpperCase())}
              disabled={scraping || forceRescraping}
            />
            <button
              type="button"
              className={styles.refreshBtn}
              onClick={handleScrapePhoneConfigs}
              disabled={scraping || forceRescraping}
            >
              {scraping ? "Waiting for browser…" : "Scrape Phone Configs"}
            </button>
            <button
              type="button"
              className={styles.forceBtn}
              onClick={handleForceRescrapeAll}
              disabled={scraping || forceRescraping}
              title="Re-scrape every device across all handles, ignoring existing data"
            >
              {forceRescraping ? "Force scraping…" : "Force Re-scrape All"}
            </button>
            <button
              type="button"
              className={styles.incompleteBtn}
              onClick={handleRescrapeIncomplete}
              disabled={scraping || forceRescraping}
              title="Re-scrape only devices with blank or single-line configs; skip devices with full configs"
            >
              {forceRescraping ? "Scraping…" : "Re-scrape Incomplete"}
            </button>
          </div>
        </div>
        {scrapeStatus && <p className={styles.subtle}>↻ {scrapeStatus}</p>}
        {scrapeError && <p className={styles.error}>{scrapeError}</p>}
        {!scrapeStatus && !scrapeError && (
          <p className={styles.subtle}>
            Enter a handle to scrape one site, or leave blank to scrape all. Click a row in the table below to view device configs.
          </p>
        )}
      </section>

      {/* ── Scraped Handles Summary ───────────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.headerRow}>
          <h2 className={styles.title}>
            Scraped Handles
            {summaryRows.length > 0 && (
              <span className={styles.count}> — {summaryRows.length} handles, {allDevices.length} devices</span>
            )}
          </h2>
          <div className={styles.controls}>
            <input
              type="search"
              className={styles.searchInput}
              placeholder="Filter by handle or name…"
              value={handleFilter}
              onChange={(e) => setHandleFilter(e.target.value)}
            />
          </div>
        </div>

        {summaryError && <p className={styles.error}>{summaryError}</p>}
        {summaryLoading && <p className={styles.subtle}>Loading…</p>}

        {!summaryLoading && summaryRows.length === 0 && (
          <p className={styles.subtle}>No phone configs scraped yet — run the scraper above to populate this table.</p>
        )}

        {!summaryLoading && summaryRows.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Handle</th>
                  <th className={styles.th}>Company</th>
                  <th className={styles.th}>Status</th>
                  <th className={styles.th}>Devices</th>
                  <th className={styles.th}>Last Scraped</th>
                </tr>
              </thead>
              <tbody>
                {filteredSummary.map((r) => (
                  <>
                    <tr
                      key={r.handle}
                      className={`${styles.row} ${selectedHandle === r.handle ? styles.rowSelected : ""}`}
                      onClick={() => handleSelectRow(r.handle)}
                      title="Click to view device configs"
                    >
                      <td className={styles.handleCell}>{r.handle}</td>
                      <td>{r.name}</td>
                      <td>
                        <span className={r.account_status.toLowerCase().includes("active") ? styles.statusActive : styles.statusOther}>
                          {r.account_status}
                        </span>
                      </td>
                      <td className={styles.mono}>{r.device_count}</td>
                      <td className={styles.mono}>{r.last_seen_utc ? r.last_seen_utc.slice(0, 10) : "—"}</td>
                    </tr>

                    {/* Inline device expansion */}
                    {selectedHandle === r.handle && (
                      <tr key={`${r.handle}-expanded`}>
                        <td colSpan={5} className={styles.expandedCell}>
                          <div className={styles.expandedHeader}>
                            <span className={styles.expandedTitle}>
                              {r.handle} — {r.name} — {selectedDevices.length} devices
                            </span>
                            <button
                              type="button"
                              className={styles.refreshBtn}
                              onClick={(e) => { e.stopPropagation(); handleScrapeDevices(r.handle); }}
                              disabled={scrapingHandle !== null}
                            >
                              {scrapingHandle === r.handle ? "Waiting for browser…" : `Re-scrape ${r.handle}`}
                            </button>
                          </div>
                          {scrapeDeviceStatus && scrapingHandle === r.handle && (
                            <p className={styles.subtle}>↻ {scrapeDeviceStatus}</p>
                          )}
                          {scrapeDeviceError && scrapingHandle === r.handle && (
                            <p className={styles.error}>{scrapeDeviceError}</p>
                          )}
                          <table className={styles.innerTable}>
                            <thead>
                              <tr>
                                <th className={styles.th}>Directory Name</th>
                                <th className={styles.th}>Extension</th>
                                <th className={styles.th}>MAC</th>
                                <th className={styles.th}>Make</th>
                                <th className={styles.th}>Model</th>
                                <th className={styles.th}>Site</th>
                                <th className={styles.th}>Config</th>
                                <th className={styles.th}>Last Seen</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedDevices.map((d) => (
                                <>
                                  <tr key={d.device_id} className={styles.innerRow}>
                                    <td>{d.directory_name || "—"}</td>
                                    <td className={styles.mono}>{d.extension || "—"}</td>
                                    <td className={styles.mono}>{d.mac || "—"}</td>
                                    <td>{d.make || "—"}</td>
                                    <td>{d.model || "—"}</td>
                                    <td className={styles.mono}>{d.site_code || "—"}</td>
                                    <td>
                                      <button
                                        type="button"
                                        className={styles.configToggleBtn}
                                        onClick={(e) => { e.stopPropagation(); setExpandedDevice(expandedDevice === d.device_id ? null : d.device_id); }}
                                      >
                                        {expandedDevice === d.device_id ? "Hide" : bestConfig(d) ? "Show config" : "No config"}
                                      </button>
                                    </td>
                                    <td className={styles.mono}>
                                      {d.last_seen_utc ? d.last_seen_utc.slice(0, 10) : "—"}
                                    </td>
                                  </tr>
                                  {expandedDevice === d.device_id && (
                                    <tr key={`${d.device_id}-config`}>
                                      <td colSpan={8} className={styles.configCell}>
                                        <pre className={styles.configPre}>
                                          {bestConfig(d) || "(no config captured)"}
                                        </pre>
                                      </td>
                                    </tr>
                                  )}
                                </>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {filteredSummary.length === 0 && (
                  <tr>
                    <td colSpan={5} className={styles.emptyCell}>No handles match the filter.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Phone Config Generator ────────────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.headerRow}>
          <h2 className={styles.title}>Phone Config Generator</h2>
          <p className={styles.generatorHint}>
            Select a handle then a device to view both the site config and the per-device phone config side by side.
          </p>
        </div>

        {/* Handle selector */}
        <div className={styles.generatorSelectors}>
          <div className={styles.selectorGroup}>
            <label className={styles.selectorLabel}>Company Handle</label>
            <select
              className={styles.selectorSelect}
              value={genHandle}
              onChange={(e) => handleGenHandleChange(e.target.value)}
              title="Select company handle"
            >
              <option value="">— Select handle —</option>
              {genHandleOptions.map((r) => (
                <option key={r.handle} value={r.handle}>
                  {r.handle} — {r.name || "unknown"}
                </option>
              ))}
            </select>
          </div>

          {genHandle && (
            <div className={styles.selectorGroup}>
              <label className={styles.selectorLabel}>Device</label>
              <select
                className={styles.selectorSelect}
                value={genDevice}
                onChange={(e) => handleGenDeviceChange(e.target.value)}
                title="Select device"
              >
                <option value="">— Select device —</option>
                {genDevices.map((d) => (
                  <option key={d.device_id} value={d.device_id}>
                    {d.directory_name || d.device_id}
                    {d.extension ? ` (ext ${d.extension})` : ""}
                    {d.mac ? ` — ${d.mac}` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {genHandle && (
          <div className={styles.configPanels}>
            {/* ── Site Config panel ──────────────────────────────────────── */}
            <div className={styles.configPanel}>
              <div className={styles.configPanelHeader}>
                <span className={styles.configPanelTitle}>Site Config</span>
                {genVpbx && (
                  <span className={styles.configPanelMeta}>
                    {genVpbx.name || genHandle}
                    {siteConfigMeta && (
                      <> &bull; scraped {siteConfigMeta.last_seen_utc?.slice(0, 10) || "—"}</>
                    )}
                  </span>
                )}
              </div>

              {siteConfigLoading && <p className={styles.subtle}>Loading site config…</p>}
              {siteConfigError && <p className={styles.error}>{siteConfigError}</p>}

              {!siteConfigLoading && !siteConfigError && siteConfigRaw === null && (
                <div className={styles.noConfig}>
                  No site config scraped yet for <strong>{genHandle}</strong>.
                  Visit the <a href="/site-config" className={styles.link}>Site Config tab</a> to scrape it.
                </div>
              )}

              {!siteConfigLoading && !siteConfigError && siteConfigRaw !== null && (
                <textarea
                  className={styles.genTextarea}
                  readOnly
                  value={siteConfigRaw || "(empty config returned)"}
                  rows={20}
                  spellCheck={false}
                  aria-label="Site Config"
                />
              )}
            </div>

            {/* ── Phone Config panel ─────────────────────────────────────── */}
            <div className={styles.configPanel}>
              <div className={styles.configPanelHeader}>
                <span className={styles.configPanelTitle}>Current Phone Config</span>
                {phoneConfigMeta && (
                  <span className={styles.configPanelMeta}>
                    {phoneConfigMeta.directory_name || phoneConfigMeta.device_id}
                    {phoneConfigMeta.extension ? ` &bull; ext ${phoneConfigMeta.extension}` : ""}
                    {phoneConfigMeta.mac ? ` &bull; ${phoneConfigMeta.mac}` : ""}
                    {phoneConfigMeta.model ? ` &bull; ${phoneConfigMeta.model}` : ""}
                    {phoneConfigMeta.last_seen_utc ? ` &bull; scraped ${phoneConfigMeta.last_seen_utc.slice(0, 10)}` : ""}
                  </span>
                )}
              </div>

              {phoneConfigLoading && <p className={styles.subtle}>Loading phone config…</p>}
              {phoneConfigError && <p className={styles.error}>{phoneConfigError}</p>}

              {!phoneConfigLoading && !phoneConfigError && !genDevice && (
                <div className={styles.noConfig}>
                  Select a device above to view its phone config.
                </div>
              )}

              {!phoneConfigLoading && !phoneConfigError && genDevice && phoneConfigRaw === null && (
                <div className={styles.noConfig}>
                  No config captured for this device. Re-scrape phone configs to populate.
                </div>
              )}

              {!phoneConfigLoading && !phoneConfigError && genDevice && phoneConfigRaw !== null && (
                <textarea
                  className={styles.genTextarea}
                  readOnly
                  value={phoneConfigRaw || "(empty config)"}
                  rows={20}
                  spellCheck={false}
                  aria-label="Current Phone Config"
                />
              )}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}