import React, { useState, useRef, useEffect } from 'react';
import * as Papa from 'papaparse';
import styles from './HostedOrderTrackerTab.module.css';

const DEFAULT_FIELDS = [
  'CUSTOMER ABBREV', 'CUSTOMER NAME', 'LOCATION', 'DEPLOY FROM (SF/GR)', 'PROJECT MANAGER',
  'SURVEY DATE', 'KICKOFF DATE', 'INSTALL DATE', 'ON-NET or OTT', 'ORDER ID', 'PON',
  'LINK TO CONTRACT', '# SEATS MINIMUM', 'PBX TYPE', 'PBX IP ADDRESS', 'PHONE MODEL / QTY',
  'SWITCH / ASSET #', 'UPS / ASSET #', 'SIDECAR / ASSET #', 'MIKROTIK / ASSET #', 'MIKROTIK IP',
  'ATA / ASSET #', 'ALGO / ASSET #', 'Wall Mount | QTY', 'NOTES', 'ORDER TASKS',
  'HOSTED JOBVIEWER', 'CONFIRM INVENTORY', 'CHANGE VPBX PAGE TO PROVISIONING',
  'INCREASE PARKING LOT TIMING TO 300 (OPTIONAL)', 'PROVISION SWITCH', 'SAVED CONFIG ON SWITCH',
  'UPDATED SWITCH ASSET PAGE WITH CONFIG', 'CONFIGURED TIK (OTT)', 'CREATE SOFTPHONES',
  'PROVISION PHONES AND TEST', 'PROGRAM ATA', 'ASSET LABEL ON ATA', 'UPLOAD ATA CONFIG TO ASSET PAGE',
  'LABEL AND PLACE EQUIPMENT ON RACK', 'VERIFY ALL  EQUIPMENT ON ASSET PAGE',
  'NOTIFY TECHS OF EQUIPMENT LOCATION', 'TURN UP DAY TASKS', 'ATA TESTED', 'ALGO TESTED',
  'CONFIGURED TIK', 'INCREASE UDP TIMEOUT', 'WHITELISTED TIK AND DIA CIRCUIT',
  'EXPORT FINAL TIK CONFIG AND UPLOAD TO ASSET PAGE', 'EXPORT FINAL SWITCH CONFIG / UPLOAD TO ASSET PAGE',
  'ALL PHONES ONLINE', 'TN ORDERS', 'CHANGE VPBX PAGE TO PRODUCTION', 'CREATE TURNUP TICKET',
  'SEND TRAINING MATERIALS', 'UPDATE TASKS IN ORDER WEB ADMIN', 'UPDATE SITE NOTES',
  'UPDATE HOSTED JOB TRACKER',
];

const DEFAULT_CUSTOMERS: string[] = ['CUST1', 'CUST2', 'CUST3', 'CUST4', 'CUST5'];

const CHECKBOX_FIELDS = new Set([
  'HOSTED JOBVIEWER', 'CONFIRM INVENTORY', 'CHANGE VPBX PAGE TO PROVISIONING',
  'INCREASE PARKING LOT TIMING TO 300 (OPTIONAL)', 'PROVISION SWITCH', 'SAVED CONFIG ON SWITCH',
  'UPDATED SWITCH ASSET PAGE WITH CONFIG', 'CONFIGURED TIK (OTT)', 'CREATE SOFTPHONES',
  'PROVISION PHONES AND TEST', 'PROGRAM ATA', 'ASSET LABEL ON ATA', 'UPLOAD ATA CONFIG TO ASSET PAGE',
  'LABEL AND PLACE EQUIPMENT ON RACK', 'VERIFY ALL  EQUIPMENT ON ASSET PAGE',
  'NOTIFY TECHS OF EQUIPMENT LOCATION', 'TURN UP DAY TASKS', 'ATA TESTED', 'ALGO TESTED',
  'CONFIGURED TIK', 'INCREASE UDP TIMEOUT', 'WHITELISTED TIK AND DIA CIRCUIT',
  'EXPORT FINAL TIK CONFIG AND UPLOAD TO ASSET PAGE', 'EXPORT FINAL SWITCH CONFIG / UPLOAD TO ASSET PAGE',
  'ALL PHONES ONLINE', 'TN ORDERS', 'CHANGE VPBX PAGE TO PRODUCTION', 'CREATE TURNUP TICKET',
  'SEND TRAINING MATERIALS', 'UPDATE TASKS IN ORDER WEB ADMIN', 'UPDATE SITE NOTES',
  'UPDATE HOSTED JOB TRACKER',
]);

