import React, { useEffect, useRef, useState } from 'react';
import * as Papa from 'papaparse';
import tableStyles from './tabs/ImportTable.module.css';
import localStyles from './StrettoImportExportTab.module.css';
import ImportTable from './tabs/ImportTable';
import {
  STRETTO_FIELDS,
  emptyStrRow,
  exportCsv,
  loadStore,
  populateStrettoFromFpbx,
  saveStore,
  type AnyRow,
  type FpbxRow,
  type StrRow,
} from './data/importStore';

const WIDE_FIELDS = [
  'username', 'email',
  'account1Sip.credentials.authorizationName',
  'account1Sip.credentials.displayName',
  'account1Sip.credentials.username',
  'account1Sip.domain',
] as const;

const STRETTO_SELECT_OPTIONS: Record<string, string[]> = {
  profile: ['sip.only', 'sip.default'],
};

const StrettoImportExportTab: React.FC = () => {
  const [rows, setRows] = useState<StrRow[]>(() => {
    const saved = loadStore('stretto') as StrRow[] | null;
    return saved?.length ? saved : Array(200).fill(null).map(emptyStrRow);
  });
  const [sipDomain, setSipDomain] = useState('');
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    saveStore('stretto', rows as AnyRow[]);
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
    setRows(prev => [...prev, emptyStrRow()]);
  }

  function handleClear() {
    if (!confirm('Clear all Stretto rows?')) return;
    setRows(Array(200).fill(null).map(emptyStrRow));
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
          const row = emptyStrRow();
          STRETTO_FIELDS.forEach(f => { row[f] = r[f] ?? ''; });
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
    exportCsv('stretto_import.csv', STRETTO_FIELDS, rows as AnyRow[]);
  }

  // Copy account1Sip.credentials.password → password for every row
  function handleCopySecret() {
    setRows(prev => prev.map(r => ({
      ...r,
      password: r['account1Sip.credentials.password'] || r.password,
    })));
    setStatus({ msg: 'SIP credential password copied to portal password column.', ok: true });
  }

  function handlePopulateFromFpbx() {
    if (!sipDomain.trim()) {
      setStatus({ msg: 'Enter a SIP domain first.', ok: false });
      return;
    }
    const fpbxRows = loadStore('fpbx') as FpbxRow[] | null;
    if (!fpbxRows?.length) {
      setStatus({ msg: 'No FPBX data found. Populate the FPBX Import tab first.', ok: false });
      return;
    }
    const strRows = populateStrettoFromFpbx(fpbxRows, sipDomain.trim());
    setRows(strRows);
    setStatus({ msg: `Populated ${strRows.length} row(s) from FPBX.`, ok: true });
  }

  return (
    <div>
      <div className={tableStyles.toolbar}>
        <div className={tableStyles.toolbarGroup}>
          <button type="button" className={tableStyles.btnDanger} onClick={handleClear}>Clear All</button>
          <div className={tableStyles.toolbarDivider} />
          <label className={`${tableStyles.btn} ${localStyles.fileLabel}`}>
            Upload
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className={localStyles.fileInput}
              onChange={handleImport}
            />
          </label>
          <button type="button" className={tableStyles.btnSuccess} onClick={handleExport}>Export To CSV</button>
          <button type="button" className={tableStyles.btn} onClick={handleCopySecret}>Copy Secret</button>
        </div>
        <div className={tableStyles.toolbarDivider} />
        <div className={tableStyles.toolbarGroup}>
          <input
            type="text"
            placeholder="SIP domain (e.g. 69.39.88.78)"
            value={sipDomain}
            onChange={e => setSipDomain(e.target.value)}
            title="SIP domain for Stretto import"
            className={localStyles.sipDomainInput}
          />
          <button type="button" className={tableStyles.btnPrimary} onClick={handlePopulateFromFpbx}>
            Populate Stretto
          </button>
        </div>
        {status && (
          <span className={status.ok ? tableStyles.statusOk : tableStyles.statusErr}>
            {status.msg}
          </span>
        )}
      </div>

      <ImportTable
        fields={STRETTO_FIELDS}
        rows={rows as AnyRow[]}
        onChange={handleChange}
        onDeleteRow={handleDeleteRow}
        onAddRow={handleAddRow}
        wideFields={WIDE_FIELDS}
        selectOptions={STRETTO_SELECT_OPTIONS}
      />
    </div>
  );
};

export default StrettoImportExportTab;
