import React, { useState, useRef, useEffect } from 'react';
import * as Papa from 'papaparse';
import styles from './HostedOrderTrackerTab.module.css';

const SCRAPER_BASE = (import.meta.env.VITE_SCRAPER_BASE as string | undefined) || 'http://localhost:8788';
const HUMAN_CONFIRM_KEY = (import.meta.env.VITE_HUMAN_CONFIRM_KEY as string | undefined) || '';

const DEFAULT_FIELDS = [
  'CUSTOMER ABBREV', 'CUSTOMER NAME', 'LOCATION', 'DEPLOY FROM (SF/GR)', 'ENGINEER',
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

const SECTION_HEADER_FIELDS = new Set(['ORDER TASKS', 'TURN UP DAY TASKS']);

const STORAGE_KEY = 'order_tracker_v1';
const DEFAULT_ENGINEER = 'tjohnson';
const ORDERS_ADMIN_URL = 'https://secure.123.net/cgi-bin/web_interface/admin/orders_web_admin.cgi';

// Maps DB column names ↔ UI field labels
const DB_TO_UI: Record<string, string> = {
  customer_abbrev: 'CUSTOMER ABBREV',
  customer_name:   'CUSTOMER NAME',
  location:        'LOCATION',
  engineer:        'ENGINEER',
  dispatch_date:   'INSTALL DATE',
  on_net_ott:      'ON-NET or OTT',
  order_id:        'ORDER ID',
  pon:             'PON',
  detail_url:      'LINK TO CONTRACT',
  seats:           '# SEATS MINIMUM',
  pbx_ip:          'PBX IP ADDRESS',
  phone_model:     'PHONE MODEL / QTY',
  install_type:    'PBX TYPE',
};
const UI_TO_DB = Object.fromEntries(Object.entries(DB_TO_UI).map(([k, v]) => [v, k]));

type CellMap = { [field: string]: { [customer: string]: string } };
type SuggestionMap = Record<string, Record<string, string>>;

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

// Merge API order list into tracker state — fills only empty cells, preserves existing data
function mergeApiOrders(prev: TrackerState, items: Record<string, string>[]): TrackerState {
  const newCustomers = [...prev.customers];
  const newData: CellMap = {};
  for (const f of prev.fields) newData[f] = { ...(prev.data[f] || {}) };

  for (const order of items) {
    const orderId = order.order_id;
    if (!orderId) continue;

    if (!newCustomers.includes(orderId)) {
      // Replace first truly empty placeholder column (all cells blank)
      const placeholderIdx = newCustomers.findIndex(c =>
        /^CUST\d+$/.test(c) && prev.fields.every(f => !(prev.data[f]?.[c] || '').trim())
      );
      if (placeholderIdx !== -1) newCustomers[placeholderIdx] = orderId;
      else newCustomers.push(orderId);
    }

    // Only fill cells that are currently empty
    for (const [dbField, uiField] of Object.entries(DB_TO_UI)) {
      if (!newData[uiField]) continue;
      if (!(newData[uiField][orderId] || '').trim() && order[dbField]) {
        newData[uiField][orderId] = String(order[dbField]);
      }
    }
  }

  return { ...prev, customers: newCustomers, data: newData };
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
  const headerIdx = lines.findIndex(l => /^(PM|Engineer)[\s,]/i.test(l) && /Order\s*ID/i.test(l));
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
  const [pasteFilter, setPasteFilter] = useState(DEFAULT_ENGINEER);
  const [pastePreview, setPastePreview] = useState<ParsedOrder[]>([]);
  const [pasteStatus, setPasteStatus] = useState('');

  // API state
  const [apiSuggestions, setApiSuggestions] = useState<SuggestionMap>({});
  const [completenessStats, setCompletenessStats] = useState<{
    total_orders: number;
    missing_by_field: Record<string, number>;
  } | null>(null);
  const [showReviewQueue, setShowReviewQueue] = useState(false);
  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const downloadRef = useRef<HTMLAnchorElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { saveState(state); }, [state]);

  useEffect(() => {
    if (showPasteModal) setTimeout(() => textareaRef.current?.focus(), 50);
  }, [showPasteModal]);

  // Load orders and suggestions from API — callable on mount and by the refresh button
  const loadFromApi = React.useCallback(async () => {
    setApiLoading(true);
    setApiError(null);
    try {
      const listRes = await fetch(
        `${SCRAPER_BASE}/api/orders?engineer=${encodeURIComponent(DEFAULT_ENGINEER)}`
      );
      if (!listRes.ok) throw new Error(`HTTP ${listRes.status}`);
      const { items } = await listRes.json() as { items: Record<string, string>[] };
      setState(prev => mergeApiOrders(prev, items));

      const orderIds = items.map(o => o.order_id).filter(Boolean);
      const detailResults = await Promise.allSettled(
        orderIds.map(id =>
          fetch(`${SCRAPER_BASE}/api/orders/${encodeURIComponent(id)}`).then(r => r.json())
        )
      );
      const newSuggestions: SuggestionMap = {};
      for (const res of detailResults) {
        if (res.status !== 'fulfilled') continue;
        const order = res.value as Record<string, unknown>;
        const orderId = order.order_id as string;
        const suggested = order._suggested as Record<string, string> | undefined;
        if (suggested && orderId) {
          const valid = Object.fromEntries(
            Object.entries(suggested).filter(([k]) => k in DB_TO_UI)
          );
          if (Object.keys(valid).length) newSuggestions[orderId] = valid;
        }
      }
      setApiSuggestions(newSuggestions);

      const summaryRes = await fetch(`${SCRAPER_BASE}/api/orders/incomplete/summary`);
      if (summaryRes.ok) setCompletenessStats(await summaryRes.json());
    } catch (e) {
      setApiError(String(e));
    } finally {
      setApiLoading(false);
    }
  }, []);

  useEffect(() => { loadFromApi(); }, [loadFromApi]);

  function update(patch: Partial<TrackerState>) {
    setState(prev => ({ ...prev, ...patch }));
  }

  // ── Accept / dismiss suggestion ────────────────────────────────────────────

  async function handleAcceptSuggestion(orderId: string, dbField: string) {
    const r = await fetch(
      `${SCRAPER_BASE}/api/orders/${encodeURIComponent(orderId)}/confirm`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Human-Confirm': HUMAN_CONFIRM_KEY },
        body: JSON.stringify({ field: dbField, reviewed_by: DEFAULT_ENGINEER }),
      }
    ).catch(e => { alert(`Network error: ${e}`); return null; });
    if (!r) return;
    if (!r.ok) {
      const err = await r.json().catch(() => ({})) as Record<string, string>;
      alert(`Confirm failed: ${err.detail || r.status}`);
      return;
    }
    const { confirmed_value } = await r.json() as { confirmed_value: string };
    const uiField = DB_TO_UI[dbField];
    if (uiField) {
      setState(prev => ({
        ...prev,
        data: { ...prev.data, [uiField]: { ...prev.data[uiField], [orderId]: confirmed_value } },
      }));
    }
    setApiSuggestions(prev => dropSuggestion(prev, orderId, dbField));
  }

  function handleDismissSuggestion(orderId: string, dbField: string) {
    setApiSuggestions(prev => dropSuggestion(prev, orderId, dbField));
  }

  function dropSuggestion(prev: SuggestionMap, orderId: string, dbField: string): SuggestionMap {
    const next = { ...prev };
    if (next[orderId]) {
      next[orderId] = { ...next[orderId] };
      delete next[orderId][dbField];
      if (!Object.keys(next[orderId]).length) delete next[orderId];
    }
    return next;
  }

  // ── Paste modal ────────────────────────────────────────────────────────────

  function handlePasteTextChange(text: string) {
    setPasteText(text);
    if (!text.trim()) { setPastePreview([]); setPasteStatus(''); return; }
    const orders = parseManhourSummary(text, pasteFilter);
    setPastePreview(orders);
    setPasteStatus(orders.length
      ? `Found ${orders.length} order${orders.length !== 1 ? 's' : ''} for Engineer "${pasteFilter}".`
      : `No orders found for Engineer "${pasteFilter}" in this data.`);
  }

  function handleFilterChange(pm: string) {
    setPasteFilter(pm);
    if (!pasteText.trim()) { setPastePreview([]); setPasteStatus(''); return; }
    const orders = parseManhourSummary(pasteText, pm);
    setPastePreview(orders);
    setPasteStatus(orders.length
      ? `Found ${orders.length} order${orders.length !== 1 ? 's' : ''} for Engineer "${pm}".`
      : `No orders found for Engineer "${pm}" in this data.`);
  }

  function applyParsedOrders() {
    if (!pastePreview.length) return;

    const existingOrders = new Set(customers.filter(c => !c.match(/^CUST\d+$/)));
    const toAdd = pastePreview.filter(o => !existingOrders.has(o.orderId));

    if (!toAdd.length) {
      setPasteStatus('All found orders are already in the tracker.');
      return;
    }

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
      newData['ENGINEER'][col]         = order.pm;
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

  function getProgress(customer: string): string {
    let done = 0, total = 0;
    for (const f of fields) {
      if (!CHECKBOX_FIELDS.has(f)) continue;
      total++;
      if (data[f]?.[customer] === 'TRUE') done++;
    }
    return total ? `${done}/${total}` : '';
  }

  // ── Derived display values ──────────────────────────────────────────────────

  const pendingSuggestionCount = Object.values(apiSuggestions).reduce(
    (sum, fieldMap) => sum + Object.keys(fieldMap).length, 0
  );

  const visibleCustomers = showReviewQueue
    ? customers.filter(c => apiSuggestions[c] && Object.keys(apiSuggestions[c]).length > 0)
    : customers;

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={() => loadFromApi()}
          disabled={apiLoading}
        >
          {apiLoading ? 'Loading…' : 'Load from 123.net'}
        </button>
        <div className={styles.divider} />
        <button
          type="button"
          className={styles.btn}
          onClick={() => setShowPasteModal(true)}
          title="Manually paste Man-Hour Summary text to import orders"
        >
          Paste Import
        </button>
        <label className={`${styles.btn} ${styles.fileLabel}`}>
          Import CSV
          <input type="file" accept=".csv" title="Import order tracker CSV"
            onChange={handleImport} className={styles.downloadLink} />
        </label>
        <button type="button" className={styles.btn} onClick={handleExport}>Export CSV</button>
        <button type="button" className={styles.btn} onClick={handleAddCustomer}>+ Add Column</button>
        <button type="button" className={`${styles.btn} ${styles.btnDanger}`} onClick={handleReset}>Clear All</button>
        <div className={styles.divider} />
        <button
          type="button"
          className={`${styles.btn} ${showReviewQueue ? styles.btnPrimary : ''}`}
          onClick={() => setShowReviewQueue(v => !v)}
          title={showReviewQueue ? 'Show all orders' : 'Show only orders with AI suggestions'}
        >
          {pendingSuggestionCount > 0
            ? `Review AI (${pendingSuggestionCount})`
            : 'Review AI'}
        </button>
        {apiLoading && <span className={styles.apiStatus}>Syncing...</span>}
        {apiError && (
          <span className={styles.apiStatusErr} title={apiError}>⚠ API error</span>
        )}
        <a ref={downloadRef} className={styles.downloadLink}>Download</a>
      </div>

      {completenessStats && completenessStats.total_orders > 0 && (
        <div className={styles.completenessBar}>
          <span className={styles.completenessTitle}>
            {completenessStats.total_orders} orders in DB
          </span>
          {Object.entries(completenessStats.missing_by_field)
            .filter(([, count]) => count > 0)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 6)
            .map(([field, count]) => (
              <span key={field} className={styles.completenessField}>
                {DB_TO_UI[field] || field}: <strong>{count}</strong> missing
              </span>
            ))}
        </div>
      )}

      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.thField}>Field</th>
              {visibleCustomers.map((c, i) => {
                const prog = getProgress(c);
                const hasSuggestions = !!(apiSuggestions[c] && Object.keys(apiSuggestions[c]).length);
                return (
                  <th key={i} className={`${styles.thCustomer}${hasSuggestions ? ` ${styles.thHasSuggestions}` : ''}`}>
                    <div className={styles.thCustomerInner}>
                      <div className={styles.thCustomerTop}>
                        <input
                          type="text"
                          className={styles.handleInput}
                          value={c}
                          onChange={e => handleCustomerHandleChange(customers.indexOf(c), e.target.value)}
                          placeholder="Handle"
                          title={`Customer handle`}
                        />
                        {customers.length > 1 && (
                          <button type="button" className={styles.deleteColBtn}
                            onClick={() => handleDeleteCustomer(customers.indexOf(c))}
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
              const dbField = UI_TO_DB[field];
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
                  {visibleCustomers.map(cust => {
                    const suggestion = dbField ? apiSuggestions[cust]?.[dbField] : undefined;
                    return (
                      <td key={cust} className={isSection ? styles.tdSection : styles.tdCell}>
                        {!isSection && CHECKBOX_FIELDS.has(field) ? (
                          <input
                            type="checkbox"
                            title={`${field} — ${cust}`}
                            checked={data[field]?.[cust] === 'TRUE'}
                            onChange={e => handleCheckboxChange(field, cust, e.target.checked)}
                          />
                        ) : !isSection ? (
                          suggestion ? (
                            <div className={styles.suggestionCell}>
                              <input
                                type="text"
                                className={styles.cellInput}
                                title={`${field} — ${cust}`}
                                value={data[field]?.[cust] || ''}
                                onChange={e => handleCellChange(field, cust, e.target.value)}
                              />
                              <div className={styles.suggestionOverlay}>
                                <span className={styles.suggestionBadge}>AI</span>
                                <span className={styles.suggestionValue} title={suggestion}>{suggestion}</span>
                                <button
                                  type="button"
                                  className={styles.acceptBtn}
                                  title="Accept this suggestion"
                                  onClick={() => void handleAcceptSuggestion(cust, dbField!)}
                                >✓</button>
                                <button
                                  type="button"
                                  className={styles.dismissBtn}
                                  title="Dismiss this suggestion"
                                  onClick={() => handleDismissSuggestion(cust, dbField!)}
                                >×</button>
                              </div>
                            </div>
                          ) : (
                            <input
                              type="text"
                              className={styles.cellInput}
                              title={`${field} — ${cust}`}
                              value={data[field]?.[cust] || ''}
                              onChange={e => handleCellChange(field, cust, e.target.value)}
                            />
                          )
                        ) : null}
                      </td>
                    );
                  })}
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
                3. Only orders where <strong>Engineer = </strong>
                <code className={styles.code}>{pasteFilter}</code> will be imported.
              </p>

              <div className={styles.filterRow}>
                <label className={styles.filterLabel}>Filter Engineer username:</label>
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
                placeholder={`Paste the Man-Hour Summary text here...\n\nExpected format:\nEngineer,Order ID,Bill Date, Closed Date, Bill MRC\ntjohnson,WS7-XXXXXXXX,2026-04-01,2026-04-15,500.00`}
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