// Section-divider rows — read-only labels, not editable
const SECTION_HEADER_FIELDS = new Set(['ORDER TASKS', 'TURN UP DAY TASKS']);

const STORAGE_KEY = 'order_tracker_v1';
const DEFAULT_PM = 'tjohnson';
const ORDERS_ADMIN_URL = 'https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi';

type CellMap = { [field: string]: { [customer: string]: string } };

interface TrackerState {
  fields: string[];
  customers: string[];
  data: CellMap;
}

function defaultState(): TrackerState {
  return {
    fields: [...DEFAULT_FIELDS],
    customers: [...DEFAULT_CUSTOMERS],
    data: Object.fromEntries(DEFAULT_FIELDS.map(f => [f, {}])),
  };
}

function loadState(): TrackerState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as TrackerState;
  } catch { /* ignore */ }
  return defaultState();
}

function saveState(s: TrackerState) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch { /* ignore */ }
}

interface ParsedOrder {
  pm: string;
  orderId: string;
  billDate: string;
  closedDate: string;
  billMrc: string;
}

function parseManhourSummary(text: string, pm: string): ParsedOrder[] {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  // Find the CSV header line
  const headerIdx = lines.findIndex(l => /^PM[\s,]/i.test(l) && /Order\s*ID/i.test(l));
  if (headerIdx === -1) return [];
  const dataLines = lines.slice(headerIdx + 1);
  const results: ParsedOrder[] = [];
  for (const line of dataLines) {
    const parts = line.split(',').map(p => p.trim());
    if (parts.length < 2) continue;
    if (parts[0].toLowerCase() === pm.toLowerCase()) {
      results.push({
        pm: parts[0],
        orderId: parts[1] || '',
        billDate: parts[2] || '',
        closedDate: parts[3] || '',
        billMrc: parts[4] || '',
      });
    }
  }
  return results;
}

