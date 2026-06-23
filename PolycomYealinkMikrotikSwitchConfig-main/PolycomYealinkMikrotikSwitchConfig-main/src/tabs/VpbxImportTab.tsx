/**
 * VpbxImportTab.tsx
 * VPBX extension + phone provisioning import table — step 3 of the workflow.
 *
 * Sources:
 *  • Loaded from FPBX (localStorage) via "← Load from FPBX" button
 *  • Loaded live from 123NET webscraper
 *  • Imported from CSV
 *
 * Toolbar actions:
 *   Clear | Import CSV | Export CSV
 *   Clean MACs | Generate MACs | Generate Secrets
 *   ← Load from FPBX
 */
import React, { useEffect, useRef, useState } from 'react';
import * as Papa from 'papaparse';
import panelStyles from './VpbxImportTab.module.css';
import tableStyles from './ImportTable.module.css';
import ImportTable from './ImportTable';
import {
  VPBX_FIELDS,
  cleanVpbxMacs,
  emptyVpbxRow,
  exportCsv,
  generateVpbxMacs,
  generateVpbxSecrets,
  loadStore,
  populateVpbxFromFpbx,
  saveStore,
  type AnyRow,
  type FpbxRow,
  type VpbxRow,
} from '../data/importStore';

const SCRAPER_BASE = import.meta.env.VITE_SCRAPER_BASE || 'http://localhost:8788';

type VpbxRecord = { handle: string; name: string; account_status: string; ip: string };
type DeviceConfig = {
  device_id: string; handle: string; directory_name: string; extension: string;
  mac: string; make: string; model: string; site_code: string; bulk_config: string;
  view_config: string; arbitrary_attributes: string;
};

function parseBulkConfig(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of raw.split('\n')) {
    const eq = line.indexOf('=');
    if (eq > 0) out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
  }
  return out;
}

const PLACEHOLDER_STRINGS = new Set(['place holder text', 'placeholder text', 'placeholder']);
function bestConfig(d: DeviceConfig): string {
  const candidates = [d.view_config, d.arbitrary_attributes, d.bulk_config];
  for (const c of candidates) {
    if (c && !PLACEHOLDER_STRINGS.has(c.trim().toLowerCase())) return c;
  }
  return '';
}

function deviceToRow(d: DeviceConfig): VpbxRow {
  const cfg = parseBulkConfig(bestConfig(d));
  const row = emptyVpbxRow();
  row.mac = d.mac || '';
  row.model = d.model || '';
  row.extension = d.extension || cfg['reg.1.address'] || cfg['account.1.label'] || '';
  row.name = d.directory_name || cfg['reg.1.displayname'] || '';
  row.secret = cfg['reg.1.auth.password'] || cfg['account.1.password'] || '';
  row.user = cfg['reg.1.auth.userid'] || cfg['account.1.auth_name'] || row.extension;
  row.tech = 'pjsip';
  return row;
}

const WIDE_FIELDS = ['name', 'description', 'voicemail_email', 'voicemail_options', 'dial'] as const;

const VPBX_MODELS = [
  'VVX500', 'VVX400', 'VVX600',
  'CP-7841-3PCC', 'CP-7832-3PCC', 'CP-7811-3PCC',
  'CP-8832-K9', 'CP-8832-3PCC',
  'SPA-122 ATA',
  'SSIP6000', 'SSIP7000', 'SSIP7000-Mic', 'SSIP330',
  'Stand Alone Softphone', 'SideCar Entry',
  'D230',
  'Trio 8500 Conference',
  'T54W', 'T57W',
  'CP960', 'CP920',
  'SIP-T46S', 'SIP-T46U', 'SIP-T48S', 'SIP-T48U',
  'Strike Door Strike',
  '8188 IP Loud Ringer', '8181 Paging Server',
  'W60P', 'W56H',
  'ATA/ATAK',
  '56h Dect w/ 60p Base', '56h Dect w/ 76p Base', '56h Dect Handset',
];

const VPBX_SELECT_OPTIONS = { model: VPBX_MODELS };

