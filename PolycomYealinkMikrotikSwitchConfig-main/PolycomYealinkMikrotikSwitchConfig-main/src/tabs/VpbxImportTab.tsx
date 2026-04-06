import React, { useEffect, useRef, useState } from 'react';
import Papa from 'papaparse';
import styles from './VpbxImportTab.module.css';

const SCRAPER_BASE = 'http://localhost:8788';

const VPBX_FIELDS = [
  'mac', 'model', 'extension', 'name', 'description', 'tech', 'secret',
  'callwaiting_enable', 'voicemail', 'voicemail_enable', 'voicemail_vmpwd',
  'voicemail_email', 'voicemail_pager', 'voicemail_options', 'voicemail_same_exten',
  'outboundcid', 'id', 'dial', 'user', 'max_contacts', 'accountcode',
] as const;

type VpbxField = typeof VPBX_FIELDS[number];
type VpbxRow = Record<VpbxField, string>;

type VpbxRecord = { handle: string; name: string; account_status: string; ip: string };
type DeviceConfig = {
  device_id: string; handle: string; directory_name: string; extension: string;
  mac: string; make: string; model: string; site_code: string; bulk_config: string;
  view_config: string; arbitrary_attributes: string;
};

const createEmpty = (): VpbxRow =>
  VPBX_FIELDS.reduce((a, f) => ({ ...a, [f]: '' }), {} as VpbxRow);

function parseBulkConfig(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of raw.split('\n')) {
    const eq = line.indexOf('=');
    if (eq > 0) out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
  }
  return out;
}

function bestConfig(d: DeviceConfig): string {
  return d.view_config || d.arbitrary_attributes || d.bulk_config || '';
}

function deviceToRow(d: DeviceConfig): VpbxRow {
  const cfg = parseBulkConfig(bestConfig(d));
  const row = createEmpty();
  row.mac = d.mac || '';
  row.model = d.model || '';
  row.extension = d.extension || cfg['reg.1.address'] || cfg['account.1.label'] || '';
  row.name = d.directory_name || cfg['reg.1.displayname'] || '';
  row.secret = cfg['reg.1.auth.password'] || cfg['account.1.password'] || '';
  row.user = cfg['reg.1.auth.userid'] || cfg['account.1.auth_name'] || row.extension;
  row.tech = 'pjsip';
  return row;
}

export default function VpbxImportTab() {
  const [rows, setRows] = useState<VpbxRow[]>(Array(5).fill(null).map(createEmpty));
  const [handles, setHandles] = useState<VpbxRecord[]>([]);
  const [selectedHandle, setSelectedHandle] = useState('');
  const [loadStatus, setLoadStatus] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scraperOnline, setScraperOnline] = useState<boolean | null>(null);
  const downloadRef = useRef<HTMLAnchorElement>(null);

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
    setLoadStatus('Loading…');
    setLoadError(null);
    try {
      const res = await fetch(
        `${SCRAPER_BASE}/api/vpbx/device-configs?handle=${encodeURIComponent(selectedHandle)}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const devices: DeviceConfig[] = data?.items || [];
      if (devices.length === 0) {
        setLoadError(`No device configs found for ${selectedHandle}. Scrape it first in the webscraper.`);
        setLoadStatus(null);
        return;
      }
      setRows(devices.map(deviceToRow));
      setLoadStatus(`Loaded ${devices.length} device(s) from ${selectedHandle}`);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
      setLoadStatus(null);
    }
  }

  function handleChange(rowIdx: number, field: VpbxField, value: string) {
    setRows(prev => {
      const next = [...prev];
      next[rowIdx] = { ...next[rowIdx], [field]: value };
      return next;
    });
  }

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse(file, {
      header: true,
      complete: (results: Papa.ParseResult<Record<string, string>>) => {
        const parsed = (results.data as VpbxRow[]).filter(r => r && Object.values(r).some(Boolean));
        setRows(parsed.length ? parsed : [createEmpty()]);
        setLoadStatus(`Imported ${parsed.length} rows from CSV`);
      },
    });
  }

  function handleExport() {
    const header = VPBX_FIELDS.join(',') + '\n';
    const body = rows.map(r =>
      VPBX_FIELDS.map(f => `"${(r[f] || '').replace(/"/g, '""')}"`).join(',')
    ).join('\n') + '\n';
    const blob = new Blob([header + body], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    if (downloadRef.current) {
      downloadRef.current.href = url;
      downloadRef.current.download = 'vpbx_import.csv';
      downloadRef.current.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  const scraperBadgeClass = scraperOnline === null
    ? styles.scraperChecking
    : scraperOnline ? styles.scraperOnline : styles.scraperOffline;
  const scraperText = scraperOnline === null
    ? 'checking…'
    : scraperOnline
      ? '● Webscraper connected'
      : '○ Webscraper offline (localhost:8788)';

  return (
    <div className={styles.container}>
      <h2>VPBX Import</h2>

      {/* Live Load Panel */}
      <div className={styles.loadPanel}>
        <div className={styles.loadPanelHeader}>
          <strong className={styles.loadPanelTitle}>Load from 123NET Webscraper</strong>
          <span className={scraperBadgeClass}>{scraperText}</span>
        </div>
        <div className={styles.loadControls}>
          <label htmlFor="vpbx-handle-select" className={styles.handleLabel}>Handle:</label>
          <select
            id="vpbx-handle-select"
            className={styles.handleSelect}
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
            className={styles.loadBtn}
            onClick={loadFromScraper}
            disabled={!scraperOnline || !selectedHandle}
          >
            Load Devices
          </button>
          {loadStatus && <span className={styles.statusOk}>✓ {loadStatus}</span>}
          {loadError && <span className={styles.statusErr}>✗ {loadError}</span>}
        </div>
        {scraperOnline && (
          <p className={styles.loadHint}>
            Loads MAC, model, extension, name, and auth credentials extracted from scraped device configs.
            Fields not in the scraped data (voicemail, outbound CID, etc.) remain blank for manual entry.
          </p>
        )}
      </div>

      {/* CSV import/export */}
      <div className={styles.csvControls}>
        <label htmlFor="vpbx-csv-import" className={styles.csvLabel}>Import CSV:</label>
        <input id="vpbx-csv-import" type="file" accept=".csv" onChange={handleImport} title="Import VPBX CSV" />
        <button type="button" onClick={handleExport}>Export CSV</button>
        <button type="button" onClick={() => setRows(prev => [...prev, createEmpty()])}>+ Add Row</button>
        <a ref={downloadRef} className={styles.downloadLink}>Download</a>
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead className={styles.thead}>
            <tr>
              {VPBX_FIELDS.map(f => (
                <th key={f} className={styles.th}>{f}</th>
              ))}
              <th className={styles.th}>Del</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx} className={idx % 2 === 0 ? styles.rowEven : styles.rowOdd}>
                {VPBX_FIELDS.map(f => (
                  <td key={f} className={styles.tdCell}>
                    <input
                      aria-label={f}
                      title={f}
                      name={f}
                      value={row[f] || ''}
                      onChange={e => handleChange(idx, f, e.target.value)}
                      className={f === 'name' || f === 'description' ? styles.cellInputWide : styles.cellInputNarrow}
                    />
                  </td>
                ))}
                <td className={styles.tdCenter}>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    onClick={() => setRows(prev => prev.length === 1 ? prev : prev.filter((_, i) => i !== idx))}
                    title="Delete row"
                  >✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
