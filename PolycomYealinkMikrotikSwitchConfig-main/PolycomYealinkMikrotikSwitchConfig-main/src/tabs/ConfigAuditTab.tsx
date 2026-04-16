import { useEffect, useMemo, useState } from 'react';

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

  const statusColor = (s: DiffLine['status']) =>
    s === 'ok' ? '#16794a' : s === 'missing' ? '#b42318' : '#8a5a00';
  const statusBg = (s: DiffLine['status']) =>
    s === 'ok' ? '#e8f7ee' : s === 'missing' ? '#ffecec' : '#fff6e5';

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
    <div style={{ maxWidth: 1100 }}>
      <h2>Config Audit</h2>
      <p style={{ color: '#555', fontSize: 13, marginBottom: 16 }}>
        Compares live scraped provisioning configs against expected values — flags drift in
        registration, provisioner URL, auth credentials, and server addresses.
      </p>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: scraperOnline ? '#16794a' : '#b42318' }}>
          {scraperBadge}
        </span>
        <label htmlFor="audit-handle" style={{ fontWeight: 600, fontSize: 13 }}>Handle:</label>
        <select
          id="audit-handle"
          value={selectedHandle}
          onChange={e => { setSelectedHandle(e.target.value); loadDevices(e.target.value); }}
          disabled={!scraperOnline}
          style={{ minWidth: 220, padding: '4px 8px' }}
          title="Select a company handle to audit"
        >
          <option value="">— select handle —</option>
          {handles.map(h => (
            <option key={h.handle} value={h.handle}>{h.handle} — {h.name}</option>
          ))}
        </select>
        <label htmlFor="audit-ip" style={{ fontWeight: 600, fontSize: 13 }}>PBX IP:</label>
        <input
          id="audit-ip"
          type="text"
          value={siteIp}
          onChange={e => setSiteIp(e.target.value)}
          placeholder="auto-filled or override"
          title="PBX/SIP server IP for this site"
          style={{ width: 160, padding: '4px 8px' }}
        />
      </div>

      {error && <p style={{ color: '#b42318', fontSize: 13 }}>{error}</p>}
      {loading && <p style={{ color: '#555', fontSize: 13 }}>Loading…</p>}

      {auditResults.length > 0 && (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              { label: 'Total checks', value: summary.total, color: '#475467' },
              { label: '✓ OK', value: summary.ok, color: '#16794a' },
              { label: '✗ Missing', value: summary.missing, color: '#b42318' },
              { label: '⚠ Changed', value: summary.changed, color: '#8a5a00' },
            ].map(s => (
              <div key={s.label} style={{ background: '#f7f8fa', border: '1px solid #e4e7ec', borderRadius: 8, padding: '8px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 11, color: '#666' }}>{s.label}</div>
              </div>
            ))}
          </div>

          {auditResults.map(({ device, lines }) => {
            const issues = lines.filter(l => l.status !== 'ok').length;
            const isExpanded = expandedDevice === device.device_id;
            return (
              <div key={device.device_id} style={{ border: '1px solid #e4e7ec', borderRadius: 8, marginBottom: 10, overflow: 'hidden' }}>
                <div
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                    background: issues === 0 ? '#f0fdf4' : issues > 2 ? '#fff5f5' : '#fffbeb',
                    cursor: 'pointer', userSelect: 'none',
                  }}
                  onClick={() => setExpandedDevice(isExpanded ? null : device.device_id)}
                >
                  <span style={{ fontWeight: 700, fontFamily: 'monospace', fontSize: 13 }}>
                    {device.directory_name || device.device_id}
                  </span>
                  <span style={{ fontSize: 12, color: '#666' }}>
                    {device.make} {device.model} · ext {device.extension || '?'} · {device.mac || 'no MAC'}
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: issues === 0 ? '#16794a' : '#b42318' }}>
                    {issues === 0 ? '✓ clean' : `${issues} issue${issues > 1 ? 's' : ''}`}
                  </span>
                  <span style={{ fontSize: 12, color: '#888' }}>{isExpanded ? '▲' : '▼'}</span>
                </div>

                {isExpanded && (
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: '#f4f4f4' }}>
                        <th style={{ padding: '5px 12px', textAlign: 'left', borderBottom: '1px solid #eee' }}>Check</th>
                        <th style={{ padding: '5px 12px', textAlign: 'left', borderBottom: '1px solid #eee' }}>Live Value</th>
                        <th style={{ padding: '5px 12px', textAlign: 'left', borderBottom: '1px solid #eee' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                          <td style={{ padding: '4px 12px', fontFamily: 'monospace', color: '#333' }}>{l.key}</td>
                          <td style={{ padding: '4px 12px', fontFamily: 'monospace', color: '#555', wordBreak: 'break-all' }}>
                            {l.key.toLowerCase().includes('password') && l.live && l.live !== '(not set)'
                              ? '••••••••'
                              : l.live}
                          </td>
                          <td style={{ padding: '4px 12px' }}>
                            <span style={{
                              display: 'inline-block', padding: '1px 8px', borderRadius: 999,
                              fontSize: 11, fontWeight: 700,
                              background: statusBg(l.status), color: statusColor(l.status),
                            }}>
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
        <p style={{ color: '#888', fontSize: 13 }}>
          No device configs found for {selectedHandle}. Run the Phone Config Scraper in the webscraper first.
        </p>
      )}
    </div>
  );
}