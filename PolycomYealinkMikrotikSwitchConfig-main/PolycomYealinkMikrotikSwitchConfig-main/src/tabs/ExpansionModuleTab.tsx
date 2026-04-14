import React, { useEffect, useState } from 'react';
import styles from './ExpansionModuleTab.module.css';
import { EXP_TYPE_ICONS, EXP_TYPE_TOOLTIPS, POLYCOM_PAGE_LABELS, POLYCOM_KEYS_PER_PAGE } from '../constants/expansionModule';

const SCRAPER_BASE = 'http://localhost:8788';

type VpbxRecord = { handle: string; name: string; account_status: string };
type DeviceConfig = {
  device_id: string; vpbx_id: string; handle: string;
  directory_name: string; extension: string; mac: string;
  make: string; model: string;
  device_properties: string; arbitrary_attributes: string;
  bulk_config: string; view_config: string; sidecar_config: string;
};

interface PolycomSection {
  address: string;
  label: string;
  type: string;
  linekeyCategory: string;
  linekeyIndex: string;
  activePage: number;
}

const ExpansionModuleTab: React.FC = () => {
  // ── Webscraper load panel state ─────────────────────────────────────────────
  const [scraperOnline, setScraperOnline] = useState<boolean | null>(null);
  const [handles, setHandles] = useState<VpbxRecord[]>([]);
  const [selectedHandle, setSelectedHandle] = useState('');
  const [devices, setDevices] = useState<DeviceConfig[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [selectedVpbxId, setSelectedVpbxId] = useState('');
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [savedSidecar, setSavedSidecar] = useState('');    // what's stored in DB
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [scraping, setScraping] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${SCRAPER_BASE}/api/vpbx/records`, { signal: AbortSignal.timeout(4000) })
      .then(r => r.json())
      .then(d => {
        setScraperOnline(true);
        setHandles((d?.items || []).sort((a: VpbxRecord, b: VpbxRecord) => a.handle.localeCompare(b.handle)));
      })
      .catch(() => setScraperOnline(false));
  }, []);

  async function handleSelectHandle(handle: string) {
    setSelectedHandle(handle);
    setSelectedDeviceId('');
    setSelectedVpbxId('');
    setDevices([]);
    setSavedSidecar('');
    if (!handle) return;
    setDevicesLoading(true);
    try {
      const res = await fetch(`${SCRAPER_BASE}/api/vpbx/device-configs?handle=${encodeURIComponent(handle)}`);
      const data = await res.json();
      setDevices((data?.items || []).sort((a: DeviceConfig, b: DeviceConfig) =>
        (a.directory_name || a.device_id).localeCompare(b.directory_name || b.device_id)
      ));
    } catch { /* ignore */ }
    setDevicesLoading(false);
  }

  function handleSelectDevice(deviceId: string) {
    setSelectedDeviceId(deviceId);
    const dev = devices.find(d => d.device_id === deviceId);
    setSelectedVpbxId(dev?.vpbx_id || '');
    setSavedSidecar(dev?.sidecar_config || '');
    setSaveStatus(null);
    // Pre-fill PBX IP from device_properties if available
    if (dev?.device_properties) {
      const ipMatch = dev.device_properties.match(/device\.ip[_\s]*address[^\n]*=\s*(\S+)/i)
        || dev.device_properties.match(/device\.[^\n]*=\s*([\d.]+)\s*$/m);
      if (ipMatch) setYealinkSection(s => ({ ...s, pbxIp: ipMatch[1] }));
    }
  }

  async function scrapeCurrentHandle() {
    if (!selectedHandle || scraping) return;
    setScraping(true);
    setScrapeStatus(`Scraping ${selectedHandle}…`);
    try {
      const res = await fetch(`${SCRAPER_BASE}/api/vpbx/device-configs/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ handles: [selectedHandle] }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { job_id } = await res.json();
      let failures = 0;
      while (true) {
        await new Promise(r => setTimeout(r, 1500));
        try {
          const jr = await fetch(`${SCRAPER_BASE}/api/jobs/${job_id}`);
          if (!jr.ok) { failures++; if (failures > 5) break; continue; }
          failures = 0;
          const job = await jr.json();
          const last = job?.events?.slice(-1)[0]?.message || '';
          setScrapeStatus(`Scraping ${selectedHandle}… ${last}`);
          if (job.status === 'complete' || job.status === 'error') break;
        } catch { failures++; if (failures > 5) break; }
      }
      setScrapeStatus(`Done — reloading ${selectedHandle}…`);
      // Reload devices WITHOUT clearing current selection
      const res2 = await fetch(`${SCRAPER_BASE}/api/vpbx/device-configs?handle=${encodeURIComponent(selectedHandle)}`);
      const data = await res2.json();
      const refreshed = (data?.items || []).sort((a: DeviceConfig, b: DeviceConfig) =>
        (a.directory_name || a.device_id).localeCompare(b.directory_name || b.device_id)
      );
      setDevices(refreshed);
      // Re-apply selected device so the "Current Scraped Config" panel updates
      if (selectedDeviceId) {
        const dev = refreshed.find((d: DeviceConfig) => d.device_id === selectedDeviceId);
        if (dev) setSavedSidecar(dev.sidecar_config || '');
      }
      setScrapeStatus(`✓ ${selectedHandle} scrape complete`);
    } catch (e) {
      setScrapeStatus(`✗ Failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setScraping(false);
    }
  }

  async function saveSidecarConfig() {
    if (!selectedDeviceId || !selectedVpbxId) return;
    setSaveStatus('Saving…');
    try {
      const res = await fetch(
        `${SCRAPER_BASE}/api/vpbx/device-configs/${encodeURIComponent(selectedDeviceId)}/sidecar`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ vpbx_id: selectedVpbxId, sidecar_config: sidecarConfig }),
        }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSavedSidecar(sidecarConfig);
      setSaveStatus('✓ Saved');
    } catch (e) {
      setSaveStatus(`✗ ${e instanceof Error ? e.message : 'Save failed'}`);
    }
  }

  // ── Polycom state ────────────────────────────────────────────────────────────
  const [polycomSection, setPolycomSection] = useState<PolycomSection>({
    address: '', label: '', type: 'automata',
    linekeyCategory: 'BLF', linekeyIndex: '', activePage: 0,
  });
  const [polycomOutput, setPolycomOutput] = useState('');

  // ── Yealink state ────────────────────────────────────────────────────────────
  const [yealinkSection, setYealinkSection] = useState({
    templateType: 'BLF', sidecarPage: '1', sidecarLine: '1',
    label: '', value: '', pbxIp: '',
  });
  // Full accumulated sidecar config (editable textarea)
  const [sidecarConfig, setSidecarConfig] = useState('');
  // Single-key preview output
  const [yealinkOutput, setYealinkOutput] = useState('');

  const generateYealinkExpansion = () => {
    const { templateType, sidecarPage, sidecarLine, label, value, pbxIp } = yealinkSection;
    let snippet = '';
    const prefix = `expansion_module.${sidecarPage}.key.${sidecarLine}`;
    if (templateType === 'BLF') {
      snippet += `${prefix}.type=16\n`;
      snippet += `${prefix}.value=${value}@${pbxIp}\n`;
      snippet += `${prefix}.line=1\n`;
      if (label) snippet += `${prefix}.label=${label}\n`;
    } else {
      snippet += `${prefix}.type=13\n`;
      snippet += `${prefix}.value=${value}\n`;
      snippet += `${prefix}.line=1\n`;
      if (label) snippet += `${prefix}.label=${label}\n`;
    }
    setYealinkOutput(snippet);
    // Append to the full sidecar config, replacing any existing entry for same page.key
    setSidecarConfig(prev => {
      const keyPrefix = `expansion_module.${sidecarPage}.key.${sidecarLine}.`;
      const lines = prev ? prev.split('\n').filter(l => !l.startsWith(keyPrefix)) : [];
      return [...lines, ...snippet.trimEnd().split('\n')].join('\n');
    });
  };

  // Generate Polycom expansion config string based on form state
  const generatePolycomExpansion = () => {
    const { address, label, type, linekeyCategory, linekeyIndex } = polycomSection;
    let config = '';
    config += `attendant.resourcelist.${linekeyIndex}.address=${address}\n`;
    config += `attendant.resourcelist.${linekeyIndex}.label=${label}\n`;
    config += `attendant.resourcelist.${linekeyIndex}.type=${type}\n`;
    config += `linekey.${linekeyIndex}.category=${linekeyCategory}\n`;
    config += `linekey.${linekeyIndex}.index=${linekeyIndex}\n`;
    setPolycomOutput(config);
  };

  return (
    <div>

      {/* ── Webscraper Load Panel ──────────────────────────────────────────── */}
      <div className={styles.scraperPanel}>
        <div className={styles.scraperHeader}>
          <span className={styles.scraperTitle}>Load from Webscraper</span>
          <span className={scraperOnline === null ? styles.badgeChecking : scraperOnline ? styles.badgeOnline : styles.badgeOffline}>
            {scraperOnline === null ? 'checking…' : scraperOnline ? '● connected' : '○ offline'}
          </span>
        </div>
        <div className={styles.scraperSelectors}>
          <div>
            <label className={styles.scraperLabel}>Handle</label>
            <select className={styles.scraperSelect}
              title="Select company handle"
              value={selectedHandle}
              onChange={e => handleSelectHandle(e.target.value)}
              disabled={!scraperOnline}
            >
              <option value="">— select handle —</option>
              {handles.map(h => (
                <option key={h.handle} value={h.handle}>{h.handle} — {h.name || 'unknown'}</option>
              ))}
            </select>
          </div>
          {selectedHandle && (
            <div>
              <label className={styles.scraperLabel} htmlFor="exp-device-select">
                Device {devicesLoading && <span className={styles.scraperNote}>Loading…</span>}
              </label>
              <select className={styles.scraperSelect}
                id="exp-device-select"
                title="Select device"
                value={selectedDeviceId}
                onChange={e => handleSelectDevice(e.target.value)}
                disabled={devicesLoading || devices.length === 0}
              >
                <option value="">— select device —</option>
                {devices.map(d => (
                  <option key={d.device_id} value={d.device_id}>
                    {d.directory_name || d.device_id}
                    {d.extension ? ` (ext ${d.extension})` : ''}
                    {d.model ? ` [${d.model}]` : ''}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* ── Scrape button + status ─────────────────────────────────────── */}
        {selectedHandle && (
          <div className={`${styles.scraperSelectors} ${styles.scrapeRow}`}>
            <button
              type="button"
              className={styles.saveBtn}
              onClick={scrapeCurrentHandle}
              disabled={scraping || !scraperOnline}
              title={`Re-scrape all devices for ${selectedHandle}`}
            >
              {scraping ? 'Scraping…' : `Scrape ${selectedHandle}`}
            </button>
            {scrapeStatus && <span className={styles.saveStatus}>{scrapeStatus}</span>}
          </div>
        )}

        {/* ── Current scraped config (read-only) ────────────────────────── */}
        {selectedDeviceId && (() => {
          const dev = devices.find(d => d.device_id === selectedDeviceId);
          const _ph = new Set(['place holder text', 'placeholder text', 'placeholder']);
          const _pick = (s: string) => s && !_ph.has(s.trim().toLowerCase()) ? s : '';
          const cfg = dev ? (_pick(dev.arbitrary_attributes) || _pick(dev.view_config) || _pick(dev.bulk_config) || _pick(dev.device_properties) || '') : '';
          const isIncomplete = !cfg || cfg.split('\n').filter(l => l.trim()).length <= 1;
          return (
            <div className={styles.sidecarSection}>
              <div className={styles.sidecarRow}>
                <span className={styles.sidecarSectionTitle}>
                  Current Scraped Config
                  {isIncomplete && <span className={styles.incompleteNote}>
                    — incomplete · click Scrape {selectedHandle} above to refresh
                  </span>}
                </span>
              </div>
              <textarea
                className={styles.sidecarTextarea}
                readOnly
                rows={8}
                value={cfg || '(no config captured yet — scrape this handle to populate)'}
                spellCheck={false}
                aria-label="Current scraped phone config"
              />
            </div>
          );
        })()}

        {selectedDeviceId && (
          <div className={styles.sidecarSection}>
            <div className={styles.sidecarRow}>
              <span className={styles.sidecarSectionTitle}>Full Sidecar Config</span>
              <div className={styles.sidecarActions}>
                {savedSidecar && (
                  <button type="button" className={styles.loadBtn}
                    onClick={() => setSidecarConfig(savedSidecar)}
                    title="Load saved sidecar config into the editor below"
                  >↓ Load Saved</button>
                )}
                <button type="button" className={styles.saveBtn}
                  onClick={saveSidecarConfig}
                  disabled={!sidecarConfig}
                  title="Save the current sidecar config to the webscraper database for this device"
                >Save to DB</button>
                {saveStatus && <span className={styles.saveStatus}>{saveStatus}</span>}
              </div>
            </div>
            {savedSidecar && savedSidecar !== sidecarConfig && (
              <p className={styles.savedNote}>
                Saved version differs from current editor content. Click "Load Saved" to restore, or "Save to DB" to overwrite.
              </p>
            )}
            <textarea
              className={styles.sidecarTextarea}
              value={sidecarConfig}
              onChange={e => setSidecarConfig(e.target.value)}
              rows={12}
              spellCheck={false}
              placeholder="Generate keys below and they'll accumulate here — or paste a full sidecar config to edit."
            />
          </div>
        )}
      </div>

      <div className={styles.columns}>
        {/* Yealink Expansion Module */}
        <div className={styles.column}>
          <h3>Yealink Expansion Module</h3>
          <img src="/expansion/yealinkexp40.jpeg" alt="Yealink EXP40" className={styles.deviceImg} />
          <img src="/expansion/yealinkexp50.jpeg" alt="Yealink EXP50" className={styles.deviceImg} />
          <div className={styles.instructions}>
            <b>Instructions:</b> Fill out the form below to generate a config for a Yealink expansion key. Each generated key is appended to the Full Sidecar Config above. Hover over any key in the preview for details.
          </div>
          <div className={styles.formGroup}>
            <label>Template Type: <span className={styles.infoIcon} title="BLF: monitors extension status. SpeedDial: dials a number.">ℹ️</span></label>
            <select title="Template type" value={yealinkSection.templateType} onChange={e => setYealinkSection(s => ({ ...s, templateType: e.target.value }))}>
              <option value="BLF">BLF</option>
              <option value="SpeedDial">SpeedDial</option>
            </select>
          </div>
          <div className={styles.formGroup}>
            <label>Sidecar Page (1-3): <span className={styles.infoIcon} title="Which page of the expansion module (1-3).">ℹ️</span></label>
            <input title="Sidecar page number (1-3)" type="number" min="1" max="3" value={yealinkSection.sidecarPage} onChange={e => setYealinkSection(s => ({ ...s, sidecarPage: e.target.value }))} />
          </div>
          <div className={styles.formGroup}>
            <label>Sidecar Line (1-20): <span className={styles.infoIcon} title="Which button (1-20) on the current page.">ℹ️</span></label>
            <input title="Sidecar line number (1-20)" type="number" min="1" max="20" value={yealinkSection.sidecarLine} onChange={e => setYealinkSection(s => ({ ...s, sidecarLine: e.target.value }))} />
          </div>
          <div className={styles.formGroup}>
            <label>Label: <span className={styles.infoIcon} title="Display label on the phone.">ℹ️</span></label>
            <input title="Button label text" type="text" value={yealinkSection.label} onChange={e => setYealinkSection(s => ({ ...s, label: e.target.value }))} />
          </div>
          <div className={styles.formGroup}>
            <label>Value (Phone/Ext): <span className={styles.infoIcon} title="Extension or number this key dials or monitors.">ℹ️</span></label>
            <input title="Extension or phone number" type="text" value={yealinkSection.value} onChange={e => setYealinkSection(s => ({ ...s, value: e.target.value }))} />
          </div>
          {yealinkSection.templateType === 'BLF' && (
            <div className={styles.formGroup}>
              <label>PBX IP: <span className={styles.infoIcon} title="PBX IP address for BLF monitoring.">ℹ️</span></label>
              <input title="PBX IP address" type="text" value={yealinkSection.pbxIp} onChange={e => setYealinkSection(s => ({ ...s, pbxIp: e.target.value }))} />
            </div>
          )}
          <button type="button" className={styles.generateBtn} onClick={generateYealinkExpansion}>Generate Yealink Expansion Config</button>
          <div className={styles.outputArea}>
            <textarea className={styles.outputTextarea} aria-label="Generated Yealink expansion config" value={yealinkOutput} readOnly rows={6} />
          </div>
          <div className={styles.previewBox}>
            <div className={styles.previewLabel}>
              <b>Preview:</b> Page
              {[1,2,3].map(page => (
                <button
                  key={page}
                  type="button"
                  className={yealinkSection.sidecarPage === String(page) ? styles.pageToggleActive : styles.pageToggleInactive}
                  onClick={() => setYealinkSection(s => ({ ...s, sidecarPage: String(page) }))}
                >{page}</button>
              ))}
            </div>
            <div className={styles.keyGrid}>
              {Array.from({ length: 20 }).map((_, idx) => {
                const isCurrent = parseInt(yealinkSection.sidecarLine) === idx + 1;
                const label = isCurrent ? yealinkSection.label : '';
                const value = isCurrent ? yealinkSection.value : '';
                const type = isCurrent ? yealinkSection.templateType : '';
                const icon = EXP_TYPE_ICONS[type || 'default'];
                const tooltip = label ? `Line: ${idx + 1}\nType: ${type}\nLabel: ${label}\nValue: ${value}` : 'Empty';
                const cellClass = `${styles.keyCell} ${type === 'BLF' ? styles.keyCellBLF : type === 'SpeedDial' ? styles.keyCellSpeedDial : ''}`;
                return (
                  <div key={idx} className={cellClass} title={tooltip}>
                    <span className={styles.keyIcon} title={EXP_TYPE_TOOLTIPS[type || 'default']}>{icon}</span>
                    <div>{label || <span className={styles.emptyLabel}>Empty</span>}</div>
                    <div className={styles.keyValue}>{value}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Polycom Expansion Module */}
        <div className={styles.column}>
          <h3>Polycom VVX Color Expansion Module</h3>
          <img src="/expansion/polycomVVX_Color_Exp_Module_2201.jpeg" alt="Polycom VVX Color Expansion Module" className={styles.deviceImg} />
          <div className={styles.instructions}>
            <b>Instructions:</b> Fill out the form below to generate a config for a Polycom expansion key.<br />
            <b>Linekey Index:</b> Keys 1–28 = Page 1, 29–56 = Page 2, 57–84 = Page 3.
          </div>
          <div className={styles.formGroup}>
            <label>Linekey Index (1-84): <span className={styles.infoIcon} title="Key position (1-84).">ℹ️</span></label>
            <input title="Linekey index (1-84)" type="number" min="1" max="84" value={polycomSection.linekeyIndex} onChange={e => setPolycomSection(s => ({ ...s, linekeyIndex: e.target.value }))} />
          </div>
          <div className={styles.formGroup}>
            <label>Address (e.g. 1001@ip): <span className={styles.infoIcon} title="SIP address for this key.">ℹ️</span></label>
            <input title="SIP address (e.g. 1001@ip)" type="text" value={polycomSection.address} onChange={e => setPolycomSection(s => ({ ...s, address: e.target.value }))} />
          </div>
          <div className={styles.formGroup}>
            <label>Label: <span className={styles.infoIcon} title="Display label on the phone.">ℹ️</span></label>
            <input title="Button label text" type="text" value={polycomSection.label} onChange={e => setPolycomSection(s => ({ ...s, label: e.target.value }))} />
          </div>
          <div className={styles.formGroup}>
            <label>Type: <span className={styles.infoIcon} title="automata = BLF, normal = speed dial.">ℹ️</span></label>
            <input title="Key type (automata or normal)" type="text" value={polycomSection.type} onChange={e => setPolycomSection(s => ({ ...s, type: e.target.value }))} />
          </div>
          <div className={styles.formGroup}>
            <label>Linekey Category: <span className={styles.infoIcon} title="BLF, EFK, etc.">ℹ️</span></label>
            <input title="Linekey category (BLF, EFK, etc.)" type="text" value={polycomSection.linekeyCategory} onChange={e => setPolycomSection(s => ({ ...s, linekeyCategory: e.target.value }))} />
          </div>
          <button type="button" className={styles.generateBtn} onClick={generatePolycomExpansion}>Generate Polycom Expansion Config</button>
          <div className={styles.outputArea}>
            <textarea className={styles.outputTextarea} aria-label="Generated Polycom expansion config" value={polycomOutput} readOnly rows={6} />
          </div>
          <div className={styles.previewBox}>
            <div className={styles.previewLabel}>
              <b>Preview:</b>
              {POLYCOM_PAGE_LABELS.map((label, i) => (
                <button
                  key={label}
                  type="button"
                  className={polycomSection.activePage === i ? styles.pageToggleActive : styles.pageToggleInactive}
                  onClick={() => setPolycomSection(s => ({ ...s, activePage: i }))}
                >{label}</button>
              ))}
            </div>
            <div className={styles.keyGrid}>
              {Array.from({ length: POLYCOM_KEYS_PER_PAGE }).map((_, idx) => {
                const globalIdx = polycomSection.activePage * POLYCOM_KEYS_PER_PAGE + idx + 1;
                const isCurrent = parseInt(polycomSection.linekeyIndex) === globalIdx;
                const label = isCurrent ? polycomSection.label : '';
                const value = isCurrent ? polycomSection.address : '';
                const type = isCurrent ? polycomSection.type : '';
                const icon = EXP_TYPE_ICONS[type === 'automata' ? 'BLF' : type === 'normal' ? 'SpeedDial' : 'default'];
                const tooltip = label ? `Index: ${globalIdx}\nType: ${type}\nLabel: ${label}\nValue: ${value}` : 'Empty';
                const cellClass = `${styles.keyCell} ${type === 'automata' ? styles.keyCellBLF : type === 'normal' ? styles.keyCellSpeedDial : ''}`;
                return (
                  <div key={idx} className={cellClass} title={tooltip}>
                    <span className={styles.keyIcon} title={EXP_TYPE_TOOLTIPS[type === 'automata' ? 'BLF' : type === 'normal' ? 'SpeedDial' : 'default']}>{icon}</span>
                    <div>{label || <span className={styles.emptyLabel}>Empty</span>}</div>
                    <div className={styles.keyValue}>{value}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExpansionModuleTab;
