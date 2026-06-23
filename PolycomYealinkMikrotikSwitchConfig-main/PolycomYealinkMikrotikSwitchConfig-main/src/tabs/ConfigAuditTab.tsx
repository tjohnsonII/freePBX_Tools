import { useEffect, useMemo, useState } from 'react';
import styles from './ConfigAuditTab.module.css';

const SCRAPER_BASE = import.meta.env.VITE_SCRAPER_BASE || 'http://localhost:8788';

type VpbxRecord = { handle: string; name: string; account_status: string; ip: string };
type DeviceConfig = {
  device_id: string; handle: string; directory_name: string; extension: string;
  mac: string; make: string; model: string; site_code: string; bulk_config: string;
  last_seen_utc: string;
};

function parseConfig(raw: string): Map<string, string> {
  const m = new Map<string, string>();
  for (const line of (raw || '').split('\n')) {
    const eq = line.indexOf('=');
    if (eq > 0) m.set(line.slice(0, eq).trim(), line.slice(eq + 1).trim());
  }
  return m;
}

type DiffLine = { key: string; live: string; status: 'ok' | 'missing' | 'changed' };

function auditDevice(device: DeviceConfig, siteIp: string): DiffLine[] {
  const live = parseConfig(device.bulk_config);
  const results: DiffLine[] = [];

  function check(key: string, expected: string | null, label?: string) {
    const k = label || key;
    const liveVal = live.get(key) ?? '';
    if (expected === null) {
      // just report what's there
      results.push({ key: k, live: liveVal || '(not set)', status: liveVal ? 'ok' : 'missing' });
    } else if (!liveVal) {
      results.push({ key: k, live: '(not set)', status: 'missing' });
    } else if (liveVal !== expected) {
      results.push({ key: k, live: `${liveVal} ≠ expected ${expected}`, status: 'changed' });
    } else {
      results.push({ key: k, live: liveVal, status: 'ok' });
    }
  }

  const ext = device.extension || live.get('reg.1.address') || live.get('account.1.label') || '';

  // Check provisioner URL
  const provUrl = live.get('static.auto_provision.server.url') || live.get('autoprovision.server.url') || '';
  results.push({
    key: 'provisioner url',
    live: provUrl || '(not set)',
    status: provUrl.includes('provisioner.123.net') ? 'ok' : provUrl ? 'changed' : 'missing',
  });

  // Check registration
  if (device.make?.toLowerCase().includes('polycom') || device.model?.toLowerCase().startsWith('vvx')) {
    check('reg.1.address', ext);
    check('reg.1.auth.userid', null, 'auth userid');
    check('reg.1.auth.password', null, 'auth password (set)');
    if (siteIp) {
      const regServer = live.get('reg.1.server.1.address') || '';
      results.push({
        key: 'reg server',
        live: regServer || '(not set)',
        status: !regServer ? 'missing' : regServer === siteIp ? 'ok' : 'changed',
      });
    }
  } else {
    // Yealink
    check('account.1.label', ext);
    check('account.1.auth_name', null, 'auth name (set)');
    check('account.1.password', null, 'auth password (set)');
    if (siteIp) {
      const regServer = live.get('account.1.sip_server_host') || '';
      results.push({
        key: 'SIP server',
        live: regServer || '(not set)',
        status: !regServer ? 'missing' : regServer === siteIp ? 'ok' : 'changed',
      });
    }
    check('static.auto_provision.custom.protect', '1', 'auto-provision protect');
  }

  return results;
}

