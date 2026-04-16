import { useEffect, useRef, useState } from 'react';
import styles from './PhoneConfigGeneratorTab.module.css';
import {
  MODEL_RULES, YEALINK_MODELS, POLYCOM_MODELS,
  type Vendor, type Target, type BuildStyle, type SourceMode,
} from '../data/modelRules';
import {
  YEALINK_STANDARD_BASE, YEALINK_DECT_BASE, YEALINK_HOLD_VOLUME,
  POLYCOM_DATE_TIME_OVERRIDE, POLYCOM_HOLD_RINGBACK,
  POLYCOM_URL_DIALING_DISABLE, POLYCOM_REMOVE_DND,
  generateYealinkParkLines, generateYealinkBLF,
  generateYealinkTransferKey, generateYealinkExternalSpeedDial,
  generatePolycomParkLines, generatePolycomBLF,
  generatePolycomSpeedDial, generatePolycomEFK,
  type EfkOptions,
} from '../data/phoneTemplates';

const SCRAPER_BASE = import.meta.env.VITE_SCRAPER_BASE || 'http://localhost:8788';

// ─── Scraper types ────────────────────────────────────────────────────────
type VpbxRecord = { handle: string; name: string; account_status: string };
type DeviceConfig = {
  device_id: string; handle: string; directory_name: string;
  extension: string; mac: string; make: string; model: string;
  site_code: string; device_properties: string; arbitrary_attributes: string;
  bulk_config: string; view_config: string; last_seen_utc: string;
};
type SiteConfig = { handle: string; site_config: string; last_seen_utc: string };

// ─── BLF / speed dial row ────────────────────────────────────────────────
interface KeyRow { keyNum: string; ext: string; label: string }
const emptyKeyRow = (): KeyRow => ({ keyNum: '', ext: '', label: '' });

// ─── Helpers ─────────────────────────────────────────────────────────────
const PLACEHOLDER_STRINGS = new Set(['place holder text', 'placeholder text', 'placeholder']);

function pickBestConfig(d: DeviceConfig): string {
  const notPlaceholder = (s: string) =>
    s && !PLACEHOLDER_STRINGS.has(s.trim().toLowerCase()) ? s : '';
  const lineCount = (s: string) => s ? s.split('\n').filter(l => l.trim()).length : 0;
  const aa = notPlaceholder(d.arbitrary_attributes);
  if (aa) return aa;
  return [d.view_config, d.bulk_config, d.device_properties]
    .map(notPlaceholder).filter(Boolean)
    .sort((a, b) => lineCount(b) - lineCount(a))[0] || '';
}

/** Try to pull PBX IP from a scraped site config or device properties. */
function extractPbxIp(siteConfig: SiteConfig | null, device: DeviceConfig | null): string {
  const sources = [
    siteConfig?.site_config,
    device?.device_properties,
    device?.arbitrary_attributes,
  ].filter(Boolean) as string[];
  for (const src of sources) {
    // Yealink: account.1.sip_server.1.address=X.X.X.X
    let m = src.match(/(?:sip_server|server)\.1\.address\s*=\s*([\d.]+)/i);
    if (m) return m[1];
    // Polycom: reg.1.server.1.address="X.X.X.X"  or  voIpProt.server.1.address="..."
    m = src.match(/(?:reg\.\d+\.server\.\d+\.address|voIpProt\.server\.1\.address)\s*=\s*"?([\d.]+)"?/i);
    if (m) return m[1];
    // Generic: serverAddress=X.X.X.X
    m = src.match(/serverAddress\s*=\s*([\d.]+)/i);
    if (m) return m[1];
  }
  return '';
}

// ─── Section wrapper ─────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      <div className={styles.sectionBody}>{children}</div>
    </div>
  );
}