export default function VpbxImportTab() {
  const [rows, setRows] = useState<VpbxRow[]>(() => {
    const saved = loadStore('vpbx') as VpbxRow[] | null;
    return saved?.length ? saved : Array(200).fill(null).map(emptyVpbxRow);
  });
  const [handles, setHandles] = useState<VpbxRecord[]>([]);
  const [selectedHandle, setSelectedHandle] = useState('');
  const [scraperStatus, setScraperStatus] = useState<string | null>(null);
  const [scraperError, setScraperError] = useState<string | null>(null);
  const [scraperOnline, setScraperOnline] = useState<boolean | null>(null);
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const downloadRef = useRef<HTMLAnchorElement>(null);

  // Persist on change
  useEffect(() => {
    saveStore('vpbx', rows as AnyRow[]);
  }, [rows]);

  // Check scraper connectivity
  useEffect(() => {
    fetch(`${SCRAPER_BASE}/api/vpbx/records`, { signal: AbortSignal.timeout(3000) })
      .then(r => r.json())
      .then(data => {
        setScraperOnline(true);
        const items: VpbxRecord[] = data?.items || [];
        setHandles(items.sort((a, b) => a.handle.localeCompare(b.handle)));
      })
      .catch(() => setScraperOnline(false));
  }, []);

  async function loadFromScraper() {
    if (!selectedHandle) return;
    setScraperStatus('Loading…');
    setScraperError(null);
    try {
      const res = await fetch(
        `${SCRAPER_BASE}/api/vpbx/device-configs?handle=${encodeURIComponent(selectedHandle)}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const devices: DeviceConfig[] = data?.items || [];
      if (devices.length === 0) {
        setScraperError(`No device configs found for ${selectedHandle}. Scrape it first.`);
        setScraperStatus(null);
        return;
      }
      setRows(devices.map(d => { const r = deviceToRow(d); r.outboundcid = r.outboundcid.replace(/\D/g, ''); return r; }));
      setScraperStatus(`Loaded ${devices.length} device(s) from ${selectedHandle}`);
    } catch (e) {
      setScraperError(e instanceof Error ? e.message : String(e));
      setScraperStatus(null);
    }
  }

  function handleChange(i: number, field: string, value: string) {
    const cleaned = field === 'outboundcid' ? value.replace(/\D/g, '') : value;
    setRows(prev => {
      const next = [...prev];
      next[i] = { ...next[i], [field]: cleaned };
      return next;
    });
  }

  function handleDeleteRow(i: number) {
    setRows(prev => prev.filter((_, idx) => idx !== i));
  }

  function handleAddRow() {
    setRows(prev => [...prev, emptyVpbxRow()]);
  }

  function handleClear() {
    if (!confirm('Clear all VPBX rows?')) return;
    setRows(Array(200).fill(null).map(emptyVpbxRow));
    setStatus({ msg: 'Cleared.', ok: true });
  }

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete(results) {
        const imported = results.data.map(r => {
          const row = emptyVpbxRow();
          VPBX_FIELDS.forEach(f => { row[f] = r[f] ?? ''; });
          return row;
        });
        setRows(imported);
        setStatus({ msg: `Imported ${imported.length} row(s).`, ok: true });
        if (fileRef.current) fileRef.current.value = '';
      },
      error() { setStatus({ msg: 'CSV parse error.', ok: false }); },
    });
  }

  function handleExport() {
    exportCsv('vpbx_import.csv', VPBX_FIELDS, rows as AnyRow[]);
  }

  function handleCleanDids() {
    setRows(prev => prev.map(r => ({ ...r, outboundcid: r.outboundcid.replace(/\D/g, '') })));
    setStatus({ msg: 'Outbound CIDs cleaned — digits only.', ok: true });
  }

  function handleCleanMacs() {
    setRows(cleanVpbxMacs(rows));
    setStatus({ msg: 'MACs cleaned.', ok: true });
  }

  function handleGenerateMacs() {
    setRows(generateVpbxMacs(rows));
    setStatus({ msg: 'MACs generated for rows with a model but no MAC.', ok: true });
  }

  function handleGenerateSecrets() {
    setRows(generateVpbxSecrets(rows));
    setStatus({ msg: 'Secrets generated.', ok: true });
  }

  function handleLoadFromFpbx() {
    const fpbxRows = loadStore('fpbx') as FpbxRow[] | null;
    if (!fpbxRows?.length) {
      setStatus({ msg: 'No FPBX data found. Populate the FBPX Import tab first.', ok: false });
      return;
    }
    const vpbxRows = populateVpbxFromFpbx(fpbxRows, rows);
    setRows(vpbxRows);
    setStatus({ msg: `Loaded ${vpbxRows.length} row(s) from FPBX.`, ok: true });
  }

  const scraperBadgeClass = scraperOnline === null
    ? panelStyles.scraperChecking
    : scraperOnline ? panelStyles.scraperOnline : panelStyles.scraperOffline;
  const scraperText = scraperOnline === null
    ? 'checking…'
    : scraperOnline ? '● Webscraper connected' : '○ Webscraper offline (localhost:8788)';

  return (
    <div className={panelStyles.container}>

      {/* Scraper panel */}
      <div className={panelStyles.loadPanel}>
        <div className={panelStyles.loadPanelHeader}>
          <strong className={panelStyles.loadPanelTitle}>Load from 123NET Webscraper</strong>
          <span className={scraperBadgeClass}>{scraperText}</span>
        </div>
        <div className={panelStyles.loadControls}>
          <label htmlFor="vpbx-handle-select" className={panelStyles.handleLabel}>Handle:</label>
          <select
            id="vpbx-handle-select"
            className={panelStyles.handleSelect}
            value={selectedHandle}
            onChange={e => setSelectedHandle(e.target.value)}
            disabled={!scraperOnline || handles.length === 0}
            title="Select a company handle to load device configs"
          >
            <option value="">— select handle —</option>
            {handles.map(h => (
              <option key={h.handle} value={h.handle}>
                {h.handle} — {h.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={panelStyles.loadBtn}
            onClick={loadFromScraper}
            disabled={!scraperOnline || !selectedHandle}
          >
            Load Devices
          </button>
          {scraperStatus && <span className={panelStyles.statusOk}>✓ {scraperStatus}</span>}
          {scraperError  && <span className={panelStyles.statusErr}>✗ {scraperError}</span>}
        </div>
        {scraperOnline && (
          <p className={panelStyles.loadHint}>
            Loads MAC, model, extension, name, and auth credentials from scraped device configs.
            Fields not scraped (voicemail, outbound CID, etc.) remain blank for manual entry or FPBX mirror.
          </p>
        )}
      </div>
      <a ref={downloadRef} className={panelStyles.downloadLink}>Download</a>

      {/* Toolbar */}
      <div className={tableStyles.toolbar}>
        <div className={tableStyles.toolbarGroup}>
          <button type="button" className={tableStyles.btnDanger} onClick={handleClear}>Clear</button>
          <div className={tableStyles.toolbarDivider} />
          <label className={`${tableStyles.btn} ${panelStyles.fileLabel}`}>
            Import CSV
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className={panelStyles.fileInput}
              onChange={handleImport}
            />
          </label>
          <button type="button" className={tableStyles.btnSuccess} onClick={handleExport}>Export CSV</button>
        </div>
        <div className={tableStyles.toolbarDivider} />
        <div className={tableStyles.toolbarGroup}>
          <button type="button" className={tableStyles.btn} onClick={handleCleanDids}>Clean DID's</button>
          <button type="button" className={tableStyles.btn} onClick={handleCleanMacs}>Clean MAC</button>
          <button type="button" className={tableStyles.btn} onClick={handleGenerateMacs}>Generate MAC's</button>
          <button type="button" className={tableStyles.btn} onClick={handleGenerateSecrets}>Generate Secrets</button>
        </div>
        <div className={tableStyles.toolbarDivider} />
        <div className={tableStyles.toolbarGroup}>
          <button type="button" className={tableStyles.btnPrimary} onClick={handleLoadFromFpbx}>
            Populate VPBX →
          </button>
        </div>
        {status && (
          <span className={status.ok ? tableStyles.statusOk : tableStyles.statusErr}>
            {status.msg}
          </span>
        )}
      </div>

      <ImportTable
        fields={VPBX_FIELDS}
        rows={rows as AnyRow[]}
        onChange={handleChange}
        onDeleteRow={handleDeleteRow}
        onAddRow={handleAddRow}
        wideFields={WIDE_FIELDS}
        selectOptions={VPBX_SELECT_OPTIONS}
      />
    </div>
  );
}
