/**
 * ImportTable.tsx
 * Shared editable table component used by all import tabs.
 */
import React from 'react';
import styles from './ImportTable.module.css';
import type { AnyRow } from '../data/importStore';

interface ImportTableProps {
  fields: readonly string[];
  /** Optional human-readable header labels keyed by field name */
  headers?: Record<string, string>;
  rows: AnyRow[];
  onChange: (rowIndex: number, field: string, value: string) => void;
  onDeleteRow: (rowIndex: number) => void;
  onAddRow: () => void;
  /** Fields that should render with a wider input */
  wideFields?: readonly string[];
}

export default function ImportTable({
  fields,
  headers,
  rows,
  onChange,
  onDeleteRow,
  onAddRow,
  wideFields = [],
}: ImportTableProps) {
  const wideSet = new Set(wideFields);

  return (
    <>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead className={styles.thead}>
            <tr>
              {fields.map(f => (
                <th key={f} className={styles.th}>
                  {headers?.[f] ?? f}
                </th>
              ))}
              <th className={styles.th} style={{ width: 36 }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={fields.length + 1} className={styles.emptyMsg}>
                  No rows — click Add Row to begin.
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr key={i} className={i % 2 === 0 ? styles.rowEven : styles.rowOdd}>
                  {fields.map(f => (
                    <td key={f} className={styles.tdCell}>
                      <input
                        className={wideSet.has(f) ? styles.cellInputWide : styles.cellInputNarrow}
                        title={headers?.[f] ?? f}
                        value={row[f] ?? ''}
                        onChange={e => onChange(i, f, e.target.value)}
                      />
                    </td>
                  ))}
                  <td className={styles.tdActions}>
                    <button
                      className={styles.deleteBtn}
                      title="Delete row"
                      onClick={() => onDeleteRow(i)}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 6 }}>
        <button className={styles.btn} onClick={onAddRow}>
          + Add Row
        </button>
      </div>
    </>
  );
}
