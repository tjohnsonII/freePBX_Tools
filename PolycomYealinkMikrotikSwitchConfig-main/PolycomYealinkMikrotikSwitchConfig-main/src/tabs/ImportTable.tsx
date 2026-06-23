import React, { useMemo, useRef, useState, useEffect } from 'react';
import { DataGrid, renderTextEditor } from 'react-data-grid';
import type { Column, RenderCellProps } from 'react-data-grid';
import 'react-data-grid/lib/styles.css';
import styles from './ImportTable.module.css';
import type { AnyRow } from '../data/importStore';

interface ImportTableProps {
  fields: readonly string[];
  headers?: Record<string, string>;
  rows: AnyRow[];
  onChange: (rowIndex: number, field: string, value: string) => void;
  onDeleteRow: (rowIndex: number) => void;
  onAddRow: () => void;
  wideFields?: readonly string[];
  selectOptions?: Record<string, string[]>;
}

const ROW_H    = 30;
const HEADER_H = 40;
const MIN_COL  = 72;   // minimum width for a normal column
const MIN_WIDE = 130;  // minimum width for a wide column
const MIN_DEL  = 34;   // delete button column

// Column weight for proportional distribution: wide=2, normal=1, del=0.38
const WIDE_W   = 2;
const NORM_W   = 1;
const DEL_W    = 0.38;

function makeSelectCell(
  options: string[],
  onChangeFn: (rowIdx: number, field: string, value: string) => void,
) {
  return function SelectCell({ row, column, rowIdx }: RenderCellProps<AnyRow>) {
    return (
      <select
        className={styles.gridSelect}
        value={row[column.key] ?? ''}
        onChange={e => onChangeFn(rowIdx, column.key, e.target.value)}
        onClick={e => e.stopPropagation()}
      >
        <option value="">—</option>
        {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
      </select>
    );
  };
}

export default function ImportTable({
  fields,
  headers,
  rows,
  onChange,
  onDeleteRow,
  onAddRow,
  wideFields = [],
  selectOptions = {},
}: ImportTableProps) {
  const wideSet = new Set(wideFields);

  // Measure available width so columns fill the container at any screen size
  const outerRef = useRef<HTMLDivElement>(null);
  const [availWidth, setAvailWidth] = useState(0);

  useEffect(() => {
    const el = outerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setAvailWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const columns = useMemo<Column<AnyRow>[]>(() => {
    const fieldWeights = fields.map(f => wideSet.has(f) ? WIDE_W : NORM_W);
    const totalWeight  = fieldWeights.reduce((s, w) => s + w, 0) + DEL_W;
    const totalMin     = fields.reduce((s, f) => s + (wideSet.has(f) ? MIN_WIDE : MIN_COL), 0) + MIN_DEL;
    const canFill      = availWidth >= totalMin && availWidth > 0;

    const colWidth = (weight: number) =>
      canFill ? Math.max(MIN_COL, Math.floor((weight / totalWeight) * availWidth)) : undefined;

    return [
      ...fields.map((f, i) => {
        const w    = fieldWeights[i];
        const minW = wideSet.has(f) ? MIN_WIDE : MIN_COL;
        const opts = selectOptions[f];
        return {
          key: f,
          name: headers?.[f] ?? f,
          width: colWidth(w) ?? (wideSet.has(f) ? MIN_WIDE : MIN_COL),
          minWidth: minW,
          resizable: true,
          frozen: i === 0,
          ...(opts
            ? { renderCell: makeSelectCell(opts, onChange), renderEditCell: undefined, editable: false }
            : { renderEditCell: renderTextEditor }
          ),
        };
      }),
      {
        key: '__del__',
        name: '',
        width: colWidth(DEL_W) ?? MIN_DEL,
        minWidth: MIN_DEL,
        resizable: false,
        renderEditCell: undefined,
        renderCell: ({ rowIdx }: RenderCellProps<AnyRow>) => (
          <button
            className={styles.deleteBtn}
            title="Delete row"
            onMouseDown={e => { e.stopPropagation(); onDeleteRow(rowIdx); }}
          >
            ✕
          </button>
        ),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields, headers, wideFields, selectOptions, onChange, onDeleteRow, availWidth]);

  function handleRowsChange(newRows: AnyRow[], { indexes }: { indexes: number[] }) {
    for (const i of indexes) {
      const oldRow = rows[i] ?? {};
      const newRow = newRows[i];
      for (const f of fields) {
        if (oldRow[f] !== newRow[f]) onChange(i, f, newRow[f] ?? '');
      }
    }
  }

  // Default height: show ~20 rows worth initially; user drags the handle to see more.
  const defaultHeight = Math.max(200, Math.min(HEADER_H + 20 * ROW_H + 2, HEADER_H + rows.length * ROW_H + 2));

  return (
    <>
      <div ref={outerRef} className={styles.tableOuter}>
        <div className={styles.rdgWrapper} style={{ height: defaultHeight }}>
          <DataGrid
            columns={columns}
            rows={rows}
            onRowsChange={handleRowsChange}
            rowHeight={ROW_H}
            headerRowHeight={HEADER_H}
            style={{ height: '100%', width: '100%' }}
            rowClass={(_, rowIdx) => rowIdx % 2 === 0 ? styles.rowEven : styles.rowOdd}
            enableVirtualization={rows.length > 60}
          />
        </div>
      </div>
      <div style={{ marginTop: 6 }}>
        <button className={styles.btn} onClick={onAddRow}>+ Add Row</button>
      </div>
    </>
  );
}