// ─── Pill toggle (radio-button-style) ────────────────────────────────────
function PillGroup<T extends string>({
  value, onChange, options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className={styles.pillGroup}>
      {options.map(o => (
        <button
          key={o.value}
          type="button"
          className={`${styles.pill} ${value === o.value ? styles.pillActive : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ─── Checkbox row ────────────────────────────────────────────────────────
function CheckRow({
  checked, onChange, label, sub,
}: {
  checked: boolean; onChange: (v: boolean) => void; label: string; sub?: string;
}) {
  return (
    <label className={styles.checkRow}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      <span>
        {label}
        {sub && <span className={styles.checkSub}>{sub}</span>}
      </span>
    </label>
  );
}

// ─── Key row table (BLF / transfer / speed dial) ─────────────────────────
function KeyRowTable({
  rows, onChange, onAdd, onRemove,
  colHeaders, colPlaceholders,
}: {
  rows: KeyRow[];
  onChange: (idx: number, field: keyof KeyRow, val: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
  colHeaders: [string, string, string];
  colPlaceholders: [string, string, string];
}) {
  return (
    <div className={styles.keyTable}>
      <div className={styles.keyTableHeader}>
        <span>{colHeaders[0]}</span>
        <span>{colHeaders[1]}</span>
        <span>{colHeaders[2]}</span>
        <span />
      </div>
      {rows.map((row, i) => (
        <div key={i} className={styles.keyTableRow}>
          <input
            className={styles.keyInput}
            type="text"
            value={row.keyNum}
            placeholder={colPlaceholders[0]}
            onChange={e => onChange(i, 'keyNum', e.target.value)}
          />
          <input
            className={styles.keyInput}
            type="text"
            value={row.ext}
            placeholder={colPlaceholders[1]}
            onChange={e => onChange(i, 'ext', e.target.value)}
          />
          <input
            className={styles.keyInput}
            type="text"
            value={row.label}
            placeholder={colPlaceholders[2]}
            onChange={e => onChange(i, 'label', e.target.value)}
          />
          <button
            type="button"
            className={styles.keyRemoveBtn}
            onClick={() => onRemove(i)}
            title="Remove row"
          >✕</button>
        </div>
      ))}
      <button type="button" className={styles.addRowBtn} onClick={onAdd}>+ Add row</button>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────
export default function PhoneConfigGeneratorTab() {

  // ── Build mode ──────────────────────────────────────────────────────
  const [vendor, setVendor] = useState<Vendor>('yealink');
  const [modelKey, setModelKey] = useState('yealink|T46U');
  const [target, setTarget] = useState<Target>('phone');
  const [buildStyle, setBuildStyle] = useState<BuildStyle>('template');
  const [sourceMode, setSourceMode] = useState<SourceMode>('scratch');

  // ── Source data (manual) ─────────────────────────────────────────────
  const [pbxIp, setPbxIp] = useState('');
  const [extension, setExtension] = useState('');
  const [sipPassword, setSipPassword] = useState('');
  const [displayLabel, setDisplayLabel] = useState('');

  // ── Scraper integration ──────────────────────────────────────────────
  const [scraperOnline, setScraperOnline] = useState<boolean | null>(null);
  const [handles, setHandles] = useState<VpbxRecord[]>([]);
  const [selectedHandle, setSelectedHandle] = useState('');
  const [devices, setDevices] = useState<DeviceConfig[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [siteConfig, setSiteConfig] = useState<SiteConfig | null>(null);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState<string | null>(null);
  const [scraperError, setScraperError] = useState<string | null>(null);

  // ── Standard template options ────────────────────────────────────────
  const [includeBase, setIncludeBase] = useState(true);
  const [includeParkLines, setIncludeParkLines] = useState(true);
  const [parkLineCount, setParkLineCount] = useState(3);

  // ── Add-on modules ───────────────────────────────────────────────────
  const [addBlfKeys, setAddBlfKeys] = useState(false);
  const [blfRows, setBlfRows] = useState<KeyRow[]>([emptyKeyRow()]);

  const [addTransferHotkey, setAddTransferHotkey] = useState(false);
  const [transferRows, setTransferRows] = useState<KeyRow[]>([emptyKeyRow()]);

  const [addExternalDial, setAddExternalDial] = useState(false);
  const [externalRows, setExternalRows] = useState<KeyRow[]>([emptyKeyRow()]);

  const [addEfk, setAddEfk] = useState(false);
  const [efkOpts, setEfkOpts] = useState<EfkOptions>({
    efkIndex: 2, linekeyNum: 2,
    mname: 'Intercom', actionString: '*80$P2N4$$Tinvite$',
    promptLabel: 'Extension', promptType: 'numeric',
  });

  const [addDateTimeOverride, setAddDateTimeOverride] = useState(false);
  const [addHoldRingback, setAddHoldRingback] = useState(false);
  const [addHoldVolume, setAddHoldVolume] = useState(false);
  const [addUrlDialingDisable, setAddUrlDialingDisable] = useState(false);
  const [addRemoveDnd, setAddRemoveDnd] = useState(false);

  // ── Output ──────────────────────────────────────────────────────────
  const [output, setOutput] = useState('');
  const [copied, setCopied] = useState(false);
  const outputRef = useRef<HTMLTextAreaElement>(null);

  // ── Check scraper on mount ───────────────────────────────────────────
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

  // ── When vendor changes, reset model to first of that vendor ─────────
  function handleVendorChange(v: Vendor) {
    setVendor(v);
    const models = v === 'yealink' ? YEALINK_MODELS : POLYCOM_MODELS;
    if (models.length) setModelKey(models[0].key);
  }

  // ── Scraper: load devices for a handle ──────────────────────────────
  async function loadDevices(handle: string) {
    setDevicesLoading(true);
    setScraperError(null);
    const [siteRes, devRes] = await Promise.allSettled([
      fetch(`${SCRAPER_BASE}/api/vpbx/site-configs/${encodeURIComponent(handle)}`),
      fetch(`${SCRAPER_BASE}/api/vpbx/device-configs?handle=${encodeURIComponent(handle)}`),
    ]);
    if (siteRes.status === 'fulfilled' && siteRes.value.ok) {
      try { setSiteConfig(await siteRes.value.json()); } catch { /* ignore */ }
    }
    if (devRes.status === 'fulfilled' && devRes.value.ok) {
      try {
        const data = await devRes.value.json();
        setDevices((data?.items || []).sort((a: DeviceConfig, b: DeviceConfig) =>
          (a.directory_name || a.device_id).localeCompare(b.directory_name || b.device_id)
        ));
      } catch { setScraperError('Failed to parse device configs'); }
    } else {
      setScraperError('Failed to load devices for this handle');
    }
    setDevicesLoading(false);
  }

  async function handleSelectHandle(handle: string) {
    setSelectedHandle(handle);
    setSelectedDeviceId('');
    setDevices([]);
    setSiteConfig(null);
    setScrapeStatus(null);
    if (!handle) return;
    await loadDevices(handle);
  }

  // ── Scraper: re-scrape handle ────────────────────────────────────────
  async function handleScrapeHandle() {
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
          const jobRes = await fetch(`${SCRAPER_BASE}/api/jobs/${job_id}`);
          if (!jobRes.ok) { failures++; if (failures > 5) break; continue; }
          failures = 0;
          const job = await jobRes.json();
          const last = job?.events?.slice(-1)[0]?.message || '';
          setScrapeStatus(`Scraping… ${last}`);
          if (['done', 'complete', 'error', 'failed'].includes(job.status)) break;
        } catch { failures++; if (failures > 5) break; }
      }
      setScrapeStatus(`Done — reloading ${selectedHandle}…`);
      await loadDevices(selectedHandle);
      setScrapeStatus(`✓ Scrape complete`);
    } catch (e) {
      setScrapeStatus(`✗ Failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setScraping(false);
    }
  }

  // ── Load production device into source fields ─────────────────────
  const selectedDevice = devices.find(d => d.device_id === selectedDeviceId) || null;

  function applyScrapedDevice(device: DeviceConfig) {
    // Auto-fill extension/label from device record
    if (device.extension) setExtension(device.extension);
    if (device.directory_name) setDisplayLabel(device.directory_name);
    // Try to extract PBX IP from site config or device data
    const ip = extractPbxIp(siteConfig, device);
    if (ip) setPbxIp(ip);
  }

  useEffect(() => {
    if (selectedDevice && sourceMode === 'production') {
      applyScrapedDevice(selectedDevice);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDeviceId, sourceMode]);

  // ── Key row table helpers ─────────────────────────────────────────────
  function updateRow(
    setter: React.Dispatch<React.SetStateAction<KeyRow[]>>,
    idx: number, field: keyof KeyRow, val: string,
  ) {
    setter(rows => rows.map((r, i) => i === idx ? { ...r, [field]: val } : r));
  }

  // ── Config assembler ─────────────────────────────────────────────────
  function assemble(): string {
    const rule = MODEL_RULES[modelKey];
    if (!rule) return '';
    const parts: string[] = [];

    // ── Base ──────────────────────────────────────────────────────
    if (sourceMode === 'production' && selectedDevice) {
      const raw = pickBestConfig(selectedDevice);
      if (raw) parts.push(`# Production Config — ${selectedDevice.directory_name || selectedDevice.device_id}\n${raw}`);
    } else if (buildStyle === 'template' && includeBase) {
      if (rule.vendor === 'yealink') {
        parts.push(rule.dect ? YEALINK_DECT_BASE : YEALINK_STANDARD_BASE);
      }
      // Polycom has no single standard base template — configuration comes from
      // the site config stored in FreePBX. Only snippets are added below.
    }

    // ── Park lines ─────────────────────────────────────────────────
    const shouldAddParks =
      (buildStyle === 'template' && includeParkLines) ||
      (buildStyle === 'adhoc' && includeParkLines);

    if (shouldAddParks && !rule.dect && pbxIp && parkLineCount > 0) {
      let parkBlock = '';
      if (rule.vendor === 'yealink') {
        parkBlock = generateYealinkParkLines(parkLineCount, pbxIp, rule.parkLineStart);
      } else {
        // For sidecar target, use sidecarStartIndex; otherwise phone parkLineStart
        const start = target === 'sidecar' ? rule.sidecarStartIndex : rule.parkLineStart;
        parkBlock = generatePolycomParkLines(parkLineCount, pbxIp, start);
      }
      if (parkBlock) parts.push(`# Park Lines\n${parkBlock}`);
    }

    // ── BLF Keys ──────────────────────────────────────────────────
    if (addBlfKeys) {
      const blf = blfRows
        .filter(r => r.keyNum && r.ext)
        .map(r => {
          if (rule.vendor === 'yealink') {
            return generateYealinkBLF(Number(r.keyNum), r.ext, r.label || r.ext, pbxIp);
          } else {
            return generatePolycomBLF(Number(r.keyNum), r.ext, r.label || r.ext, pbxIp);
          }
        });
      if (blf.length) parts.push(`# BLF Keys\n${blf.join('\n')}`);
    }

    // ── Transfer Hotkeys (Yealink only) ───────────────────────────
    if (addTransferHotkey && rule.vendor === 'yealink') {
      const xfer = transferRows
        .filter(r => r.keyNum && r.ext)
        .map(r => generateYealinkTransferKey(Number(r.keyNum), r.ext, r.label || r.ext, pbxIp));
      if (xfer.length) parts.push(`# Transfer Hotkeys\n${xfer.join('\n')}`);
    }

    // ── External Speed Dial (Yealink only) ────────────────────────
    if (addExternalDial && rule.vendor === 'yealink') {
      const ext = externalRows
        .filter(r => r.keyNum && r.ext)
        .map(r => generateYealinkExternalSpeedDial(Number(r.keyNum), r.ext, r.label || r.ext));
      if (ext.length) parts.push(`# External Speed Dial\n${ext.join('\n')}`);
    }

    // ── BLF Speed Dial (Polycom only — normal type) ───────────────
    if (addExternalDial && rule.vendor === 'polycom') {
      const ext = externalRows
        .filter(r => r.keyNum && r.ext)
        .map(r => generatePolycomSpeedDial(Number(r.keyNum), r.ext, r.label || r.ext, pbxIp));
      if (ext.length) parts.push(`# Speed Dial Keys\n${ext.join('\n')}`);
    }

    // ── EFK Prompt (Polycom only) ─────────────────────────────────
    if (addEfk && rule.vendor === 'polycom') {
      parts.push(`# EFK Prompt Button\n${generatePolycomEFK(efkOpts)}`);
    }

    // ── Misc add-ons ──────────────────────────────────────────────
    if (addDateTimeOverride && rule.vendor === 'polycom') {
      parts.push(`# Date/Time Override\n${POLYCOM_DATE_TIME_OVERRIDE}`);
    }
    if (addHoldRingback && rule.vendor === 'polycom') {
      parts.push(`# Hold Ringback\n${POLYCOM_HOLD_RINGBACK}`);
    }
    if (addHoldVolume && rule.vendor === 'yealink') {
      parts.push(`# Prevent Volume Reset on Hold\n${YEALINK_HOLD_VOLUME}`);
    }
    if (addUrlDialingDisable && rule.vendor === 'polycom') {
      parts.push(`# Disable URL Dialing\n${POLYCOM_URL_DIALING_DISABLE}`);
    }
    if (addRemoveDnd && rule.vendor === 'polycom') {
      parts.push(`# Remove DND\n${POLYCOM_REMOVE_DND}`);
    }

    return parts.join('\n\n');
  }

  function handleGenerate() {
    setOutput(assemble());
    setTimeout(() => outputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  }

  async function handleCopy() {
    if (!output) return;
    await navigator.clipboard.writeText(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // ── Derived values ────────────────────────────────────────────────────
  const rule = MODEL_RULES[modelKey];
  const modelOptions = vendor === 'yealink' ? YEALINK_MODELS : POLYCOM_MODELS;
  const scraperBadgeClass = scraperOnline === null
    ? styles.badgeChecking
    : scraperOnline ? styles.badgeOnline : styles.badgeOffline;
  const scraperBadgeText = scraperOnline === null
    ? 'Checking scraper connection…'
    : scraperOnline
      ? '● Webscraper connected'
      : '○ Webscraper offline (start backend at localhost:8788)';

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className={styles.container}>
      <h2 className={styles.heading}>Phone Config Generator</h2>
      <p className={styles.subtitle}>
        Assemble production-ready FreePBX phone configurations using your team's standard templates.
      </p>

      {/* ═══ SECTION 1: Build Mode ═══════════════════════════════════════ */}
      <Section title="1 · Build Mode">
        <div className={styles.buildGrid}>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>Vendor</label>
            <PillGroup<Vendor>
              value={vendor}
              onChange={handleVendorChange}
              options={[
                { value: 'yealink', label: 'Yealink' },
                { value: 'polycom', label: 'Polycom' },
              ]}
            />
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>Model</label>
            <select
              className={styles.select}
              title="Phone model"
              value={modelKey}
              onChange={e => setModelKey(e.target.value)}
            >
              {modelOptions.map(m => (
                <option key={m.key} value={m.key}>{m.label}</option>
              ))}
            </select>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>Target</label>
            <PillGroup<Target>
              value={target}
              onChange={setTarget}
              options={[
                { value: 'phone', label: 'Phone' },
                { value: 'sidecar', label: 'Sidecar' },
                { value: 'combined', label: 'Combined' },
              ]}
            />
            {target === 'sidecar' && !rule.sidecarSupported && (
              <span className={styles.fieldNote}>⚠ This model does not support a sidecar.</span>
            )}
            {target === 'combined' && (
              <span className={styles.fieldNote}>Combined output = phone config + park lines at sidecar index.</span>
            )}
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>Build Style</label>
            <PillGroup<BuildStyle>
              value={buildStyle}
              onChange={setBuildStyle}
              options={[
                { value: 'template', label: 'Standard Template' },
                { value: 'adhoc', label: 'Ad Hoc Snippets' },
              ]}
            />
            <span className={styles.fieldNote}>
              {buildStyle === 'template'
                ? 'Starts from the standard base config. Add modules on top.'
                : 'No base template injected. Only selected snippets are generated.'}
            </span>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>Starting Point</label>
            <PillGroup<SourceMode>
              value={sourceMode}
              onChange={setSourceMode}
              options={[
                { value: 'scratch', label: 'From Scratch' },
                { value: 'production', label: 'From Production Config' },
              ]}
            />
            <span className={styles.fieldNote}>
              {sourceMode === 'production'
                ? 'Loads the scraped device config as the base, then appends selected modules.'
                : 'Builds from the selected template or empty state.'}
            </span>
          </div>
        </div>
      </Section>

      {/* ═══ SECTION 2: Source Data ═══════════════════════════════════════ */}
      <Section title="2 · Source Data">
        <div className={styles.sourceGrid}>

          {/* Manual fields always visible */}
          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>PBX IP Address</label>
            <input
              className={styles.input}
              type="text"
              placeholder="e.g. 10.0.0.1"
              value={pbxIp}
              onChange={e => setPbxIp(e.target.value)}
            />
            <span className={styles.fieldNote}>Required for park lines, BLF, and transfer keys.</span>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>Extension</label>
            <input
              className={styles.input}
              type="text"
              placeholder="e.g. 101"
              value={extension}
              onChange={e => setExtension(e.target.value)}
            />
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>SIP Password</label>
            <input
              className={styles.input}
              type="text"
              placeholder="SIP auth password"
              value={sipPassword}
              onChange={e => setSipPassword(e.target.value)}
            />
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel}>Display Label</label>
            <input
              className={styles.input}
              type="text"
              placeholder="e.g. John Smith"
              value={displayLabel}
              onChange={e => setDisplayLabel(e.target.value)}
            />
          </div>
        </div>

        {/* Scraper panel — always shown, used for production source */}
        <div className={styles.scraperPanel}>
          <div className={styles.scraperPanelHeader}>
            <span className={scraperBadgeClass}>{scraperBadgeText}</span>
            {sourceMode === 'production' && (
              <span className={styles.scraperNote}>
                Select a device below to load its production config as the base.
              </span>
            )}
          </div>

          {scraperOnline && (
            <div className={styles.scraperControls}>
              <div className={styles.fieldGroup}>
                <label className={styles.fieldLabel}>Company Handle</label>
                <select
                  className={styles.select}
                  title="Company handle"
                  value={selectedHandle}
                  onChange={e => handleSelectHandle(e.target.value)}
                  disabled={handles.length === 0}
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
                <>
                  <div className={styles.fieldGroup}>
                    <label className={styles.fieldLabel}>
                      Device
                      {devicesLoading && <span className={styles.labelNote}> Loading…</span>}
                      {!devicesLoading && devices.length > 0 && (
                        <span className={styles.labelNote}> ({devices.length})</span>
                      )}
                    </label>
                    <select
                      className={styles.select}
                      title="Device"
                      value={selectedDeviceId}
                      onChange={e => setSelectedDeviceId(e.target.value)}
                      disabled={devicesLoading || devices.length === 0}
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

                  <div className={styles.fieldGroup}>
                    <label className={styles.fieldLabel}>Scrape</label>
                    <div className={styles.scrapeRow}>
                      <button
                        type="button"
                        className={styles.scrapeBtn}
                        onClick={handleScrapeHandle}
                        disabled={scraping}
                      >
                        {scraping ? 'Scraping…' : `Re-scrape ${selectedHandle}`}
                      </button>
                      {selectedDevice && sourceMode === 'production' && (
                        <button
                          type="button"
                          className={styles.loadBtn}
                          onClick={() => applyScrapedDevice(selectedDevice)}
                        >
                          Load Fields
                        </button>
                      )}
                    </div>
                    {scrapeStatus && <span className={styles.scrapeStatus}>{scrapeStatus}</span>}
                  </div>
                </>
              )}

              {scraperError && <p className={styles.error}>✗ {scraperError}</p>}
            </div>
          )}
        </div>
      </Section>

      {/* ═══ SECTION 3: Standard Template Options (template mode only) ═══ */}
      {buildStyle === 'template' && (
        <Section title="3 · Standard Template Options">
          <div className={styles.templateOptions}>
            {vendor === 'yealink' && (
              <CheckRow
                checked={includeBase}
                onChange={setIncludeBase}
                label="Include standard base config"
                sub=" — network, NTP, directory, provisioning URL, voicemail, admin password"
              />
            )}
            {vendor === 'polycom' && (
              <p className={styles.infoNote}>
                Polycom configuration is site-level (XML). Use the snippets below to add
                per-device overrides on top of the existing site config.
              </p>
            )}
            <div className={styles.parkLineRow}>
              <CheckRow
                checked={includeParkLines}
                onChange={setIncludeParkLines}
                label="Include park lines"
                sub={rule.dect ? ' — not available on DECT phones' : ` — starts at key ${rule.parkLineStart}`}
              />
              {includeParkLines && !rule.dect && (
                <label className={styles.parkCountLabel}>
                  Count:
                  <input
                    className={styles.parkCountInput}
                    type="number"
                    min={1}
                    max={5}
                    value={parkLineCount}
                    onChange={e => setParkLineCount(Number(e.target.value))}
                  />
                </label>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* ═══ SECTION 4: Add-on Modules ══════════════════════════════════ */}
      <Section title={buildStyle === 'template' ? '4 · Add-on Modules' : '3 · Snippets'}>
        <div className={styles.addons}>

          {/* Park lines in ad hoc mode */}
          {buildStyle === 'adhoc' && !rule.dect && (
            <div className={styles.addonBlock}>
              <div className={styles.parkLineRow}>
                <CheckRow
                  checked={includeParkLines}
                  onChange={setIncludeParkLines}
                  label="Park lines"
                  sub={` — starts at key ${rule.parkLineStart}`}
                />
                {includeParkLines && (
                  <label className={styles.parkCountLabel}>
                    Count:
                    <input
                      className={styles.parkCountInput}
                      type="number" min={1} max={5}
                      value={parkLineCount}
                      onChange={e => setParkLineCount(Number(e.target.value))}
                    />
                  </label>
                )}
              </div>
            </div>
          )}

          {/* BLF Keys */}
          {!rule.dect && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addBlfKeys}
                onChange={setAddBlfKeys}
                label="BLF / Monitor Keys"
                sub=" — busy lamp field keys that light up when an extension is in use"
              />
              {addBlfKeys && (
                <KeyRowTable
                  rows={blfRows}
                  onChange={(i, f, v) => updateRow(setBlfRows, i, f, v)}
                  onAdd={() => setBlfRows(r => [...r, emptyKeyRow()])}
                  onRemove={i => setBlfRows(r => r.filter((_, idx) => idx !== i))}
                  colHeaders={['Key #', 'Extension', 'Label']}
                  colPlaceholders={['e.g. 7', '101', 'John Smith']}
                />
              )}
            </div>
          )}

          {/* Transfer Hotkeys — Yealink only */}
          {vendor === 'yealink' && !rule.dect && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addTransferHotkey}
                onChange={setAddTransferHotkey}
                label="Transfer Hotkeys (Yealink)"
                sub=" — linekey type 12, blind-transfers the active call"
              />
              {addTransferHotkey && (
                <KeyRowTable
                  rows={transferRows}
                  onChange={(i, f, v) => updateRow(setTransferRows, i, f, v)}
                  onAdd={() => setTransferRows(r => [...r, emptyKeyRow()])}
                  onRemove={i => setTransferRows(r => r.filter((_, idx) => idx !== i))}
                  colHeaders={['Key #', 'Extension', 'Label']}
                  colPlaceholders={['e.g. 8', '200', 'Receptionist']}
                />
              )}
            </div>
          )}

          {/* External / Speed Dial */}
          {!rule.dect && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addExternalDial}
                onChange={setAddExternalDial}
                label={vendor === 'yealink' ? 'External Number Speed Dial (Yealink)' : 'Speed Dial Keys (Polycom)'}
                sub={vendor === 'yealink'
                  ? ' — linekey type 13'
                  : ' — attendant.resourcelist type=normal'}
              />
              {addExternalDial && (
                <KeyRowTable
                  rows={externalRows}
                  onChange={(i, f, v) => updateRow(setExternalRows, i, f, v)}
                  onAdd={() => setExternalRows(r => [...r, emptyKeyRow()])}
                  onRemove={i => setExternalRows(r => r.filter((_, idx) => idx !== i))}
                  colHeaders={['Key #', 'Number / Extension', 'Label']}
                  colPlaceholders={['e.g. 9', '18005551234', 'Support Line']}
                />
              )}
            </div>
          )}

          {/* EFK Prompt — Polycom only */}
          {vendor === 'polycom' && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addEfk}
                onChange={setAddEfk}
                label="EFK Prompt Button (Polycom)"
                sub=" — feature code button that prompts user for input (e.g. Intercom)"
              />
              {addEfk && (
                <div className={styles.efkGrid}>
                  <label className={styles.fieldLabel}>EFK Index</label>
                  <input className={styles.input} type="number" min={1} value={efkOpts.efkIndex}
                    title="EFK list index (efk.efklist.N)"
                    onChange={e => setEfkOpts(o => ({ ...o, efkIndex: Number(e.target.value) }))} />

                  <label className={styles.fieldLabel}>Linekey Number</label>
                  <input className={styles.input} type="number" min={1} value={efkOpts.linekeyNum}
                    title="Linekey number to assign this EFK to"
                    onChange={e => setEfkOpts(o => ({ ...o, linekeyNum: Number(e.target.value) }))} />

                  <label className={styles.fieldLabel}>Button Name</label>
                  <input className={styles.input} type="text" value={efkOpts.mname}
                    title="Button display name"
                    placeholder="e.g. Intercom"
                    onChange={e => setEfkOpts(o => ({ ...o, mname: e.target.value }))} />

                  <label className={styles.fieldLabel}>Action String</label>
                  <input className={styles.input} type="text" value={efkOpts.actionString}
                    placeholder="*80$P2N4$$Tinvite$"
                    onChange={e => setEfkOpts(o => ({ ...o, actionString: e.target.value }))} />

                  <label className={styles.fieldLabel}>Prompt Label</label>
                  <input className={styles.input} type="text" value={efkOpts.promptLabel}
                    placeholder="Extension"
                    onChange={e => setEfkOpts(o => ({ ...o, promptLabel: e.target.value }))} />

                  <label className={styles.fieldLabel}>Prompt Type</label>
                  <select className={styles.select} title="Prompt input type" value={efkOpts.promptType}
                    onChange={e => setEfkOpts(o => ({ ...o, promptType: e.target.value as 'numeric' | 'string' }))}>
                    <option value="numeric">Numeric</option>
                    <option value="string">String</option>
                  </select>
                </div>
              )}
            </div>
          )}

          {/* Date/Time Override — Polycom only */}
          {vendor === 'polycom' && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addDateTimeOverride}
                onChange={setAddDateTimeOverride}
                label="Date/Time Override (Polycom)"
                sub=" — forces Eastern Time and Google NTP (pool.ntp.org)"
              />
            </div>
          )}

          {/* Hold Ringback — Polycom only */}
          {vendor === 'polycom' && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addHoldRingback}
                onChange={setAddHoldRingback}
                label="Enable Hold Ringback (Polycom)"
                sub=" — plays a tone reminding the user they have a call on hold"
              />
            </div>
          )}

          {/* Hold Volume Reset — Yealink only */}
          {vendor === 'yealink' && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addHoldVolume}
                onChange={setAddHoldVolume}
                label="Prevent Volume Reset Between Calls (Yealink)"
                sub=" — voice.handset.autoreset_spk_vol=0"
              />
            </div>
          )}

          {/* URL Dialing Disable — Polycom only */}
          {vendor === 'polycom' && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addUrlDialingDisable}
                onChange={setAddUrlDialingDisable}
                label="Disable URL Dialing (Polycom)"
                sub=" — stops incoming calls from displaying as SIP URLs"
              />
            </div>
          )}

          {/* Remove DND — Polycom only */}
          {vendor === 'polycom' && (
            <div className={styles.addonBlock}>
              <CheckRow
                checked={addRemoveDnd}
                onChange={setAddRemoveDnd}
                label="Disable Do Not Disturb (Polycom)"
                sub=" — prevents users from enabling DND"
              />
            </div>
          )}
        </div>
      </Section>

      {/* ═══ SECTION 5: Output ═══════════════════════════════════════════ */}
      <Section title={buildStyle === 'template' ? '5 · Generated Config' : '4 · Generated Config'}>
        <div className={styles.outputActions}>
          <button type="button" className={styles.generateBtn} onClick={handleGenerate}>
            Generate Config
          </button>
          {output && (
            <button type="button" className={styles.copyBtn} onClick={handleCopy}>
              {copied ? '✓ Copied!' : 'Copy to Clipboard'}
            </button>
          )}
          {output && (
            <span className={styles.outputMeta}>
              {output.split('\n').filter(l => l.trim() && !l.startsWith('#')).length} config lines
            </span>
          )}
        </div>
        {output ? (
          <textarea
            ref={outputRef}
            className={styles.outputTextarea}
            value={output}
            onChange={e => setOutput(e.target.value)}
            rows={30}
            spellCheck={false}
            aria-label="Generated phone config"
          />
        ) : (
          <p className={styles.outputEmpty}>
            Click <strong>Generate Config</strong> to assemble the configuration based on your selections above.
          </p>
        )}
      </Section>
    </div>
  );
}
