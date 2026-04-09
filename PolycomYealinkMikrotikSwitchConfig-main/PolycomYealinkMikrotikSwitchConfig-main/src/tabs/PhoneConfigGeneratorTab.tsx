import React, { useEffect, useState } from 'react';
import styles from './PhoneConfigGeneratorTab.module.css';

const SCRAPER_BASE = 'http://localhost:8788';

type VpbxRecord = { handle: string; name: string; account_status: string };
type DeviceConfig = {
  device_id: string;
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
type SiteConfig = {
  handle: string;
  site_config: string;
  last_seen_utc: string;
};

const PLACEHOLDER_STRINGS = new Set(['place holder text', 'placeholder text', 'placeholder']);
function isPlaceholder(s: string): boolean {
  return PLACEHOLDER_STRINGS.has(s.trim().toLowerCase());
}

function bestConfig(d: DeviceConfig): string {
  const candidates = [d.view_config, d.arbitrary_attributes, d.bulk_config];
  for (const c of candidates) {
    if (c && !isPlaceholder(c)) return c;
  }
  return '';
}

export default function PhoneConfigGeneratorTab() {
  const [scraperOnline, setScraperOnline] = useState<boolean | null>(null);
  const [handles, setHandles] = useState<VpbxRecord[]>([]);
  const [selectedHandle, setSelectedHandle] = useState('');
  const [devices, setDevices] = useState<DeviceConfig[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [siteConfig, setSiteConfig] = useState<SiteConfig | null>(null);
  const [siteLoading, setSiteLoading] = useState(false);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${SCRAPER_BASE}/api/vpbx/records`, { signal: AbortSignal.timeout(4000) })
      .then(r => r.json())
      .then(data => {
        setScraperOnline(true);
        const items: VpbxRecord[] = data?.items || [];
        setHandles(items.sort((a, b) => a.handle.localeCompare(b.handle)));
      })
      .catch(() => setScraperOnline(false));
  }, []);

  async function handleSelectHandle(handle: string) {
    setSelectedHandle(handle);
    setSelectedDeviceId('');
    setDevices([]);
    setSiteConfig(null);
    setError(null);
    if (!handle) return;

    setSiteLoading(true);
    setDevicesLoading(true);

    const [siteRes, devRes] = await Promise.allSettled([
      fetch(`${SCRAPER_BASE}/api/vpbx/site-configs/${encodeURIComponent(handle)}`),
      fetch(`${SCRAPER_BASE}/api/vpbx/device-configs?handle=${encodeURIComponent(handle)}`),
    ]);

    if (siteRes.status === 'fulfilled' && siteRes.value.ok) {
      try { setSiteConfig(await siteRes.value.json()); } catch { /* ignore */ }
    }
    setSiteLoading(false);

    if (devRes.status === 'fulfilled' && devRes.value.ok) {
      try {
        const data = await devRes.value.json();
        setDevices((data?.items || []).sort((a: DeviceConfig, b: DeviceConfig) =>
          (a.directory_name || a.device_id).localeCompare(b.directory_name || b.device_id)
        ));
      } catch { setError('Failed to parse device configs'); }
    } else {
      setError('Failed to load devices for this handle');
    }
    setDevicesLoading(false);
  }

  const selectedDevice = devices.find(d => d.device_id === selectedDeviceId) || null;
  const deviceConfig = selectedDevice ? bestConfig(selectedDevice) : null;

  const badgeClass = scraperOnline === null
    ? styles.badgeChecking
    : scraperOnline ? styles.badgeOnline : styles.badgeOffline;
  const badgeText = scraperOnline === null
    ? 'Checking connection…'
    : scraperOnline
      ? '● Webscraper connected'
      : '○ Webscraper offline — start the backend at localhost:8788';

  return (
    <div className={styles.container}>
      <h2 className={styles.heading}>Phone Config Generator</h2>
      <p className={styles.subtitle}>
        Select a company handle then a device to view the site config and per-device phone config side by side.
      </p>

      <div className={badgeClass}>{badgeText}</div>

      {/* Selectors */}
      <div className={styles.selectors}>
        <div className={styles.selectorGroup}>
          <label className={styles.selectorLabel}>Company Handle</label>
          <select
            className={styles.handleSelect}
            value={selectedHandle}
            onChange={e => handleSelectHandle(e.target.value)}
            disabled={!scraperOnline || handles.length === 0}
            title="Select company handle"
          >
            <option value="">— Select handle —</option>
            {handles.map(h => (
              <option key={h.handle} value={h.handle}>
                {h.handle} — {h.name || 'unknown'}
              </option>
            ))}
          </select>
        </div>

        {selectedHandle && (
          <div className={styles.selectorGroup}>
            <label className={styles.selectorLabel}>
              Device
              {devicesLoading && <span className={styles.selectorLabelNote}> Loading…</span>}
              {!devicesLoading && devices.length > 0 && (
                <span className={styles.selectorLabelNote}> ({devices.length} devices)</span>
              )}
            </label>
            <select
              className={styles.deviceSelect}
              value={selectedDeviceId}
              onChange={e => setSelectedDeviceId(e.target.value)}
              disabled={devicesLoading || devices.length === 0}
              title="Select device"
            >
              <option value="">— Select device —</option>
              {devices.map(d => (
                <option key={d.device_id} value={d.device_id}>
                  {d.directory_name || d.device_id}
                  {d.extension ? ` (ext ${d.extension})` : ''}
                  {d.mac ? ` — ${d.mac}` : ''}
                  {d.model ? ` [${d.model}]` : ''}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && <p className={styles.error}>✗ {error}</p>}

      {/* Config panels */}
      {selectedHandle && (
        <div className={styles.panels}>
          {/* Site Config */}
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>Site Config</span>
              {siteConfig && (
                <span className={styles.panelMeta}>
                  {handles.find(h => h.handle === selectedHandle)?.name || selectedHandle}
                  {' · scraped '}{siteConfig.last_seen_utc?.slice(0, 10) || '—'}
                </span>
              )}
            </div>
            {siteLoading && <p className={styles.panelEmpty}>Loading site config…</p>}
            {!siteLoading && !siteConfig && (
              <p className={styles.panelEmpty}>
                No site config scraped yet for <strong>{selectedHandle}</strong>.
                Scrape it from the Phone Config Scraper in the 123NET Webscraper app (port 3005).
              </p>
            )}
            {!siteLoading && siteConfig && (
              <textarea
                className={styles.panelTextarea}
                readOnly
                value={siteConfig.site_config || '(empty site config)'}
                rows={30}
                spellCheck={false}
                aria-label="Site Config"
              />
            )}
          </div>

          {/* Device Phone Config */}
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>Phone Config</span>
              {selectedDevice && (
                <span className={styles.panelMeta}>
                  {selectedDevice.directory_name || selectedDevice.device_id}
                  {selectedDevice.extension ? ` · ext ${selectedDevice.extension}` : ''}
                  {selectedDevice.mac ? ` · ${selectedDevice.mac}` : ''}
                  {selectedDevice.model ? ` · ${selectedDevice.model}` : ''}
                </span>
              )}
            </div>
            {!selectedDeviceId && (
              <p className={styles.panelEmpty}>Select a device above to view its phone config.</p>
            )}
            {selectedDeviceId && deviceConfig === '' && (
              <p className={styles.panelEmpty}>
                No config captured for this device yet. Run "Force Re-scrape All" from the Phone Config Scraper.
              </p>
            )}
            {selectedDeviceId && deviceConfig !== null && deviceConfig !== '' && (
              <textarea
                className={styles.panelTextarea}
                readOnly
                value={deviceConfig}
                rows={30}
                spellCheck={false}
                aria-label="Phone Config"
              />
            )}
          </div>
        </div>
      )}

      {/* Device Properties panel */}
      {selectedDevice?.device_properties && (
        <div className={styles.dpPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>
              Device Properties
              <span className={styles.dpHeaderNote}>(from FreePBX edit_device page)</span>
            </span>
          </div>
          <textarea
            className={styles.panelTextarea}
            readOnly
            value={selectedDevice.device_properties}
            rows={12}
            spellCheck={false}
            aria-label="Device Properties"
          />
        </div>
      )}
    </div>
  );
}
