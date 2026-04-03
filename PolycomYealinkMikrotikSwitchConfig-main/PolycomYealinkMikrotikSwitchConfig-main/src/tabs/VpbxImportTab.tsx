import React, { useEffect, useRef, useState } from 'react';
import Papa from 'papaparse';

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

function deviceToRow(d: DeviceConfig): VpbxRow {
  const cfg = parseBulkConfig(d.bulk_config || '');
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

  // Check scraper connectivity + load handles
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

  const scraperBadge = scraperOnline === null
    ? { text: 'checking…', color: '#888' }
    : scraperOnline
      ? { text: '● Webscraper connected', color: '#16794a' }
      : { text: '○ Webscraper offline (localhost:8788)', color: '#b42318' };

  return (
    <div style={{ maxWidth: 1200 }}>
      <h2>VPBX Import</h2>

      {/* Live Load Panel */}
      <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <strong style={{ fontSize: 14 }}>Load from 123NET Webscraper</strong>
          <span style={{ fontSize: 12, color: scraperBadge.color }}>{scraperBadge.text}</span>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <label htmlFor="vpbx-handle-select" style={{ fontSize: 13, fontWeight: 600 }}>Handle:</label>
          <select
            id="vpbx-handle-select"
            value={selectedHandle}
            onChange={e => setSelectedHandle(e.target.value)}
            disabled={!scraperOnline || handles.length === 0}
            style={{ minWidth: 200, padding: '4px 8px' }}
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
            onClick={loadFromScraper}
            disabled={!scraperOnline || !selectedHandle}
            style={{ padding: '4px 14px' }}
          >
            Load Devices
          </button>
          {loadStatus && <span style={{ fontSize: 13, color: '#16794a' }}>✓ {loadStatus}</span>}
          {loadError && <span style={{ fontSize: 13, color: '#b42318' }}>✗ {loadError}</span>}
        </div>
        {scraperOnline && (
          <p style={{ margin: '8px 0 0', fontSize: 12, color: '#555' }}>
            Loads MAC, model, extension, name, and auth credentials extracted from scraped bulk configs.
            Fields not in the scraped data (voicemail, outbound CID, etc.) remain blank for manual entry.
          </p>
        )}
      </div>

      {/* CSV import/export */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <label htmlFor="vpbx-csv-import" style={{ fontSize: 13 }}>Import CSV:</label>
        <input id="vpbx-csv-import" type="file" accept=".csv" onChange={handleImport} title="Import VPBX CSV" />
        <button onClick={handleExport}>Export CSV</button>
        <button onClick={() => setRows(prev => [...prev, createEmpty()])}>+ Add Row</button>
        <a ref={downloadRef} style={{ display: 'none' }}>Download</a>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: 900 }}>
          <thead>
            <tr style={{ background: '#f4f4f4' }}>
              {VPBX_FIELDS.map(f => (
                <th key={f} style={{ padding: '6px 8px', border: '1px solid #ddd', whiteSpace: 'nowrap', textAlign: 'left' }}>
                  {f}
                </th>
              ))}
              <th style={{ padding: '6px 8px', border: '1px solid #ddd' }}>Del</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx} style={{ background: idx % 2 === 0 ? '#fff' : '#fafafa' }}>
                {VPBX_FIELDS.map(f => (
                  <td key={f} style={{ padding: 2, border: '1px solid #eee' }}>
                    <input
                      aria-label={f}
                      title={f}
                      name={f}
                      value={row[f] || ''}
                      onChange={e => handleChange(idx, f, e.target.value)}
                      style={{ width: f === 'name' || f === 'description' ? 120 : 80, padding: '2px 4px', fontSize: 12, border: 'none', background: 'transparent' }}
                    />
                  </td>
                ))}
                <td style={{ padding: 2, border: '1px solid #eee', textAlign: 'center' }}>
                  <button
                    onClick={() => setRows(prev => prev.length === 1 ? prev : prev.filter((_, i) => i !== idx))}
                    style={{ fontSize: 11, padding: '1px 6px', cursor: 'pointer' }}
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