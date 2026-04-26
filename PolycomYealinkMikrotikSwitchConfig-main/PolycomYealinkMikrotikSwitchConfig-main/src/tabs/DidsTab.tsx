/**
 * DidsTab.tsx
 * Standalone DID routing import table.
 *
 * 15 columns: cidnum, extension, destination, privacyman, mohclass,
 *             description, grppre, delay_answer, pricid,
 *             pmmaxretries, pmmaxlength, reversal, rvolume,
 *             indication_zone, callrecording
 *
 * Toolbar actions:
 *   Clear editable fields | Clean Extensions | Import CSV | Export CSV
 */
import React, { useEffect, useRef, useState } from 'react';
import * as Papa from 'papaparse';
import styles from './ImportTable.module.css';
import ImportTable from './ImportTable';
import {
  DIDS_FIELDS,
  cleanDidExtensions,
  clearDidEditableFields,
  emptyDidRow,
  exportCsv,
  loadStore,
  saveStore,
  type AnyRow,
  type DidRow,
} from '../data/importStore';

const WIDE_FIELDS = ['destination', 'description'] as const;

export default function DidsTab() {
  const [rows, setRows] = useState<DidRow[]>(() => {
    const saved = loadStore('dids') as DidRow[] | null;
    return saved?.length ? saved : Array(200).fill(null).map(emptyDidRow);
  });
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    saveStore('dids', rows as AnyRow[]);
  }, [rows]);

  function handleChange(i: number, field: string, value: string) {
    const cleaned = field === 'extension' ? value.replace(/\D/g, '') : value;
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
    setRows(prev => [...prev, emptyDidRow()]);
  }

  function handleClearEditable() {
    if (!confirm('Clear extension, destination, and description from all rows? (cidnum will be kept)')) return;
    setRows(clearDidEditableFields(rows));
    setStatus({ msg: 'Editable fields cleared.', ok: true });
  }

  function handleCleanExtensions() {
    setRows(cleanDidExtensions(rows));
    setStatus({ msg: 'Extensions cleaned (digits only).', ok: true });
  }

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete(results) {
        const imported = results.data.map(r => {
          const row = emptyDidRow();
          DIDS_FIELDS.forEach(f => { row[f] = r[f] ?? ''; });
          row.extension = row.extension.replace(/\D/g, '');
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
    exportCsv('dids_import.csv', DIDS_FIELDS, rows as AnyRow[]);
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <div className={styles.toolbarGroup}>
          <button className={styles.btnDanger} onClick={handleClearEditable}>Clear</button>
          <button className={styles.btnSuccess} onClick={handleExport}>Export DIDs</button>
          <button className={styles.btn} onClick={handleCleanExtensions}>Clean DIDs</button>
        </div>
        <div className={styles.toolbarDivider} />
        <div className={styles.toolbarGroup}>
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
        </div>
        {status && (
          <span className={status.ok ? styles.statusOk : styles.statusErr}>
            {status.msg}
          </span>
        )}
      </div>

      <ImportTable
        fields={DIDS_FIELDS}
        rows={rows as AnyRow[]}
        onChange={handleChange}
        onDeleteRow={handleDeleteRow}
        onAddRow={handleAddRow}
        wideFields={WIDE_FIELDS}
      />
    </div>
  );
}
