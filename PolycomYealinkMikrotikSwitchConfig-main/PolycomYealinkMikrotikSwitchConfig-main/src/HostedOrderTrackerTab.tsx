import React, { useState, useRef } from 'react';
import * as Papa from 'papaparse';
import styles from './HostedOrderTrackerTab.module.css';

// All fields as rows, columns are customers
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

const HostedOrderTrackerTab: React.FC = () => {
  const [fields, setFields] = useState([...DEFAULT_FIELDS]);
  const [customers, setCustomers] = useState([...DEFAULT_CUSTOMERS]);
  const [data, setData] = useState<{ [field: string]: { [customer: string]: string } }>(
    Object.fromEntries(DEFAULT_FIELDS.map(f => [f, { '': '' }]))
  );
  const downloadRef = useRef<HTMLAnchorElement>(null);

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results: Papa.ParseResult<Record<string, string>>) => {
        const csvData = results.data as Record<string, string>[];
        if (!csvData.length) return;
        const csvFields = csvData.map(row => row['Field'] || row['field'] || Object.values(row)[0]);
        const csvCustomers = Object.keys(csvData[0]).filter(k => k !== 'Field' && k !== 'field');
        const newData: { [field: string]: { [customer: string]: string } } = {};
        csvFields.forEach((f, i) => {
          newData[f] = {};
          csvCustomers.forEach(c => { newData[f][c] = csvData[i][c] || ''; });
        });
        setFields(csvFields);
        setCustomers(csvCustomers);
        setData(newData);
      },
    });
  }

  function handleExport() {
    const csvHeader = ['Field', ...customers].join(',') + '\n';
    const csvRows = fields.map(f =>
      [f, ...customers.map(c => data[f]?.[c] || '')]
        .map(v => `"${(v || '').replace(/"/g, '""')}"`)
        .join(',')
    ).join('\n') + '\n';
    const csv = csvHeader + csvRows;
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    if (downloadRef.current) {
      downloadRef.current.href = url;
      downloadRef.current.download = 'order_tracker.csv';
      downloadRef.current.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  function handleCellChange(field: string, customer: string, value: string) {
    setData(d => ({ ...d, [field]: { ...d[field], [customer]: value } }));
  }

  function handleCheckboxChange(field: string, customer: string, checked: boolean) {
    setData(d => ({ ...d, [field]: { ...d[field], [customer]: checked ? 'TRUE' : 'FALSE' } }));
  }

  function handleDeleteField(idx: number) {
    const field = fields[idx];
    setFields(f => f.filter((_, i) => i !== idx));
    setData(d => {
      const next = { ...d };
      delete next[field];
      return next;
    });
  }

  function handleAddCustomer() {
    setCustomers(custs => [...custs, '']);
    setData(d => {
      const newData = { ...d };
      for (const f of fields) newData[f] = { ...newData[f], ['']: '' };
      return newData;
    });
  }

  function handleCustomerHandleChange(idx: number, value: string) {
    setCustomers(custs => {
      const newCusts = [...custs];
      const old = newCusts[idx];
      newCusts[idx] = value;
      setData(d => {
        const newData = { ...d };
        for (const f of fields) {
          const fieldData = { ...newData[f] };
          fieldData[value] = fieldData[old] || '';
          if (old !== '') delete fieldData[old];
          newData[f] = fieldData;
        }
        return newData;
      });
      return newCusts;
    });
  }

  function handleDeleteCustomer(idx: number) {
    const name = customers[idx];
    setCustomers(custs => custs.filter((_, i) => i !== idx));
    setData(d => {
      const newData = { ...d };
      for (const f of fields) {
        const fieldData = { ...newData[f] };
        delete fieldData[name];
        newData[f] = fieldData;
      }
      return newData;
    });
  }

  return (
    <div className={styles.container}>
      <h2>Hosted Order Tracker</h2>

      <div className={styles.toolbar}>
        <label className={`${styles.btn} ${styles.fileLabel}`}>
          Import CSV
          <input
            type="file"
            accept=".csv"
            title="Import order tracker CSV"
            onChange={handleImport}
            className={styles.downloadLink}
          />
        </label>
        <button type="button" className={styles.btn} onClick={handleExport}>Export CSV</button>
        <button type="button" className={styles.btn} onClick={handleAddCustomer}>+ Add Column</button>
        <a ref={downloadRef} className={styles.downloadLink}>Download</a>
      </div>

      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.thField}>Field</th>
              {customers.map((c, i) => (
                <th key={i} className={styles.thCustomer}>
                  <div className={styles.thCustomerInner}>
                    <input
                      type="text"
                      className={styles.handleInput}
                      value={c}
                      onChange={e => handleCustomerHandleChange(i, e.target.value)}
                      placeholder="Handle (e.g. WS7)"
                      title={`Customer ${i + 1} handle`}
                    />
                    {customers.length > 1 && (
                      <button
                        type="button"
                        className={styles.deleteColBtn}
                        onClick={() => handleDeleteCustomer(i)}
                        title={`Delete customer column ${c || i + 1}`}
                      >
                        ×
                      </button>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fields.map((field, i) => (
              <tr key={field}>
                <td className={styles.tdField}>
                  {field}
                  {fields.length > 1 && (
                    <button
                      type="button"
                      className={styles.deleteFieldBtn}
                      onClick={() => handleDeleteField(i)}
                      title={`Delete field: ${field}`}
                    >
                      ×
                    </button>
                  )}
                </td>
                {customers.map(cust => (
                  <td key={cust} className={styles.tdCell}>
                    {CHECKBOX_FIELDS.has(field) ? (
                      <input
                        type="checkbox"
                        title={`${field} — ${cust || `column ${customers.indexOf(cust) + 1}`}`}
                        checked={data[field]?.[cust] === 'TRUE'}
                        onChange={e => handleCheckboxChange(field, cust, e.target.checked)}
                      />
                    ) : (
                      <input
                        type="text"
                        className={styles.cellInput}
                        title={`${field} — ${cust || `column ${customers.indexOf(cust) + 1}`}`}
                        value={data[field]?.[cust] || ''}
                        onChange={e => handleCellChange(field, cust, e.target.value)}
                      />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default HostedOrderTrackerTab;
