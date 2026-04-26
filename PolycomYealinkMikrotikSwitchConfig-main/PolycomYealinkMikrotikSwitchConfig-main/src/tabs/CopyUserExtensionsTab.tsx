/**
 * CopyUserExtensionsTab.tsx
 * Source of the import workflow: copyUserExtensions → fpbx → vpbx → stretto_import
 *
 * Columns: User Name, Extension Number, Email, Direct Inward Dial,
 *          Caller ID Number, SBS Account?, Softphone Required?
 *
 * Buttons: Clear, Import CSV, Export CSV, Populate FPBX
 */
import React, { useEffect, useRef, useState } from 'react';
import * as Papa from 'papaparse';
import styles from './ImportTable.module.css';
import ImportTable from './ImportTable';
import {
  COPY_USER_FIELDS,
  COPY_USER_HEADERS,
  emptyCopyUserRow,
  exportCsv,
  loadStore,
  populateFpbxFromCopyUsers,
  populateFpbxFields,
  saveStore,
  type AnyRow,
  type CopyUserRow,
} from '../data/importStore';

const WIDE = ['userName', 'email', 'directInwardDial'] as const;

const DISPLAY_HEADERS: Record<string, string> = {
  ...COPY_USER_HEADERS,
  sbsAccount: 'SMS Required?',
  softphoneRequired: 'Softphone Account?',
};

export default function CopyUserExtensionsTab() {
  const [rows, setRows] = useState<CopyUserRow[]>(() => {
    const saved = loadStore('copyUsers') as CopyUserRow[] | null;
    return saved?.length ? saved : Array(200).fill(null).map(emptyCopyUserRow);
  });
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Persist on change
  useEffect(() => {
    saveStore('copyUsers', rows as AnyRow[]);
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
    setRows(prev => [...prev, emptyCopyUserRow()]);
  }

  function handleClear() {
    if (!confirm('Clear all rows?')) return;
    const blank = Array(200).fill(null).map(emptyCopyUserRow);
    setRows(blank);
    saveStore('copyUsers', blank as AnyRow[]);
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
          const row = emptyCopyUserRow();
          COPY_USER_FIELDS.forEach(f => {
            row[f] = r[f] ?? r[COPY_USER_HEADERS[f]] ?? '';
          });
          return row;
        });
        setRows(imported);
        setStatus({ msg: `Imported ${imported.length} row(s).`, ok: true });
        if (fileRef.current) fileRef.current.value = '';
      },
      error() {
        setStatus({ msg: 'CSV parse error.', ok: false });
      },
    });
  }

  function handleExport() {
    exportCsv('copyUserExtensions.csv', COPY_USER_FIELDS, rows as AnyRow[]);
  }

  function handleCleanDids() {
    setRows(prev => prev.map(row => ({
      ...row,
      directInwardDial: row.directInwardDial.replace(/\D/g, ''),
    })));
    setStatus({ msg: 'DIDs cleaned — special characters removed.', ok: true });
  }

  function handlePopulateFpbx() {
    const fpbxRows = populateFpbxFields(populateFpbxFromCopyUsers(rows));
    saveStore('fpbx', fpbxRows as AnyRow[]);
    setStatus({ msg: `Populated FPBX with ${fpbxRows.length} row(s). Switch to the FBPX Import tab.`, ok: true });
  }

  return (
    <div>
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
          <div className={styles.toolbarDivider} />
          <button className={styles.btn} onClick={handleCleanDids} title="Strip all non-digit characters from the Direct Inward Dial column">
            Clean DIDs
          </button>
        </div>
        <div className={styles.toolbarDivider} />
        <div className={styles.toolbarGroup}>
          <button className={styles.btnPrimary} onClick={handlePopulateFpbx}>
            Populate FPBX →
          </button>
        </div>
        {status && (
          <span className={status.ok ? styles.statusOk : styles.statusErr}>
            {status.msg}
          </span>
        )}
      </div>

      <ImportTable
        fields={COPY_USER_FIELDS}
        headers={DISPLAY_HEADERS}
        rows={rows as AnyRow[]}
        onChange={handleChange}
        onDeleteRow={handleDeleteRow}
        onAddRow={handleAddRow}
        wideFields={WIDE}
      />
    </div>
  );
}