export default function ConfigAuditTab() {
  const [handles, setHandles] = useState<VpbxRecord[]>([]);
  const [selectedHandle, setSelectedHandle] = useState('');
  const [devices, setDevices] = useState<DeviceConfig[]>([]);
  const [siteIp, setSiteIp] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scraperOnline, setScraperOnline] = useState<boolean | null>(null);
  const [expandedDevice, setExpandedDevice] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${SCRAPER_BASE}/api/vpbx/records`, { signal: AbortSignal.timeout(3000) })
      .then(r => r.json())
      .then(data => {
        setScraperOnline(true);
        const items: VpbxRecord[] = data?.items || [];
        setHandles(items.sort((a, b) => a.handle.localeCompare(b.handle)));
      })
      .catch(() => setScraperOnline(false));
  }, []);

  async function loadDevices(handle: string) {
    if (!handle) return;
    setLoading(true);
    setError(null);
    setDevices([]);
    try {
      const [devRes, recRes] = await Promise.all([
        fetch(`${SCRAPER_BASE}/api/vpbx/device-configs?handle=${encodeURIComponent(handle)}`),
        fetch(`${SCRAPER_BASE}/api/vpbx/records`),
      ]);
      const devData = await devRes.json();
      const recData = await recRes.json();
      setDevices(devData?.items || []);
      const rec = (recData?.items || []).find((r: VpbxRecord) => r.handle === handle);
      if (rec?.ip) setSiteIp(rec.ip);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const auditResults = useMemo(() => {
    return devices.map(d => ({
      device: d,
      lines: auditDevice(d, siteIp),
    }));
  }, [devices, siteIp]);

  const statusBadgeCls = (s: DiffLine['status']) =>
    s === 'ok' ? styles.statusBadgeOk : s === 'missing' ? styles.statusBadgeMissing : styles.statusBadgeChanged;

  const summary = useMemo(() => {
    const all = auditResults.flatMap(r => r.lines);
    return {
      total: all.length,
      ok: all.filter(l => l.status === 'ok').length,
      missing: all.filter(l => l.status === 'missing').length,
      changed: all.filter(l => l.status === 'changed').length,
    };
  }, [auditResults]);

  const scraperBadge = scraperOnline === null ? '…'
    : scraperOnline ? '● connected' : '○ offline';

  return (
    <div className={styles.root}>
      <h2>Config Audit</h2>
      <p className={styles.description}>
        Compares live scraped provisioning configs against expected values — flags drift in
        registration, provisioner URL, auth credentials, and server addresses.
      </p>

      <div className={styles.filterBar}>
        <span className={scraperOnline ? styles.connectedBadge : styles.offlineBadge}>
          {scraperBadge}
        </span>
        <label htmlFor="audit-handle" className={styles.fieldLabel}>Handle:</label>
        <select
          id="audit-handle"
          value={selectedHandle}
          onChange={e => { setSelectedHandle(e.target.value); loadDevices(e.target.value); }}
          disabled={!scraperOnline}
          className={styles.handleSelect}
          title="Select a company handle to audit"
        >
          <option value="">— select handle —</option>
          {handles.map(h => (
            <option key={h.handle} value={h.handle}>{h.handle} — {h.name}</option>
          ))}
        </select>
        <label htmlFor="audit-ip" className={styles.fieldLabel}>PBX IP:</label>
        <input
          id="audit-ip"
          type="text"
          value={siteIp}
          onChange={e => setSiteIp(e.target.value)}
          placeholder="auto-filled or override"
          title="PBX/SIP server IP for this site"
          className={styles.ipInput}
        />
      </div>

      {error && <p className={styles.errorText}>{error}</p>}
      {loading && <p className={styles.loadingText}>Loading…</p>}

      {auditResults.length > 0 && (
        <>
          <div className={styles.summaryRow}>
            {[
              { label: 'Total checks', value: summary.total, cls: 'summaryCardValueTotal' },
              { label: '✓ OK', value: summary.ok, cls: 'summaryCardValueOk' },
              { label: '✗ Missing', value: summary.missing, cls: 'summaryCardValueMissing' },
              { label: '⚠ Changed', value: summary.changed, cls: 'summaryCardValueChanged' },
            ].map(s => (
              <div key={s.label} className={styles.summaryCard}>
                <div className={`${styles.summaryCardValue} ${styles[s.cls]}`}>{s.value}</div>
                <div className={styles.summaryCardLabel}>{s.label}</div>
              </div>
            ))}
          </div>

          {auditResults.map(({ device, lines }) => {
            const issues = lines.filter(l => l.status !== 'ok').length;
            const isExpanded = expandedDevice === device.device_id;
            const headerCls = `${styles.deviceHeader} ${issues === 0 ? styles.deviceHeaderClean : issues > 2 ? styles.deviceHeaderError : styles.deviceHeaderWarn}`;
            return (
              <div key={device.device_id} className={styles.deviceRow}>
                <div
                  className={headerCls}
                  onClick={() => setExpandedDevice(isExpanded ? null : device.device_id)}
                >
                  <span className={styles.deviceName}>
                    {device.directory_name || device.device_id}
                  </span>
                  <span className={styles.deviceInfo}>
                    {device.make} {device.model} · ext {device.extension || '?'} · {device.mac || 'no MAC'}
                  </span>
                  <span className={`${styles.deviceIssues} ${issues === 0 ? styles.issueClean : styles.issueDirty}`}>
                    {issues === 0 ? '✓ clean' : `${issues} issue${issues > 1 ? 's' : ''}`}
                  </span>
                  <span className={styles.chevron}>{isExpanded ? '▲' : '▼'}</span>
                </div>

                {isExpanded && (
                  <table className={styles.auditTable}>
                    <thead>
                      <tr>
                        <th className={styles.th}>Check</th>
                        <th className={styles.th}>Live Value</th>
                        <th className={styles.th}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, i) => (
                        <tr key={i} className={styles.tr}>
                          <td className={styles.tdKey}>{l.key}</td>
                          <td className={styles.tdValue}>
                            {l.key.toLowerCase().includes('password') && l.live && l.live !== '(not set)'
                              ? '••••••••'
                              : l.live}
                          </td>
                          <td className={styles.tdStatus}>
                            <span className={`${styles.statusBadge} ${statusBadgeCls(l.status)}`}>
                              {l.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })}
        </>
      )}

      {!loading && selectedHandle && devices.length === 0 && !error && (
        <p className={styles.emptyText}>
          No device configs found for {selectedHandle}. Run the Phone Config Scraper in the webscraper first.
        </p>
      )}
    </div>
  );
}