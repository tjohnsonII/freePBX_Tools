import React, { useEffect, useRef, useState } from 'react';
import * as Papa from 'papaparse';
import styles from './ImportTable.module.css';
import ImportTable from './ImportTable';
import {
  IM_NUMBER_FIELDS,
  emptyImNumberRow,
  exportCsv,
  loadStore,
  saveStore,
  type AnyRow,
  type ImNumberRow,
} from '../data/importStore';

const WIDE_FIELDS = ['description', 'destination'] as const;

export default function ImNumberImportTab() {
  const [rows, setRows] = useState<ImNumberRow[]>(() => {
    const saved = loadStore('im_number') as ImNumberRow[] | null;
    return saved?.length ? saved : Array(200).fill(null).map(emptyImNumberRow);
  });
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    saveStore('im_number', rows as AnyRow[]);
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
    setRows(prev => [...prev, emptyImNumberRow()]);
  }

  function handleClear() {
    if (!confirm('Clear all IM Number rows?')) return;
    setRows(Array(200).fill(null).map(emptyImNumberRow));
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
          const row = emptyImNumberRow();
          IM_NUMBER_FIELDS.forEach(f => { row[f] = r[f] ?? ''; });
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
    exportCsv('im_number_import.csv', IM_NUMBER_FIELDS, rows as AnyRow[]);
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <div className={styles.toolbarGroup}>
          <button className={styles.btnDanger} onClick={handleClear}>Clear All</button>
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
          <button className={styles.btnSuccess} onClick={handleExport}>Export CSV</button>
        </div>
        {status && (
          <span className={status.ok ? styles.statusOk : styles.statusErr}>
            {status.msg}
          </span>
        )}
      </div>
      <ImportTable
        fields={IM_NUMBER_FIELDS}
        rows={rows as AnyRow[]}
        onChange={handleChange}
        onDeleteRow={handleDeleteRow}
        onAddRow={handleAddRow}
        wideFields={WIDE_FIELDS}
      />
    </div>
  );
}
