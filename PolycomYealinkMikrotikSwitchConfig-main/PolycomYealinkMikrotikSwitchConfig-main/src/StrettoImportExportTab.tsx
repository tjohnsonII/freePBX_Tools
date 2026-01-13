import React, { useRef, useState } from 'react';
import * as Papa from 'papaparse';

const COLUMNS = [
  'username',
  'password',
  'email',
  'profile',
  'account1Sip.credentials.password',
  'account1Sip.credentials.displayName',
  'account1Sip.credentials.username',
  'account1Sip.domain',
];

type RowType = Record<(typeof COLUMNS)[number], string>;

const StrettoImportExportTab: React.FC = () => {
  // Start with 10 rows by default
  const [rows, setRows] = useState<RowType[]>(Array(10).fill(0).map(() => Object.fromEntries(COLUMNS.map(c => [c, ''])) as RowType));
  const [columns, setColumns] = useState<string[]>([...COLUMNS]);
  const downloadRef = useRef<HTMLAnchorElement>(null);
  const [error, setError] = useState('');

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse(file, {
      header: true,
      complete: (results: Papa.ParseResult<Record<string, string>>) => {
        const validRows = (results.data as RowType[]).filter(
          row => row.username && row['account1Sip.credentials.username']
        );
        setRows(validRows);
        setError(validRows.length < (results.data as RowType[]).length ? 'Some rows were skipped due to missing required fields.' : '');
      },
    });
  }

  function handleExport() {
    const csvHeader = columns.join(',') + '\n';
    const csvRows = rows.map(row =>
      columns.map(col => `"${(row[col] || '').replace(/"/g, '""')}"`).join(',')
    ).join('\n') + '\n';
    const csv = csvHeader + csvRows;
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    if (downloadRef.current) {
      downloadRef.current.href = url;
      downloadRef.current.download = 'stretto_import.csv';
      downloadRef.current.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  // Editable table for Stretto import/export
  function handleCellChange(rowIdx: number, col: string, value: string) {
    setRows(rows => {
      const updated = [...rows];
      updated[rowIdx] = { ...updated[rowIdx], [col]: value };
      return updated;
    });
  }

  function handleAddRows(count = 1) {
    setRows(rows => [...rows, ...Array(count).fill(0).map(() => Object.fromEntries(columns.map(c => [c, ''])) as RowType)]);
  }

  function handleDeleteRow(idx: number) {
    setRows(rows => rows.filter((_, i) => i !== idx));
  }

  // Remove a column (field) from the table
  function handleDeleteColumn(col: string) {
    setColumns(cols => cols.filter(c => c !== col));
    setRows(rows => rows.map(row => {
      const newRow = { ...row };
      delete newRow[col];
      return newRow;
    }));
  }

  return (
    <div>
      <h2>Stretto Import/Export</h2>
      <div style={{ marginBottom: 12 }}>
        <input type="file" accept=".csv" onChange={handleImport} />
        <button type="button" onClick={handleExport} style={{ marginLeft: 8 }}>
          Export as CSV
        </button>
        <button type="button" onClick={() => handleAddRows(1)} style={{ marginLeft: 8 }}>
          Add 1 Row
        </button>
        <button type="button" onClick={() => handleAddRows(5)} style={{ marginLeft: 8 }}>
          Add 5 Rows
        </button>
        <button type="button" onClick={() => handleAddRows(10)} style={{ marginLeft: 8 }}>
          Add 10 Rows
        </button>
        <a ref={downloadRef} style={{ display: 'none' }}>Download</a>
      </div>
      {error && <div style={{ color: 'red', marginBottom: 8 }}>{error}</div>}
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {columns.map(col => (
              <th key={col} style={{ border: '1px solid #ccc', padding: 4, background: '#f4f4f4', position: 'relative' }}>
                {col}
                <button
                  type="button"
                  onClick={() => handleDeleteColumn(col)}
                  style={{ position: 'absolute', top: 2, right: 2, background: 'none', border: 'none', color: 'red', fontWeight: 'bold', cursor: 'pointer' }}
                  title={`Delete column ${col}`}
                >
                  ×
                </button>
              </th>
            ))}
            <th style={{ border: '1px solid #ccc', padding: 4, background: '#f4f4f4' }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length + 1} style={{ textAlign: 'center', padding: 8 }}>
                No data
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i}>
                {columns.map(col => (
                  <td key={col} style={{ border: '1px solid #ccc', padding: 4 }}>
                    <input
                      type="text"
                      value={row[col] || ''}
                      onChange={e => handleCellChange(i, col, e.target.value)}
                      style={{ width: '100%', border: '1px solid #ccc', borderRadius: 4, padding: 4 }}
                    />
                  </td>
                ))}
                <td style={{ border: '1px solid #ccc', padding: 4, textAlign: 'center' }}>
                  <button type="button" onClick={() => handleDeleteRow(i)} style={{ color: 'red' }}>Delete</button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};

export default StrettoImportExportTab;