const HostedOrderTrackerTab: React.FC = () => {
  const [state, setState] = useState<TrackerState>(loadState);
  const { fields, customers, data } = state;

  const [showPasteModal, setShowPasteModal] = useState(false);
  const [pasteText, setPasteText] = useState('');
  const [pasteFilter, setPasteFilter] = useState(DEFAULT_PM);
  const [pastePreview, setPastePreview] = useState<ParsedOrder[]>([]);
  const [pasteStatus, setPasteStatus] = useState('');

  const downloadRef = useRef<HTMLAnchorElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Persist on every state change
  useEffect(() => { saveState(state); }, [state]);

  // Focus textarea when modal opens
  useEffect(() => {
    if (showPasteModal) setTimeout(() => textareaRef.current?.focus(), 50);
  }, [showPasteModal]);

  function update(patch: Partial<TrackerState>) {
    setState(prev => ({ ...prev, ...patch }));
  }

  // ── Paste modal ────────────────────────────────────────────────────────────

  function handlePasteTextChange(text: string) {
    setPasteText(text);
    if (!text.trim()) { setPastePreview([]); setPasteStatus(''); return; }
    const orders = parseManhourSummary(text, pasteFilter);
    setPastePreview(orders);
    setPasteStatus(orders.length
      ? `Found ${orders.length} order${orders.length !== 1 ? 's' : ''} for PM "${pasteFilter}".`
      : `No orders found for PM "${pasteFilter}" in this data.`);
  }

  function handleFilterChange(pm: string) {
    setPasteFilter(pm);
    if (!pasteText.trim()) { setPastePreview([]); setPasteStatus(''); return; }
    const orders = parseManhourSummary(pasteText, pm);
    setPastePreview(orders);
    setPasteStatus(orders.length
      ? `Found ${orders.length} order${orders.length !== 1 ? 's' : ''} for PM "${pm}".`
      : `No orders found for PM "${pm}" in this data.`);
  }

  function applyParsedOrders() {
    if (!pastePreview.length) return;

    // Existing customers that are "real" handles (not default CUSTX placeholders)
    const existingOrders = new Set(customers.filter(c => !c.match(/^CUST\d+$/)));
    const toAdd = pastePreview.filter(o => !existingOrders.has(o.orderId));

    if (!toAdd.length) {
      setPasteStatus('All found orders are already in the tracker.');
      return;
    }

    // Strip placeholder CUST columns that are fully empty
    const nonEmptyCustomers = customers.filter(c => {
      if (!c.match(/^CUST\d+$/)) return true;
      return fields.some(f => (data[f]?.[c] || '').trim() !== '');
    });

    const newCustomers = [...nonEmptyCustomers, ...toAdd.map(o => o.orderId)];

    const newData: CellMap = {};
    for (const f of fields) {
      newData[f] = { ...(data[f] || {}) };
    }

    for (const order of toAdd) {
      const col = order.orderId;
      const abbrev = order.orderId.split('-')[0] || order.orderId;

      newData['CUSTOMER ABBREV'][col]  = abbrev;
      newData['PROJECT MANAGER'][col]  = order.pm;
      newData['ORDER ID'][col]         = order.orderId;
      newData['LINK TO CONTRACT'][col] = ORDERS_ADMIN_URL;
      if (order.billDate) newData['KICKOFF DATE'][col] = order.billDate;
      if (order.billMrc)  newData['NOTES'][col]        = `MRC: $${order.billMrc}`;
    }

    update({ customers: newCustomers, data: newData });
    setPasteStatus(`Added ${toAdd.length} order${toAdd.length !== 1 ? 's' : ''} to the tracker.`);
    setPasteText('');
    setPastePreview([]);
    setTimeout(() => setShowPasteModal(false), 800);
  }

  // ── CSV import/export ───────────────────────────────────────────────────────

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results: Papa.ParseResult<Record<string, string>>) => {
        const rows = results.data as Record<string, string>[];
        if (!rows.length) return;
        const newFields = rows.map(r => r['Field'] || r['field'] || Object.values(r)[0]);
        const newCustomers = Object.keys(rows[0]).filter(k => k !== 'Field' && k !== 'field');
        const newData: CellMap = {};
        newFields.forEach((f, i) => {
          newData[f] = {};
          newCustomers.forEach(c => { newData[f][c] = rows[i][c] || ''; });
        });
        update({ fields: newFields, customers: newCustomers, data: newData });
      },
    });
    e.target.value = '';
  }

  function handleExport() {
    const csvHeader = ['Field', ...customers].join(',') + '\n';
    const csvRows = fields.map(f =>
      [f, ...customers.map(c => data[f]?.[c] || '')]
        .map(v => `"${(v || '').replace(/"/g, '""')}"`)
        .join(',')
    ).join('\n') + '\n';
    const blob = new Blob([csvHeader + csvRows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    if (downloadRef.current) {
      downloadRef.current.href = url;
      downloadRef.current.download = 'order_tracker.csv';
      downloadRef.current.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  function handleReset() {
    if (!confirm('Clear all order tracker data and reset to defaults?')) return;
    const s = defaultState();
    setState(s);
    saveState(s);
  }

  // ── Cell editing ────────────────────────────────────────────────────────────

  function handleCellChange(field: string, customer: string, value: string) {
    update({ data: { ...data, [field]: { ...data[field], [customer]: value } } });
  }

  function handleCheckboxChange(field: string, customer: string, checked: boolean) {
    update({ data: { ...data, [field]: { ...data[field], [customer]: checked ? 'TRUE' : '' } } });
  }

  function handleDeleteField(idx: number) {
    const field = fields[idx];
    const newFields = fields.filter((_, i) => i !== idx);
    const newData = { ...data };
    delete newData[field];
    update({ fields: newFields, data: newData });
  }

  function handleAddCustomer() {
    const label = `CUST${customers.length + 1}`;
    const newData = { ...data };
    for (const f of fields) newData[f] = { ...newData[f], [label]: '' };
    update({ customers: [...customers, label], data: newData });
  }

  function handleCustomerHandleChange(idx: number, value: string) {
    const old = customers[idx];
    const newCustomers = [...customers];
    newCustomers[idx] = value;
    const newData: CellMap = {};
    for (const f of fields) {
      const fd = { ...data[f] };
      fd[value] = fd[old] || '';
      if (old !== value) delete fd[old];
      newData[f] = fd;
    }
    update({ customers: newCustomers, data: newData });
  }

  function handleDeleteCustomer(idx: number) {
    const name = customers[idx];
    const newCustomers = customers.filter((_, i) => i !== idx);
    const newData: CellMap = {};
    for (const f of fields) {
      const fd = { ...data[f] };
      delete fd[name];
      newData[f] = fd;
    }
    update({ customers: newCustomers, data: newData });
  }

  // ── Progress stats ──────────────────────────────────────────────────────────
  // Count checked tasks per customer for the progress indicator
  function getProgress(customer: string): string {
    let done = 0, total = 0;
    for (const f of fields) {
      if (!CHECKBOX_FIELDS.has(f)) continue;
      total++;
      if (data[f]?.[customer] === 'TRUE') done++;
    }
    return total ? `${done}/${total}` : '';
  }

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={() => setShowPasteModal(true)}
        >
          Load from 123.net
        </button>
        <div className={styles.divider} />
        <label className={`${styles.btn} ${styles.fileLabel}`}>
          Import CSV
          <input type="file" accept=".csv" title="Import order tracker CSV"
            onChange={handleImport} className={styles.downloadLink} />
        </label>
        <button type="button" className={styles.btn} onClick={handleExport}>Export CSV</button>
        <button type="button" className={styles.btn} onClick={handleAddCustomer}>+ Add Column</button>
        <button type="button" className={`${styles.btn} ${styles.btnDanger}`} onClick={handleReset}>Clear All</button>
        <a ref={downloadRef} className={styles.downloadLink}>Download</a>
      </div>

      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.thField}>Field</th>
              {customers.map((c, i) => {
                const prog = getProgress(c);
                return (
                  <th key={i} className={styles.thCustomer}>
                    <div className={styles.thCustomerInner}>
                      <div className={styles.thCustomerTop}>
                        <input
                          type="text"
                          className={styles.handleInput}
                          value={c}
                          onChange={e => handleCustomerHandleChange(i, e.target.value)}
                          placeholder="Handle"
                          title={`Customer ${i + 1} handle`}
                        />
                        {customers.length > 1 && (
                          <button type="button" className={styles.deleteColBtn}
                            onClick={() => handleDeleteCustomer(i)}
                            title={`Delete column ${c || i + 1}`}>×</button>
                        )}
                      </div>
                      {prog && <span className={styles.progress}>{prog}</span>}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {fields.map((field, i) => {
              const isSection = SECTION_HEADER_FIELDS.has(field);
              return (
                <tr key={field} className={isSection ? styles.sectionRow : undefined}>
                  <td className={styles.tdField}>
                    {field}
                    {!isSection && fields.length > 1 && (
                      <button type="button" className={styles.deleteFieldBtn}
                        onClick={() => handleDeleteField(i)}
                        title={`Delete field: ${field}`}>×</button>
                    )}
                  </td>
                  {customers.map(cust => (
                    <td key={cust} className={isSection ? styles.tdSection : styles.tdCell}>
                      {!isSection && CHECKBOX_FIELDS.has(field) ? (
                        <input
                          type="checkbox"
                          title={`${field} — ${cust || `col ${customers.indexOf(cust) + 1}`}`}
                          checked={data[field]?.[cust] === 'TRUE'}
                          onChange={e => handleCheckboxChange(field, cust, e.target.checked)}
                        />
                      ) : !isSection ? (
                        <input
                          type="text"
                          className={styles.cellInput}
                          title={`${field} — ${cust || `col ${customers.indexOf(cust) + 1}`}`}
                          value={data[field]?.[cust] || ''}
                          onChange={e => handleCellChange(field, cust, e.target.value)}
                        />
                      ) : null}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Paste Modal ──────────────────────────────────────────────────────── */}
      {showPasteModal && (
        <div className={styles.modalBackdrop} onClick={() => setShowPasteModal(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <span className={styles.modalTitle}>Load Orders from 123.net</span>
              <button type="button" className={styles.modalClose}
                onClick={() => setShowPasteModal(false)}>×</button>
            </div>

            <div className={styles.modalBody}>
              <p className={styles.modalInstructions}>
                1. Go to{' '}
                <a href={ORDERS_ADMIN_URL} target="_blank" rel="noreferrer"
                  className={styles.modalLink}>
                  123.net Orders Web Admin
                </a>{' '}
                and open the <strong>Man-Hour Summary</strong> report.
                <br />
                2. Select all the text on that page, copy it, and paste it below.
                <br />
                3. Only orders where <strong>PM = </strong>
                <code className={styles.code}>{pasteFilter}</code> will be imported.
              </p>

              <div className={styles.filterRow}>
                <label className={styles.filterLabel}>Filter PM username:</label>
                <input
                  type="text"
                  className={styles.filterInput}
                  value={pasteFilter}
                  onChange={e => handleFilterChange(e.target.value)}
                  placeholder="e.g. tjohnson"
                />
              </div>

              <textarea
                ref={textareaRef}
                className={styles.pasteArea}
                placeholder={`Paste the Man-Hour Summary text here...\n\nExpected format:\nPM,Order ID,Bill Date, Closed Date, Bill MRC\ntjohnson,WS7-XXXXXXXX,2026-04-01,2026-04-15,500.00`}
                value={pasteText}
                onChange={e => handlePasteTextChange(e.target.value)}
                rows={12}
              />

              {pasteStatus && (
                <p className={pastePreview.length ? styles.statusOk : styles.statusErr}>
                  {pasteStatus}
                </p>
              )}

              {pastePreview.length > 0 && (
                <div className={styles.previewWrap}>
                  <table className={styles.previewTable}>
                    <thead>
                      <tr>
                        <th>Order ID</th>
                        <th>Bill Date</th>
                        <th>Closed Date</th>
                        <th>MRC</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pastePreview.map(o => (
                        <tr key={o.orderId}>
                          <td><strong>{o.orderId}</strong></td>
                          <td>{o.billDate}</td>
                          <td>{o.closedDate}</td>
                          <td>{o.billMrc ? `$${o.billMrc}` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className={styles.modalFooter}>
              <button type="button" className={styles.btn}
                onClick={() => setShowPasteModal(false)}>Cancel</button>
              <button
                type="button"
                className={`${styles.btn} ${styles.btnPrimary}`}
                disabled={!pastePreview.length}
                onClick={applyParsedOrders}
              >
                Add {pastePreview.length || 0} Order{pastePreview.length !== 1 ? 's' : ''} to Tracker
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default HostedOrderTrackerTab;
