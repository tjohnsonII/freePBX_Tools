/**
 * FbpxImportTab.tsx
 * FreePBX extension import table — step 2 of the workflow.
 *
 * Receives data from:  copyUserExtensions (via localStorage)
 * Pushes data to:      vpbx (via localStorage), stretto (via localStorage)
 *
 * Toolbar actions:
 *   Clear | Import CSV | Export CSV
 *   Populate Fields | Generate Secrets | Clean Outbound CID
 *   ← Receive from copyUserExtensions
 *   Mirror to VPBX → | Populate Stretto →
 */
import React, { useEffect, useRef, useState } from 'react';
import * as Papa from 'papaparse';
import styles from './ImportTable.module.css';
import ImportTable from './ImportTable';
import {
  FPBX_FIELDS,
  cleanFpbxOutboundCid,
  emptyFpbxRow,
  exportCsv,
  generateFpbxSecrets,
  loadStore,
  populateFpbxFields,
  populateFpbxFromCopyUsers,
  populateStrettoFromFpbx,
  populateVpbxFromFpbx,
  saveStore,
  type AnyRow,
  type CopyUserRow,
  type FpbxRow,
  type VpbxRow,
} from '../data/importStore';

const WIDE_FIELDS = ['name', 'description', 'voicemail_email', 'voicemail_options', 'dial'] as const;

export default function FbpxImportTab() {
  const [rows, setRows] = useState<FpbxRow[]>(() => {
    const saved = loadStore('fpbx') as FpbxRow[] | null;
    return saved?.length ? saved : Array(5).fill(null).map(emptyFpbxRow);
  });
  const [sipDomain, setSipDomain] = useState('');
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    saveStore('fpbx', rows as AnyRow[]);
  }, [rows]);

  function handleChange(i: number, field: string, value: string) {
    setRows(prev => {
      const next = [...prev];
      next[i] = { ...next[i], [field]: value };
      return next;
    });
  }

  function handleDeleteRow(i: number) {
    setRows(prev => prev.filter((_, idx) => idx !== i));
  }

  function handleAddRow() {
    setRows(prev => [...prev, emptyFpbxRow()]);
  }

  function handleClear() {
    if (!confirm('Clear all FPBX rows?')) return;
    const blank = Array(5).fill(null).map(emptyFpbxRow);
    setRows(blank);
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
          const row = emptyFpbxRow();
          FPBX_FIELDS.forEach(f => { row[f] = r[f] ?? ''; });
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
    exportCsv('fpbx_import.csv', FPBX_FIELDS, rows as AnyRow[]);
  }

  function handlePopulateFields() {
    setRows(populateFpbxFields(rows));
    setStatus({ msg: 'Fields populated.', ok: true });
  }

  function handleGenerateSecrets() {
    setRows(generateFpbxSecrets(rows));
    setStatus({ msg: 'Secrets generated.', ok: true });
  }

  function handleCleanCid() {
    setRows(cleanFpbxOutboundCid(rows));
    setStatus({ msg: 'Outbound CIDs cleaned.', ok: true });
  }

  function handleReceiveFromCopyUsers() {
    const copyUsers = loadStore('copyUsers') as CopyUserRow[] | null;
    if (!copyUsers?.length) {
      setStatus({ msg: 'No copyUserExtensions data found. Populate that tab first.', ok: false });
      return;
    }
    const fpbxRows = populateFpbxFields(populateFpbxFromCopyUsers(copyUsers));
    setRows(fpbxRows);
    setStatus({ msg: `Loaded ${fpbxRows.length} row(s) from copyUserExtensions.`, ok: true });
  }

  function handleMirrorToVpbx() {
    const existing = (loadStore('vpbx') as VpbxRow[] | null) ?? [];
    const vpbxRows = populateVpbxFromFpbx(rows, existing);
    saveStore('vpbx', vpbxRows as AnyRow[]);
    setStatus({ msg: `Mirrored ${vpbxRows.length} row(s) to VPBX. Switch to the VPBX Import tab.`, ok: true });
  }

  function handlePopulateStretto() {
    if (!sipDomain.trim()) {
      setStatus({ msg: 'Enter a SIP domain first.', ok: false });
      return;
    }
    const strRows = populateStrettoFromFpbx(rows, sipDomain.trim());
    saveStore('stretto', strRows as AnyRow[]);
    setStatus({ msg: `Populated Stretto with ${strRows.length} row(s). Switch to the Stretto Import tab.`, ok: true });
  }

  return (
    <div>
      {/* Row 1: file ops + clear */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarGroup}>
          <button className={styles.btnDanger} onClick={handleClear}>Clear</button>
          <div className={styles.toolbarDivider} />
          <label className={styles.btn} style={{ cursor: 'pointer' }}>
            Import CSV
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={handleImport}
            />
          </label>
          <button className={styles.btn} onClick={handleExport}>Export CSV</button>
        </div>
        <div className={styles.toolbarDivider} />
        {/* Row 1: compute actions */}
        <div className={styles.toolbarGroup}>
          <button className={styles.btn} onClick={handlePopulateFields}>Populate Fields</button>
          <button className={styles.btn} onClick={handleGenerateSecrets}>Generate Secrets</button>
          <button className={styles.btn} onClick={handleCleanCid}>Clean Outbound CID</button>
        </div>
        {status && (
          <span className={status.ok ? styles.statusOk : styles.statusErr}>
            {status.msg}
          </span>
        )}
      </div>

      {/* Row 2: workflow cross-tab actions */}
      <div className={styles.toolbar} style={{ marginBottom: 10 }}>
        <div className={styles.toolbarGroup}>
          <button className={styles.btnPrimary} onClick={handleReceiveFromCopyUsers}>
            ← Receive from copyUserExtensions
          </button>
        </div>
        <div className={styles.toolbarDivider} />
        <div className={styles.toolbarGroup}>
          <button className={styles.btnPrimary} onClick={handleMirrorToVpbx}>
            Mirror to VPBX →
          </button>
        </div>
        <div className={styles.toolbarDivider} />
        <div className={styles.toolbarGroup}>
          <input
            type="text"
            placeholder="SIP domain (e.g. pbx.example.com)"
            value={sipDomain}
            onChange={e => setSipDomain(e.target.value)}
            title="SIP domain for Stretto import"
            style={{
              padding: '4px 8px',
              fontSize: 12,
              border: '1px solid var(--app-border)',
              borderRadius: 4,
              background: 'var(--app-surface)',
              color: 'var(--app-fg)',
              minWidth: 220,
            }}
          />
          <button className={styles.btnPrimary} onClick={handlePopulateStretto}>
            Populate Stretto →
          </button>
        </div>
      </div>

      <ImportTable
        fields={FPBX_FIELDS}
        rows={rows as AnyRow[]}
        onChange={handleChange}
        onDeleteRow={handleDeleteRow}
        onAddRow={handleAddRow}
        wideFields={WIDE_FIELDS}
      />
    </div>
  );
}
