import { ottMikrotikTemplate } from './ottMikrotikTemplate';
import MikrotikTab from './tabs/MikrotikTab';
import React, { useState, useRef, useEffect } from 'react';
// Import main CSS for styling
import './App.css'
// Import PapaParse for CSV import/export
import Papa from 'papaparse';
// Import custom dynamic switch config components
import SwitchDynamicTemplate from './SwitchDynamicTemplate';
import Switch24DynamicTemplate from './Switch24DynamicTemplate';
import Switch8DynamicTemplate from './Switch8DynamicTemplate';
import HostedOrderTrackerTab from './HostedOrderTrackerTab';
import StrettoImportExportTab from './StrettoImportExportTab';
import { FaInfoCircle } from 'react-icons/fa';
import DiagnosticsTab from './tabs/DiagnosticsTab';
import VpbxImportTab from './tabs/VpbxImportTab';
import ConfigAuditTab from './tabs/ConfigAuditTab';
import PhoneConfigGeneratorTab from './tabs/PhoneConfigGeneratorTab';

// List of supported phone models for config generation
const MODEL_OPTIONS = [
  'VVX 400', 'VVX 500', 'VVX 600', 'CP-7841-3PCC', 'CP-8832-K9', 'CP-7832-3PCC',
  'CP-8832-3PCC', 'SPA-122 ATA', 'SSIP6000', 'CP-7811-3PCC', 'SSIP7000', 'SSIP330',
  'D230', 'Trio 8500 Confernce', 'SSIP700-Mic', 'Yealink T54W', 'Yealink T57W',
  'CP960', 'Yealink SIP-T46S', 'SIP-T46U', 'SIP-T48S', 'SIP-T48U', 'i12 Door Strike',
  '8180 IP Loud Ringer', '8301 Paging Server', 'Yealink W56P', 'Yealink W60P',
  'HT813 ATA', '8186', 'Yealink 56h Dect w/ 60p Base', 'Yealink 56h Dect w/ 76p Base',
  'Yealink 56h Dect Handset'
];

// Tab definitions for navigation, including the Reference tab
const TABS = [
  { key: 'phone', label: 'Phone Configs' },
  { key: 'expansion', label: 'Expansion Modules' },
  { key: 'fullconfig', label: 'Full Config' },
  { key: 'reference', label: 'Reference' },
  { key: 'diagnostics', label: 'Diagnostics' },
  { key: 'fbpx', label: 'FBPX Import' },
  { key: 'vpbx', label: 'VPBX Import' },
  { key: 'phonegen', label: 'Phone Config Generator' },
  { key: 'audit', label: 'Config Audit' },
  { key: 'mikrotik', label: 'Mikrotik Templates' },
  { key: 'switch', label: 'Switch Templates' },
  { key: 'ordertracker', label: 'Order Tracker' },
  { key: 'streeto', label: 'Stretto Import' },
];

// Field definitions for FBPX import/export template (PBX user fields)
const FPBX_FIELDS = [
  "extension", "name", "description", "tech", "secret", "callwaiting_enable", "voicemail",
  "voicemail_enable", "voicemail_vmpwd", "voicemail_email", "voicemail_pager", "voicemail_options",
  "voicemail_same_exten", "outboundcid", "id", "dial", "user", "max_contacts", "accountcode"
];

// Type definition for FBPX form (for type safety)
type FpbxFormType = Record<typeof FPBX_FIELDS[number], string>;

// Helper to create an empty FBPX row
const createEmptyFpbxRow = (): FpbxFormType => FPBX_FIELDS.reduce((acc, f) => ({ ...acc, [f]: '' }), {} as FpbxFormType);

// --- Static config blocks for Yealink/Polycom ---
const DEFAULT_TIME_OFFSET = '-5';
const DEFAULT_ADMIN_PASSWORD = ''; // pragma: allowlist secret

// Tooltips for Phone Config tab fields
const FIELD_TOOLTIPS: Record<string, string> = {
  // Base Config Options
  ip: "Enter the IP address of the phone you are configuring. Used to identify the device on the network.",
  phoneType: "Select the brand of phone (Polycom or Yealink) you are generating the configuration for.",
  model: "Choose the specific model of the phone. This determines the correct configuration format.",
  startExt: "Enter the starting extension number. Used to auto-fill settings across multiple phones.",
  endExt: "Enter the ending extension number. Used to generate config for a range of extensions.",
  labelPrefix: "Prefix added to the label shown on each phone’s screen (e.g., company name or department).",
  timeOffset: "Adjusts the phone’s time display relative to UTC (e.g., -5 for EST).",
  adminPassword: "Sets the admin password for the phone’s web interface. Ensure it meets your security requirements.", // pragma: allowlist secret
  yealinkLabelLength: "When checked, uses the full label text for BLF/speed dial keys. May affect layout on small screens.",
  yealinkDisableMissedCall: "Prevents the phone from displaying missed call alerts. Useful in shared environments.",
  yealinkCallStealing: "Allows users to pick up active calls from another BLF-monitored extension.",
  // Polycom MWI
  polycomMWIExt: "Enter the extension number whose voicemail status should be monitored.",
  polycomMWIPbxIp: "Enter the IP address of the PBX server that the phone will connect to for MWI.",
  // Linekey/BLF/Speed/Transfer/Hotkey Generator
  linekeyBrand: "Select the phone brand (Yealink or Polycom) for which the key will be configured.",
  linekeyNum: "The key/button number on the phone to assign this function (usually starts at 1).",
  linekeyLabel: "Text label that will appear on the phone’s display for this key.",
  linekeyRegLine: "Select the line (account) this key should be associated with, usually Line 1.",
  linekeyType: "Choose the key function type (e.g., BLF, speed dial, transfer, etc.).",
  linekeyValue: "The target number, extension, or function code to assign to the key.",
  // External Number Speed Dial
  externalBrand: "Choose the phone brand for which you are creating the external dial key.",
  externalLineNum: "The programmable key/button number to assign this speed dial.",
  externalLabel: "Label to display for the external number on the phone’s screen.",
  externalNumber: "Enter the external phone number this key will dial when pressed."
};

// Expansion Module Preview Icons, Tooltips, and Polycom constants moved to constants/expansionModule.ts
// Removed unused import to resolve 'All imports in import declaration are unused.' error

// --- Phase-1 config parser: only hydrates fields the UI explicitly supports. ---
// All other lines are counted as unparsed so the caller can warn the user.
function parseSupportedFields(raw: string, brand: 'Polycom' | 'Yealink'): {
  adminPassword?: string;
  timeOffset?: string;
  unparsedCount: number;
} {
  const KNOWN_KEYS = new Set([
    'static.security.user_password',
    'local_time.time_zone',
    'tcpipapp.sntp.gmtoffset',
    'reg.1.address', 'reg.1.auth.userid', 'reg.1.auth.password',
    'reg.1.displayname', 'reg.1.label', 'reg.1.line.1.label',
  ]);
  const lines = raw.split('\n').map(l => l.trim()).filter(l => l && l.includes('=') && !l.startsWith('#'));
  const result: { adminPassword?: string; timeOffset?: string; unparsedCount: number } = { unparsedCount: 0 };
  let parsedCount = 0;
  for (const line of lines) {
    const eqIdx = line.indexOf('=');
    const key = line.slice(0, eqIdx).trim();
    const value = line.slice(eqIdx + 1).trim();
    if (key === 'static.security.user_password') { result.adminPassword = value; parsedCount++; }
    else if (key === 'local_time.time_zone' && brand === 'Yealink') { result.timeOffset = value; parsedCount++; }
    else if (key === 'tcpipapp.sntp.gmtoffset' && brand === 'Polycom') {
      const secs = parseInt(value);
      if (!isNaN(secs)) { result.timeOffset = String(secs / 3600); parsedCount++; }
    } else if (KNOWN_KEYS.has(key)) { parsedCount++; }
  }
  result.unparsedCount = Math.max(0, lines.length - parsedCount);
  return result;
}

function App() {
  // --- Yealink/Polycom advanced options state (move to top, single source of truth) ---
  const [yealinkLabelLength, setYealinkLabelLength] = useState(false);
  const [yealinkDisableMissedCall, setYealinkDisableMissedCall] = useState(false);
  const [yealinkCallStealing, setYealinkCallStealing] = useState(false);
  // UI banner: capture current host and port for display
  const [clientInfo] = useState(() => {
    if (typeof window !== 'undefined') {
      const { hostname, port, protocol } = window.location;
      const resolvedPort = port || (protocol === 'https:' ? '443' : '80');
      return { hostname, port: resolvedPort, protocol };
    }
    return { hostname: 'unknown', port: '', protocol: '' };
  });

  // --- OTT Mikrotik Template Editor State ---
  const [ottFields, setOttFields] = useState({
    ip: '',
    customerName: '',
    customerAddress: '',
    city: '',
    xip: '',
    handle: '',
  });
  function getOttTemplate(fields: typeof ottFields): string {
    return ottMikrotikTemplate
      .replace('XXX.XXX.XXX.XXX', fields.ip || 'XXX.XXX.XXX.XXX')
      .replace('"CUSTOMER NAME"', fields.customerName || '"CUSTOMER NAME"')
      .replace('"CUSTOMER ADDRESS"', fields.customerAddress || '"CUSTOMER ADDRESS"')
      .replace('"CITY"', fields.city || '"CITY"')
      .replace('"XIP"', fields.xip || '"XIP"')
      .replace('"HANDLE-CUSTOMERADDRESS"', fields.handle || '"HANDLE-CUSTOMERADDRESS"');
  }
  // State for active tab selection
  const [activeTab, setActiveTab] = useState('phone');
  // State for phone type (Polycom or Yealink)
  const [phoneType, setPhoneType] = useState<'Polycom' | 'Yealink'>('Polycom');
  // State for selected phone model
  const [model, setModel] = useState(MODEL_OPTIONS[0]);
  // State for IP address input
  const [ip, setIp] = useState('');
  // State for extension range and label prefix
  const [startExt, setStartExt] = useState('71');
  const [endExt, setEndExt] = useState('73');
  const [labelPrefix, setLabelPrefix] = useState('Park');
  // State for generated config output
  const [output, setOutput] = useState('');
  // --- Phone Config Scraper panel state ---
  const SCRAPER_BASE_PHONE = 'http://localhost:8788';
  const [scraperHandles, setScraperHandles] = useState<{ handle: string; name: string; ip: string }[]>([]);
  const [scraperHandle, setScraperHandle] = useState('');
  const [scraperDevices, setScraperDevices] = useState<{ device_id: string; directory_name: string; extension: string; mac: string; make: string; model: string; bulk_config: string }[]>([]);
  const [scraperDevice, setScraperDevice] = useState('');
  const [scraperOnlinePhone, setScraperOnlinePhone] = useState<boolean | null>(null);
  const [scraperLiveConfig, setScraperLiveConfig] = useState('');
  // --- Edit mode / loaded config state ---
  const [configMode, setConfigMode] = useState<'new' | 'edit'>('new');
  const [loadedConfigRaw, setLoadedConfigRaw] = useState('');
  const [loadedDeviceMeta, setLoadedDeviceMeta] = useState<{
    deviceId: string; directoryName: string; extension: string;
    mac: string; make: string; model: string; handle: string; handleName: string;
  } | null>(null);
  const [fullConfigOutput, setFullConfigOutput] = useState('');
  // --- Current Scraped Config display state (separate from edit-mode hydration) ---
  const [currentConfigLoading, setCurrentConfigLoading] = useState(false);
  const [currentConfigError, setCurrentConfigError] = useState('');
  // currentConfigParsed: fields extracted from the raw scraped config for display in metadata
  const [currentConfigParsed, setCurrentConfigParsed] = useState<{
    adminPassword?: string; timeOffset?: string; unparsedCount: number;
  } | null>(null);
  // --- Site Config display state (loaded when a handle is selected) ---
  const [siteConfigRaw, setSiteConfigRaw] = useState('');
  const [siteConfigLoading, setSiteConfigLoading] = useState(false);
  const [siteConfigError, setSiteConfigError] = useState('');
  const [siteConfigMeta, setSiteConfigMeta] = useState<{
    handle: string; last_seen_utc: string;
  } | null>(null);
  // --- Dark mode ---
  const [darkMode, setDarkMode] = useState(() => {
    try { return localStorage.getItem('theme') === 'dark'; } catch { return false; }
  });
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
    try { localStorage.setItem('theme', darkMode ? 'dark' : 'light'); } catch { /* ignore */ }
  }, [darkMode]);

  // --- Advanced section collapse toggles (Phone tab) ---
  const [showMWI, setShowMWI] = useState(false);
  const [showLinekeyGen, setShowLinekeyGen] = useState(false);
  const [showExternalSpeed, setShowExternalSpeed] = useState(false);

  useEffect(() => {
    fetch(`${SCRAPER_BASE_PHONE}/api/vpbx/records`, { signal: AbortSignal.timeout(3000) })
      .then(r => r.json())
      .then(data => {
        setScraperOnlinePhone(true);
        const items = data?.items || [];
        setScraperHandles(items.sort((a: { handle: string }, b: { handle: string }) => a.handle.localeCompare(b.handle)));
      })
      .catch(() => setScraperOnlinePhone(false));
  }, []);

  async function loadScraperDevices(handle: string) {
    if (!handle) {
      setScraperDevices([]); setScraperDevice(''); setScraperLiveConfig('');
      setLoadedConfigRaw(''); setLoadedDeviceMeta(null);
      setConfigMode('new');
      // Clear site config when handle is deselected
      setSiteConfigRaw(''); setSiteConfigMeta(null); setSiteConfigError('');
      return;
    }

    // Clear stale device + site-config state before loading new handle
    setScraperDevice(''); setScraperLiveConfig('');
    setLoadedConfigRaw(''); setLoadedDeviceMeta(null);
    setConfigMode('new');
    setSiteConfigRaw(''); setSiteConfigMeta(null); setSiteConfigError('');

    // Load devices for this handle
    try {
      const res = await fetch(`${SCRAPER_BASE_PHONE}/api/vpbx/device-configs?handle=${encodeURIComponent(handle)}`);
      const data = await res.json();
      const devs = data?.items || [];
      setScraperDevices(devs);
      const rec = scraperHandles.find(h => h.handle === handle);
      if (rec?.ip) setIp(rec.ip);
    } catch { setScraperDevices([]); }

    // Load site config for this handle in parallel — 404 means not yet scraped (not an error)
    setSiteConfigLoading(true);
    fetch(`${SCRAPER_BASE_PHONE}/api/vpbx/site-configs/${encodeURIComponent(handle)}`)
      .then(r => {
        if (r.status === 404) { setSiteConfigLoading(false); return null; }
        return r.json();
      })
      .then(data => {
        if (!data) return; // 404 case — leave raw empty
        setSiteConfigRaw(data.site_config || '');
        setSiteConfigMeta({ handle: data.handle, last_seen_utc: data.last_seen_utc || '' });
      })
      .catch(() => setSiteConfigError('Failed to load site config from webscraper.'))
      .finally(() => setSiteConfigLoading(false));
  }

  function applyScraperDevice(deviceId: string) {
    const dev = scraperDevices.find(d => d.device_id === deviceId);
    if (!dev) {
      setScraperDevice('');
      setScraperLiveConfig('');
      setLoadedConfigRaw('');
      setLoadedDeviceMeta(null);
      setCurrentConfigLoading(false);
      setCurrentConfigError('');
      setCurrentConfigParsed(null);
      return;
    }

    const brand: 'Polycom' | 'Yealink' =
      dev.make?.toLowerCase().includes('yealink') ||
      dev.model?.toLowerCase().includes('yealink') ||
      dev.model?.toLowerCase().startsWith('sip-') ? 'Yealink' : 'Polycom';

    setScraperDevice(deviceId);

    // Populate currentConfig display state — raw config is already in device payload
    const raw = dev.bulk_config || '';
    setScraperLiveConfig(raw);
    setLoadedConfigRaw(raw);
    setCurrentConfigError(raw ? '' : 'Device record exists but no bulk config was captured. Run "Scrape Phone Configs" for this handle to populate it.');
    setCurrentConfigLoading(false);

    // Parse known fields for display metadata — does NOT touch form fields
    const parsed = raw ? parseSupportedFields(raw, brand) : { unparsedCount: 0 };
    setCurrentConfigParsed(parsed);

    const handleRec = scraperHandles.find(h => h.handle === scraperHandle);
    setLoadedDeviceMeta({
      deviceId: dev.device_id,
      directoryName: dev.directory_name,
      extension: dev.extension,
      mac: dev.mac,
      make: dev.make,
      model: dev.model,
      handle: scraperHandle,
      handleName: handleRec?.name || '',
    });
    // Stay in 'new' mode — user must explicitly press "Load Current Config Into Form"
    // to switch to edit mode and hydrate fields.
  }

  // Called only when user explicitly clicks "Load Current Config Into Form"
  function loadCurrentConfigIntoForm() {
    if (!loadedDeviceMeta || !loadedConfigRaw) return;
    const brand: 'Polycom' | 'Yealink' =
      loadedDeviceMeta.make?.toLowerCase().includes('yealink') ||
      loadedDeviceMeta.model?.toLowerCase().includes('yealink') ||
      loadedDeviceMeta.model?.toLowerCase().startsWith('sip-') ? 'Yealink' : 'Polycom';

    if (loadedDeviceMeta.extension) { setStartExt(loadedDeviceMeta.extension); setEndExt(loadedDeviceMeta.extension); }
    if (loadedDeviceMeta.model) setModel(loadedDeviceMeta.model);
    setPhoneType(brand);

    const parsed = parseSupportedFields(loadedConfigRaw, brand);
    if (parsed.adminPassword !== undefined) setAdminPassword(parsed.adminPassword);
    if (parsed.timeOffset !== undefined) setTimeOffset(parsed.timeOffset);
    setCurrentConfigParsed(parsed);
    setConfigMode('edit');
  }

  // Yealink expansion module state
  const [yealinkSection, setYealinkSection] = useState({
    templateType: 'BLF',
    sidecarPage: '1',
    sidecarLine: '1',
    label: '',
    value: '',
    pbxIp: '',
  });
  const [yealinkOutput, setYealinkOutput] = useState('');

  type YealinkExpansionKey = { label: string; value: string; ip?: string };
  const yealinkKeys: YealinkExpansionKey[] = Array.from({ length: 20 }, () => ({
    label: yealinkSection.label,
    value: yealinkSection.value,
    ip: yealinkSection.pbxIp,
  }));
  const generateYealinkExpansion = () => {
    const { templateType, sidecarPage, sidecarLine, label, value, pbxIp } = yealinkSection;
    let config = '';
    if (templateType === 'SpeedDial') {
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.label=${label}\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.type=13\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.value=${value}\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.line=1\n`;
    } else {
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.label=${label}\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.type=16\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.value=${value}@${pbxIp}\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.line=1\n`;
    }
    setYealinkOutput(config);
  };

  // Generate all 20 Yealink expansion keys for the selected page
  function generateYealinkExpansionAll() {
    const page = yealinkSection.sidecarPage || '1';
    let config = '';
    yealinkKeys.forEach((key, i) => {
      const idx = i + 1;
      config += `expansion_module.${page}.key.${idx}.label=${key.label}\n`;
      config += `expansion_module.${page}.key.${idx}.type=16\n`; // or 13 for SpeedDial
      config += `expansion_module.${page}.key.${idx}.value=${key.value}${key.ip ? '@' + key.ip : ''}\n`;
      config += `expansion_module.${page}.key.${idx}.line=1\n`;
    });
    setYealinkOutput(config);
  }

  // Polycom expansion module state
  const [polycomSection, setPolycomSection] = useState({
    address: '',
    label: '',
    type: 'automata',
    linekeyCategory: 'BLF',
    linekeyIndex: '',
  });
  const [polycomOutput, setPolycomOutput] = useState('');

  type PolycomExpansionKey = { address: string; label: string };
  const polycomKeys: PolycomExpansionKey[] = Array.from({ length: 28 }, () => ({
    address: polycomSection.address,
    label: polycomSection.label,
  }));
  const generatePolycomExpansion = () => {
    const { address, label, type, linekeyCategory, linekeyIndex } = polycomSection;
    let config = '';
    config += `attendant.resourcelist.${linekeyIndex}.address=${address}\n`;
    config += `attendant.resourcelist.${linekeyIndex}.label=${label}\n`;
    config += `attendant.resourcelist.${linekeyIndex}.type=${type}\n`;
    config += `linekey.${linekeyIndex}.category=${linekeyCategory}\n`;
    config += `linekey.${linekeyIndex}.index=${linekeyIndex}\n`;
    setPolycomOutput(config);
  };

  // Generate all 28 Polycom expansion keys
  function generatePolycomExpansionAll() {
    let config = '';
    polycomKeys.forEach((key, i) => {
      const idx = i + 1;
      config += `attendant.resourcelist.${idx}.address=${key.address}\n`;
      config += `attendant.resourcelist.${idx}.label=${key.label}\n`;
      config += `attendant.resourcelist.${idx}.type=automata\n`;
      config += `linekey.${idx}.category=BLF\n`;
      config += `linekey.${idx}.index=${idx}\n`;
    });
    setPolycomOutput(config);
  }

  // Polycom MWI (Message Waiting Indicator) state and generator
  const [polycomMWI, setPolycomMWI] = useState({
    ext: '',
    pbxIp: '',
    output: ''
  });
  function generatePolycomMWI() {
    setPolycomMWI(mwi => ({
      ...mwi,
      output:
        `voIpProt.SIP.specialEvent.checkMWI.1.address=${mwi.ext}@${mwi.pbxIp}\n` +
        `voIpProt.SIP.specialEvent.checkMWI.1.type=checkMWI\n`
    }));
  }

  // Generate Yealink expansion module config (sidecar keys)
  // const generateYealinkExpansion = () => {
  //   const { templateType, sidecarPage, sidecarLine, label, value, pbxIp } = yealinkSection;
  //   let config = '';
  //   if (templateType === 'SpeedDial') {
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.label=${label}\n`;
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.type=13\n`;
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.value=${value}\n`;
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.line=1\n`;
  //   } else {
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.label=${label}\n`;
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.type=16\n`;
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.value=${value}@${pbxIp}\n`;
  //     config += `expansion_module.${sidecarPage}.key.${sidecarLine}.line=1\n`;
  //   }
  //   setYealinkOutput(config);
  // };

  // State for Polycom expansion module section
  // ...existing code...

  // Helper: Generate Polycom park lines config for selected model
  function generatePolycomParkLines(model: string, start: number, end: number, ip: string) {
    let config = '';
    if (model === 'VVX 400') {
      let linekey = 7;
      for (let i = start; i <= end; i++, linekey++) {
        config += `attendant.resourcelist.${linekey}.address=${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.calladdress=*85${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.label=Park ${linekey - 6}\n`;
        config += `attendant.resourcelist.${linekey}.type=automata\n`;
      }
      for (let l = 7; l < linekey; l++) {
        config += `linekey.${l}.category=BLF\n`;
        config += `linekey.${l}.index=${l}\n`;
      }
    } else if (model === 'VVX 500') {
      let linekey = 9;
      for (let i = start; i <= end; i++, linekey++) {
        config += `attendant.resourcelist.${linekey}.address=${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.calladdress=*85${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.label=Park ${linekey - 8}\n`;
        config += `attendant.resourcelist.${linekey}.type=automata\n`;
      }
      for (let l = 9; l < linekey; l++) {
        config += `linekey.${l}.category=BLF\n`;
        config += `linekey.${l}.index=${l}\n`;
      }
    } else if (model === 'VVX 600') {
      // 13,14,15 for 71,72,73
      const keys = [13, 14, 15];
      let idx = 0;
      for (let i = start; i <= end; i++, idx++) {
        const linekey = keys[idx];
        config += `attendant.resourcelist.${linekey}.address=${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.calladdress=*85${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.label=Park ${idx + 1}\n`;
        config += `attendant.resourcelist.${linekey}.type=automata\n`;
      }
      for (let j = 0; j < idx; j++) {
        const linekey = keys[j];
        config += `linekey.${linekey}.category=BLF\n`;
        config += `linekey.${linekey}.index=${linekey}\n`;
      }
    } else {
      // Generic Polycom template
      let linekey = start;
      for (let i = start; i <= end; i++, linekey++) {
        config += `attendant.resourcelist.${linekey}.address=${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.calladdress=${i}@${ip}\n`;
        config += `attendant.resourcelist.${linekey}.label=Park\n`;
        config += `attendant.resourcelist.${linekey}.type=automata\n`;
        config += `linekey.${linekey}.category=BLF\n`;
        config += `linekey.${linekey}.index=${linekey}\n`;
      }
    }
    return config;
  }

  // Helper: Generate Yealink park lines config for selected model
  function generateYealinkParkLines(model: string, start: number, end: number, ip: string) {
    let config = '';
    if (model === 'Yealink SIP-T46S' || model === 'Yealink T54W') {
      let linekey = 6;
      for (let i = start; i <= end; i++, linekey++) {
        config += `linekey.${linekey}.extension=${i}\n`;
        config += `linekey.${linekey}.label=Park ${linekey - 5}\n`;
        config += `linekey.${linekey}.line=1\n`;
        config += `linekey.${linekey}.type=10\n`;
        config += `linekey.${linekey}.value=${i}@${ip}\n`;
      }
    } else if (model === 'SIP-T48S' || model === 'Yealink T57W') {
      let linekey = 7;
      for (let i = start; i <= end; i++, linekey++) {
        config += `linekey.${linekey}.extension=${i}\n`;
        config += `linekey.${linekey}.label=Park ${linekey - 6}\n`;
        config += `linekey.${linekey}.line=1\n`;
        config += `linekey.${linekey}.type=10\n`;
        config += `linekey.${linekey}.value=${i}@${ip}\n`;
      }
    } else {
      let linekey = start;
      for (let i = start; i <= end; i++, linekey++) {
        config += `linekey.${linekey}.extension=${i}\n`;
        config += `linekey.${linekey}.label=Park\n`;
        config += `linekey.${linekey}.line=1\n`;
        config += `linekey.${linekey}.type=10\n`;
        config += `linekey.${linekey}.value=${i}@${ip}\n`;
      }
    }
    return config;
  }

  // Global/Required attributes for Yealink phones (toggle advanced features)
  const yealinkOptions = {
    callStealing: yealinkCallStealing,
    labelLength: yealinkLabelLength,
    disableMissedCall: yealinkDisableMissedCall,
  };

  // Helper: Generate Yealink global attributes config
  function getYealinkGlobalAttributes(opts: typeof yealinkOptions) {
    let config = '';
    if (opts.callStealing) {
      config += 'features.pickup.direct_pickup_code=**\n';
      config += 'features.pickup.direct_pickup_enable=1\n';
    }
    if (opts.labelLength) {
      config += 'features.config_dsskey_length=1\n';
    }
    if (opts.disableMissedCall) {
      config += 'phone_setting.missed_call_power_led_flash.enable=0\n';
      config += 'features.missed_call_popup.enable=0\n';
    }
    return config;
  }

  // State for feature key template section (advanced programmable keys)
  // ...existing code...

  // (Unused quick-macro templates removed to keep tsc build clean)

  // Generate main config for Polycom or Yealink park lines (main output)
  const generateConfig = () => {
    const start = parseInt(startExt, 10);
    const end = parseInt(endExt, 10);
    if (isNaN(start) || isNaN(end) || !ip) {
      setOutput('Please enter valid extension numbers and IP address.');
      return;
    }
    let config = `# Model: ${model}\n`;

    // --- Insert static config blocks for W56P/W60P, Yealink, Polycom ---
    if (
      model === 'Yealink W56P' ||
      model === 'Yealink W60P' ||
      model === 'Yealink 56h Dect w/ 60p Base' ||
      model === 'Yealink 56h Dect w/ 76p Base' ||
      model === 'Yealink 56h Dect Handset'
    ) {
      config += [
        'account.1.subscribe_mwi_to_vm=1',
        'custom.handset.time_format=0',
        'features.remote_phonebook.enable=1',
        'features.remote_phonebook.flash_time=3600',
        'local_time.dhcp_time=0',
        'local_time.ntp_server1=pool.ntp.org',
        'local_time.summer_time=2',
        'local_time.time_format=0',
        `local_time.time_zone=${timeOffset}`,
        'local_time.time_zone_name=United States-Eastern Time',
        'programablekey.2.label=Directory',
        'programablekey.2.line=%EMPTY%',
        'programablekey.2.type=47',
        'programablekey.2.xml_phonebook=-1',
        'sip.mac_in_ua=1',
        'sip.trust_ctrl=1',
        'static.auto_provision.custom.protect=1',
        'static.auto_provision.server.url=http://provisioner.123.net/',
        'voice_mail.number.1=*97',
        `static.security.user_password=${adminPassword}`,
        ''
      ].join('\n');
    } else if (phoneType === 'Yealink') {
      config += [
        'static.network.ip_address_mode=0',
        'static.network.static_dns_enable=1',
        'static.network.primary_dns=8.8.8.8',
        'static.network.secondary_dns=8.8.4.4',
        'account.1.subscribe_mwi_to_vm=1',
        'account.1.cid_source=1',
        'custom.handset.time_format=0',
        'features.remote_phonebook.enable=1',
        'features.remote_phonebook.flash_time=3600',
        'features.call_log_show_num=2',
        'features.enhanced_dss_keys.enable=1',
        'feature.enhancedFeatureKeys.enabled=1',
        'local_time.dhcp_time=0',
        'local_time.ntp_server1=pool.ntp.org',
        'local_time.summer_time=2',
        'local_time.time_format=0',
        `local_time.time_zone=${timeOffset}`,
        'local_time.time_zone_name=United States-Eastern Time',
        'programablekey.2.label=Directory',
        'programablekey.2.line=%EMPTY%',
        'programablekey.2.type=47',
        'programablekey.2.xml_phonebook=-1',
        'sip.mac_in_ua=1',
        'sip.trust_ctrl=1',
        'static.auto_provision.custom.protect=1',
        'static.auto_provision.server.url=http://provisioner.123.net/',
        'voice_mail.number.1=*97',
        `static.security.user_password=${adminPassword}`,
        ''
      ].join('\n');
      config += getYealinkGlobalAttributes(yealinkOptions);
      config += generateYealinkParkLines(model, start, end, ip);
    } else if (phoneType === 'Polycom') {
      config += [
        'device.sntp.gmtoffsetcityid=16',
        'device.sntp.gmtoffsetcityid.set=1',
        'device.sntp.servername=north-america.pool.ntp.org',
        'device.sntp.servername.set=1',
        'lcl.datetime.date.format=D,dM',
        'lcl.datetime.date.longformat=0',
        'tcpipapp.sntp.address=pool.ntp.org',
        'tcpipapp.sntp.address.overridedhcp=1',
        `tcpipapp.sntp.gmtoffset=${parseInt(timeOffset) * 3600}`,
        'tcpipapp.sntp.gmtoffset.overridedhcp=1',
        'tcpipapp.sntp.gmtoffsetcityid=16',
        ''
      ].join('\n');
      config += generatePolycomParkLines(model, start, end, ip);
    }
    // Append expansion config if model supports it
    if (phoneType === 'Polycom' && ['VVX 400', 'VVX 500', 'VVX 600'].includes(model)) {
      config += '\n# Polycom Expansion Module\n';
      config += polycomOutput; // or call generatePolycomExpansionAll() if you want all keys
    }
    if (phoneType === 'Yealink' && ['Yealink T54W', 'Yealink T57W', 'Yealink SIP-T46S', 'SIP-T48S', 'SIP-T48U'].includes(model)) {
      config += '\n# Yealink Expansion Module\n';
      config += yealinkOutput; // or call generateYealinkExpansionAll() if you want all keys
    }
    setOutput(config);
  };

  // State and handlers for FBPX import/export form (PBX CSV import/export)
  const [fpbxRows, setFpbxRows] = useState<FpbxFormType[]>(Array(10).fill(0).map(createEmptyFpbxRow));
  const fpbxDownloadRef = useRef<HTMLAnchorElement>(null);

  function handleFpbxChange(rowIdx: number, e: React.ChangeEvent<HTMLInputElement>) {
    setFpbxRows(rows => {
      const updated = [...rows];
      updated[rowIdx] = { ...updated[rowIdx], [e.target.name]: e.target.value };
      return updated;
    });
  }

  function handleFpbxExport() {
    const csvHeader = FPBX_FIELDS.join(',') + '\n';
    const csvRows = fpbxRows.map(row => FPBX_FIELDS.map(f => `"${(row[f] || '').replace(/"/g, '""')}"`).join(',')).join('\n') + '\n';
    const csv = csvHeader + csvRows;
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    if (fpbxDownloadRef.current) {
      fpbxDownloadRef.current.href = url;
      fpbxDownloadRef.current.download = 'fpbx_import.csv';
      fpbxDownloadRef.current.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  function handleFpbxImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse(file, {
      header: true,
      complete: (results: Papa.ParseResult<Record<string, string>>) => {
        const rows = (results.data as FpbxFormType[]).filter(row => row && Object.values(row).some(Boolean));
        setFpbxRows(rows.length ? rows : [createEmptyFpbxRow()]);
      },
    });
  }

  function handleFpbxAddRow(count = 1) {
    setFpbxRows(rows => [...rows, ...Array(count).fill(0).map(createEmptyFpbxRow)]);
  }
  function handleFpbxDeleteRow(idx: number) {
    setFpbxRows(rows => rows.length === 1 ? rows : rows.filter((_, i) => i !== idx));
  }

  // New state for time offset and admin password
  const [timeOffset, setTimeOffset] = useState(DEFAULT_TIME_OFFSET);
  const [adminPassword, setAdminPassword] = useState(DEFAULT_ADMIN_PASSWORD);

  // New state for external number speed dial
  const [externalSpeed, setExternalSpeed] = useState({
    brand: 'Yealink',
    lineNum: '',
    label: '',
    number: '',
    efkIndex: '',
  });
  const [externalSpeedOutput, setExternalSpeedOutput] = useState('');

  // Generate external number speed dial config
  function generateExternalSpeed() {
    if (externalSpeed.brand === 'Yealink') {
      setExternalSpeedOutput(
        `linekey.${externalSpeed.lineNum}.line=1\n` +
        `linekey.${externalSpeed.lineNum}.label=${externalSpeed.label}\n` +
        `linekey.${externalSpeed.lineNum}.type=13\n` +
        `linekey.${externalSpeed.lineNum}.value=${externalSpeed.number}\n`
      );
    } else {
      setExternalSpeedOutput(
        'feature.enhancedFeatureKeys.enabled=1\n' +
        'feature.EFKLineKey.enabled=1\n' +
        `efk.efklist.${externalSpeed.efkIndex}.mname=${externalSpeed.label}\n` +
        `efk.efklist.${externalSpeed.efkIndex}.status=1\n` +
        `efk.efklist.${externalSpeed.efkIndex}.action.string=${externalSpeed.number}$Tinvite$\n` +
        `linekey.${externalSpeed.lineNum}.category=EFK\n` +
        `linekey.${externalSpeed.lineNum}.index=${externalSpeed.efkIndex}\n`
      );
    }
  }

  // --- Full Config composer ---
  function composeFullConfig() {
    const phoneOut = output.trim();
    const expansionOut = phoneType === 'Yealink' ? yealinkOutput.trim() : polycomOutput.trim();
    if (!phoneOut && !expansionOut) {
      setFullConfigOutput('');
      return;
    }
    let composed = '';
    if (phoneOut) composed += phoneOut;
    if (phoneOut && expansionOut) composed += '\n\n';
    if (expansionOut) composed += `# Expansion Module\n${expansionOut}`;
    setFullConfigOutput(composed);
  }

  // --- Reset form to loaded raw values ---
  function resetToLoaded() {
    if (!loadedConfigRaw || !loadedDeviceMeta) return;
    const brand = loadedDeviceMeta.make?.toLowerCase().includes('yealink') ||
      loadedDeviceMeta.model?.toLowerCase().includes('yealink') ||
      loadedDeviceMeta.model?.toLowerCase().startsWith('sip-') ? 'Yealink' : 'Polycom';
    const parsed = parseSupportedFields(loadedConfigRaw, brand);
    if (parsed.adminPassword !== undefined) setAdminPassword(parsed.adminPassword);
    if (parsed.timeOffset !== undefined) setTimeOffset(parsed.timeOffset);
    setScraperLiveConfig(loadedConfigRaw);
  }

  // Fix: Remove stray/duplicate code (no stray generateYealinkExpansion, etc.)

  // Fix: All <select> elements have <option> children (already present in your code)

  // Fix: All handlers and keys are correct (already present in your code)

  // Fix: All imports are present (already present in your code)

  // Fix: Remove any syntax errors (none found in your code)

  // Fix: Remove incomplete object in YEALINK_LINEKEY_TYPES
  const YEALINK_LINEKEY_TYPES = [
    { code: 0, label: 'NA' },
    { code: 1, label: 'Conference' },
    { code: 2, label: 'Forward' },
    { code: 3, label: 'Transfer' },
    { code: 4, label: 'Hold' },
    { code: 5, label: 'DND' },
    { code: 7, label: 'Call Return' },
    { code: 8, label: 'SMS' },
    { code: 9, label: 'Directed Pickup' },
    { code: 10, label: 'Call Park' },
    { code: 11, label: 'DTMF' },
    { code: 12, label: 'Voice Mail' },
    { code: 13, label: 'Speed Dial' },
    { code: 14, label: 'Intercom' },
    { code: 15, label: 'Line' },
    { code: 16, label: 'BLF' },
    { code: 17, label: 'URL' },
    { code: 18, label: 'Group Listening' },
    { code: 20, label: 'Private Hold' },
    { code: 22, label: 'XML Group' },
    { code: 23, label: 'Group Pickup' },
    { code: 24, label: 'Multicast Paging' },
    { code: 25, label: 'Record' },
    { code: 27, label: 'XML Browser' },
    { code: 34, label: 'Hot Desking' },
    { code: 35, label: 'URL Record' }, // <-- Added
    { code: 38, label: 'LDAP' },
    { code: 39, label: 'BLF List' },
    { code: 40, label: 'Prefix' },
    { code: 41, label: 'Zero Touch' },
    { code: 42, label: 'ACD' },
    { code: 45, label: 'Local Group' },
    { code: 46, label: 'Network Group' },
    { code: 49, label: 'Custom Button' },
    { code: 50, label: 'Keypad Lock' },
    { code: 55, label: 'Meet-Me Conference' },
    { code: 56, label: 'Retrieve Park' },
    { code: 57, label: 'Hoteling' },
    { code: 58, label: 'ACD Grace' },
    { code: 59, label: 'Sisp Code' },
    { code: 60, label: 'Emergency' },
    { code: 61, label: 'Directory' },
    { code: 73, label: 'MACRO' },
  ];
  const [linekeyGen, setLinekeyGen] = useState({
    brand: 'Yealink',
    lineNum: '',
    label: '',
    regLine: '1',
    type: 16,
    value: '',
    efkIndex: '',
    output: ''
  });
  function generateLinekey() {
    if (linekeyGen.brand === 'Yealink') {
      setLinekeyGen(lk => ({
        ...lk,
        output:
          `linekey.${lk.lineNum}.label=${lk.label}\n` +
          `linekey.${lk.lineNum}.line=${lk.regLine}\n` +
          `linekey.${lk.lineNum}.type=${lk.type}\n` +
          `linekey.${lk.lineNum}.value=${lk.value}\n`
    }));
    } else {
      setLinekeyGen(lk => ({
        ...lk,
        output:
          `attendant.resourcelist.${lk.efkIndex}.address=${lk.value}\n` +
          `attendant.resourcelist.${lk.efkIndex}.label=${lk.label}\n` +
          `attendant.resourcelist.${lk.efkIndex}.type=normal\n` +
          `linekey.${lk.lineNum}.category=BLF\n` +
          `linekey.${lk.lineNum}.index=${lk.efkIndex}\n`
      }));
    }
  }

  // Reference sub-navigation state (move to top for scope)
  const REFERENCE_SUBTABS = [
    { key: 'phones', label: "Phones" },
    { key: 'mikrotik', label: "Mikrotik" },
    { key: 'switches', label: "Switches" },
    { key: 'pbx', label: "PBX's" },
  ];
  const [referenceSubtab, setReferenceSubtab] = useState('phones');

  // --- OTT Mikrotik Template Editor State ---
  // const [ottFields, setOttFields] = useState({
  //   ip: '',
  //   customerName: '',
  //   customerAddress: '',
  //   city: '',
  //   xip: '',
  //   handle: '',
  // });
  // function getOttTemplate(fields: typeof ottFields) {
  //   // return ottMikrotikTemplate
  //   //   .replace('XXX.XXX.XXX.XXX', fields.ip || 'XXX.XXX.XXX.XXX')
  //   //   .replace('"CUSTOMER NAME"', fields.customerName || '"CUSTOMER NAME"')
  //   //   .replace('"CUSTOMER ADDRESS"', fields.customerAddress || '"CUSTOMER ADDRESS"')
  //   //   .replace('"CITY"', fields.city || '"CITY"')
  //   //   .replace('"XIP"', fields.xip || '"XIP"')
  //   //   .replace('"HANDLE-CUSTOMERADDRESS"', fields.handle || '"HANDLE-CUSTOMERADDRESS"');
  //   return '';
  // }

  // Main UI rendering
  return (
    <div className="appShell">
      <header className="brandHeader">
        <a className="brandLogo" href="/" aria-label="123NET">
          <img src="/123net-logo.png" alt="123NET" />
        </a>
        <div className="brandHeaderText">
          <div className="brandAppName">Hosted Config Generator</div>
          <div className="brandMeta">Connected to {clientInfo.hostname}:{clientInfo.port}</div>
        </div>
        <button
          type="button"
          className="dark-mode-btn"
          onClick={() => setDarkMode(d => !d)}
          title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {darkMode ? '☀ Light' : '☾ Dark'}
        </button>
      </header>

      <main className="container">
      <div className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={activeTab === tab.key ? 'active' : ''}
            onClick={() => setActiveTab(tab.key)}

          >
            {tab.label}
          </button>
        ))}
      </div>
      <hr />
      {/* Tab content rendering */}
      {activeTab === 'reference' && (
        <div className="ref-container">
          <h2 className="ref-h2">Reference</h2>
          {/* Sub-navigation menu */}
          <div className="ref-subnav">
            {REFERENCE_SUBTABS.map(sub => (
              <button
                key={sub.key}
                className={referenceSubtab === sub.key ? 'active' : ''}
                onClick={() => setReferenceSubtab(sub.key)}

              >
                {sub.label}
              </button>
            ))}
          </div>
          {/* Subtab content */}
          <div className="ref-content">
            {referenceSubtab === 'phones' && (
              <div className="ref-section">
                <h2>Phone Config Reference (Legend)</h2>
                <div className="ref-tables-flex">
                  {/* Polycom Reference Table */}
                  <div className="ref-brand-col">
                    <h3>Polycom</h3>
                    <table className="reference-table">
                      <thead>
                        <tr>
                          <th>Setting</th>
                          <th>Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr><td><code>attendant.resourcelist.X.address</code></td><td>BLF/park/extension address (e.g. 1001@ip)</td></tr>
                        <tr><td><code>attendant.resourcelist.X.label</code></td><td>Button label (displayed on phone)</td></tr>
                        <tr><td><code>attendant.resourcelist.X.type</code></td><td>Type of key (<b>automata</b> for BLF/park, <b>normal</b> for speed dial)</td></tr>
                        <tr><td><code>linekey.X.category</code></td><td>Key category (<b>BLF</b>, <b>EFK</b>)</td></tr>
                        <tr><td><code>efk.efklist.X.action.string</code></td><td>Macro or feature key action (e.g. transfer, record, external number)</td></tr>
                        <tr><td><code>feature.enhancedFeatureKeys.enabled</code></td><td>Enable enhanced feature keys (macros, advanced features)</td></tr>
                        <tr><td><code>linekey.X.index</code></td><td>Index of the key (matches resourcelist or efklist)</td></tr>
                        <tr><td><code>efk.efkprompt.X.label</code></td><td>Prompt label for user input (numeric, string, etc.)</td></tr>
                        <tr><td><code>feature.EFKLineKey.enabled</code></td><td>Enable EFK line key macros</td></tr>
                      </tbody>
                    </table>
                    <h4 className="ref-h4">Common Polycom Features</h4>
                    <ul className="ref-ul">
                      <li><b>BLF (Busy Lamp Field):</b> Monitors extension/park status, lights up when in use.</li>
                      <li><b>Speed Dial:</b> Quick dial to a number or extension.</li>
                      <li><b>EFK (Enhanced Feature Key):</b> Macro for advanced actions (e.g. transfer, record, external call).</li>
                      <li><b>Expansion Module:</b> Extra programmable keys for sidecar modules.</li>
                    </ul>
                  </div>
                  {/* Yealink Reference Table */}
                  <div className="ref-brand-col">
                    <h3>Yealink</h3>
                    <table className="reference-table">
                      <thead>
                        <tr>
                          <th>Setting</th>
                          <th>Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr><td><code>linekey.X.extension</code></td><td>Extension or park number assigned to key</td></tr>
                        <tr><td><code>linekey.X.label</code></td><td>Button label (displayed on phone)</td></tr>
                        <tr><td><code>linekey.X.type</code></td><td>Type of key (<b>10</b> for BLF, <b>13</b> for speed dial, <b>3</b> for transfer-to-VM)</td></tr>
                        <tr><td><code>linekey.X.value</code></td><td>Value for the key (e.g. extension@ip, feature code)</td></tr>
                        <tr><td><code>features.enhanced_dss_keys.enable</code></td><td>Enable enhanced DSS keys (advanced features/macros)</td></tr>
                        <tr><td><code>feature.enhancedFeatureKeys.enabled</code></td><td>Enable enhanced feature keys (macros, advanced features)</td></tr>
                        <tr><td><code>expansion_module.Y.key.Z.label</code></td><td>Label for expansion module key (sidecar)</td></tr>
                        <tr><td><code>expansion_module.Y.key.Z.type</code></td><td>Type of expansion key (<b>16</b> for BLF, <b>13</b> for speed dial)</td></tr>
                        <tr><td><code>expansion_module.Y.key.Z.value</code></td><td>Value for expansion key (e.g. extension@ip)</td></tr>
                      </tbody>
                    </table>
                    <h4 className="ref-h4">Common Yealink Features</h4>
                    <ul className="ref-ul">
                      <li><b>BLF (Busy Lamp Field):</b> Monitors extension/park status, lights up when in use (type=10).</li>
                      <li><b>Speed Dial:</b> Quick dial to a number or extension (type=13).</li>
                      <li><b>Transfer to VM:</b> Direct transfer to voicemail (type=3, value=*ext@ip).</li>
                      <li><b>Expansion Module:</b> Extra programmable keys for sidecar modules (expansion_module.Y.key.Z.*).</li>
                      <li><b>Enhanced DSS/Feature Keys:</b> Enable advanced macros and prompts.</li>
                    </ul>
                  </div>
                </div>
              </div>
            )}
            {referenceSubtab === 'mikrotik' && (
              <div className="ref-section">
                <h3>Mikrotik Reference</h3>
                <div className="ref-card">
                  <h4>What does each Mikrotik config template do?</h4>
                  <ul>
                    <li>
                      <b>OTT Mikrotik Template (Editable):</b>
                      <br />
                      This configuration template is designed for Over-The-Top (OTT) VoIP or data deployments, where the Mikrotik router is installed at a customer location and connects back to the service provider over a public or third-party WAN. It allows users to fill in site-specific variables (IP addresses, customer info, gateway, etc.) and generates a fully pre-configured, drop-in-ready script for provisioning.
                      <ul>
                        <li><b>WAN and LAN Setup:</b> Configures ether10 as the uplink to the customer’s internet router and assigns a static WAN IP. Internal VLANs (e.g., VLAN 202 for phones, VLAN 102 for local management) are trunked through ether9 back to 123Net.</li>
                        <li><b>DHCP Services for VoIP Phones:</b> Provides DHCP on the phone VLAN with custom DHCP options (66, 160, 202) for provisioning server URLs, VLAN tagging, and NTP synchronization. This enables plug-and-play VoIP phone deployment.</li>
                        <li><b>Firewall Rules and Filtering:</b> Includes security policies that allow only trusted IPs to manage the router, permit traffic from the phone VLAN, management subnets, and PBX networks, and block all other inbound connections by default. SIP helper services are disabled for improved SIP handling.</li>
                        <li><b>Address Lists for Management & Services:</b> Pre-defined address lists for management (MGMT), phone VLANs, PBX access, and backend tools (BT) simplify rule creation and policy enforcement.</li>
                        <li><b>SNMP and Time Settings:</b> Enables SNMP with customer-specific metadata, sets local timezone, NTP servers, and router hostname to reflect site identity.</li>
                        <li><b>Connection Tracking Optimization:</b> Sets a reduced UDP timeout (1m30s) to improve VoIP call stability and avoid lingering sessions.</li>
                        <li><b>Pre-Built NAT Rules:</b> Configures masquerading for the VoIP phone subnet to allow internet access for phones or remote provisioning.</li>
                      </ul>
                      <b>Use Case:</b> Ideal for remote site deployments where full routing/NAT is handled by an upstream customer router. This template simplifies the process of deploying and managing Mikrotik routers for hosted VoIP or data services without requiring manual configuration each time.
                    </li>
                    <li>
                      <b>Mikrotik 5009 Bridge Template:</b>
                      <br />
                      This template provides a configuration for the MikroTik RB5009 router operating in bridge mode, ideal for transparent network pass-through or segmentation without performing NAT or routing. It is commonly used to connect customer premises equipment to the core network or to isolate VoIP traffic via dedicated interfaces.
                      <ul>
                        <li><b>Bridge Interface Creation:</b> A logical bridge interface named <code>Phones</code> aggregates multiple physical interfaces and VLANs, simplifying management and centralizing DHCP and firewall control.</li>
                        <li><b>Interface Assignment for VoIP:</b> Ports <code>ether4</code> and <code>ether5</code> are assigned for hosted VoIP devices and labeled for clarity. These ports are added to the Phones bridge to allow devices on either port to share the same Layer 2 network.</li>
                        <li><b>VLAN Support:</b> A VLAN interface (<code>vlan202</code>) with ID 202 is created on the Phones bridge, allowing for traffic segmentation and service-specific policies (e.g., dedicated VoIP traffic pathing).</li>
                        <li><b>DHCP Services:</b> A small IP pool (172.16.1.3–172.16.1.10) and DHCP server are configured on the Phones bridge to provide automatic addressing to VoIP endpoints. DNS servers (e.g., 1.1.1.1 and 8.8.8.8) and a gateway (172.16.1.1) are assigned to ensure basic internet and provisioning access.</li>
                        <li><b>Static IP Assignment for Bridge Gateway:</b> The bridge interface is given a static IP of 172.16.1.1/24, serving as the default gateway for connected phones.</li>
                        <li><b>Firewall Address Lists and NAT:</b>
                          <ul>
                            <li>An address list for management (MGMT) includes the local subnet and specific remote management IPs.</li>
                            <li>A masquerade rule ensures that devices behind the bridge can reach external networks (e.g., for provisioning) without requiring upstream NAT configuration.</li>
                          </ul>
                        </li>
                        <li><b>Connection Tracking Optimization:</b> The UDP timeout is shortened to 1m30s, which helps prevent stale SIP sessions and improves call reliability.</li>
                        <li><b>Service Port Hardening:</b> SIP helper services and legacy protocols like FTP, TFTP, and PPTP are explicitly disabled to reduce unwanted interference and attack surface.</li>
                      </ul>
                      <b>Use Case:</b> This template is ideal for transparently bridging VoIP phones or customer hardware through the MikroTik RB5009 to an upstream switch or router. It is especially useful when:
                      <ul>
                        <li>You need to segment VoIP traffic but avoid routing/NAT on-site.</li>
                        <li>You want central DHCP and firewall control.</li>
                        <li>You’re deploying hosted phones that require isolated Layer 2 environments.</li>
                      </ul>
                    </li>
                    <li>
                      <b>Mikrotik 5009 Passthrough Template:</b>
                      <br />
                      This configuration template sets up the MikroTik RB5009 router in passthrough mode, enabling transparent traffic forwarding between customer devices and the core network. It is ideal for scenarios where routing, NAT, or complex processing is not required at the customer edge, but DHCP tagging, service segregation, and firewall policy enforcement are still needed.
                      <ul>
                        <li><b>Tagged VLAN Configuration (Trunk Port):</b> VLANs 102 and 202 are configured on a shared physical interface (typically ether7) to separate traffic into logical segments:
                          <ul>
                            <li><b>vlan102:</b> Management traffic (e.g., local admin access)</li>
                            <li><b>vlan202:</b> Hosted VoIP phones and services</li>
                          </ul>
                        </li>
                        <li><b>Advanced DHCP Option Support:</b> Implements custom DHCP option sets for phones using options 66, 160, 202, and more to automate provisioning:
                          <ul>
                            <li><b>Option 66/160:</b> Points phones to the provisioning server</li>
                            <li><b>Option 202:</b> Injects VLAN tagging info for phone boot VLANs</li>
                            <li><b>Option 42/2:</b> NTP and GMT offset settings</li>
                          </ul>
                        </li>
                        <li><b>DHCP Server and IP Pool for VoIP Phones:</b> Assigns phones in VLAN 202 addresses from 172.16.1.30–172.16.1.250 and handles DNS, NTP, and gateway assignment via DHCP.</li>
                        <li><b>IP Addressing for Management and VoIP VLANs:</b> Static IPs are assigned to each VLAN interface (e.g., 192.168.10.1/24 on VLAN 102, 172.16.1.1/24 on VLAN 202) for interface-level control and monitoring.</li>
                        <li><b>Firewall Address Lists for Policy Enforcement:</b> Pre-defined address lists group management (MGMT), phone (PHONEVLAN), and PBX servers (PBX), simplifying rules and securing control plane access.</li>
                        <li><b>Firewall Rules:</b>
                          <ul>
                            <li>Allows passthrough traffic (forward chain) from customer to core</li>
                            <li>Explicitly allows traffic from phones and PBX servers</li>
                            <li>Drops everything else by default (best practice: add drop rule at end if not already defined)</li>
                          </ul>
                        </li>
                        <li><b>NAT Masquerading for Phone Subnet:</b> Ensures phones behind the RB5009 can reach the internet (e.g., for provisioning) even without upstream NAT configuration.</li>
                        <li><b>UDP Timeout Optimization for SIP:</b> Sets a reduced UDP timeout of 1m30s, improving SIP call handling and avoiding dropped sessions due to inactive UDP bindings.</li>
                        <li><b>Disabled Legacy Service Ports:</b> FTP, TFTP, SIP ALG, and other protocols that interfere with hosted VoIP are fully disabled to enhance security and ensure compatibility with SIP endpoints.</li>
                      </ul>
                      <b>Use Case:</b> The 5009 Passthrough Template is ideal for drop-in deployments where:
                      <ul>
                        <li>The RB5009 is acting as a bridge or VLAN-aware switch at the edge.</li>
                        <li>No customer-side NAT/routing is needed.</li>
                        <li>The device must enforce DHCP option tagging and basic security policies.</li>
                        <li>Hosted VoIP phones or segmented VLAN services are in use.</li>
                        <li>You need a "touchless" provisioning-ready passthrough router that’s easy to deploy and manage remotely.</li>
                      </ul>
                    </li>
                    <li>
                      <b>OnNet Mikrotik Config Template:</b>
                      <br />
                      Used for "OnNet" (on-network) deployments, this template configures the Mikrotik for integration with the provider’s core network, including VLANs, routing, and security settings.
                    </li>
                    <li>
                      <b>Mikrotik StandAlone ATA Template:</b>
                      <br />
                      Provides configuration for using a Mikrotik router with a stand-alone Analog Telephone Adapter (ATA), ensuring proper voice VLAN, QoS, and network isolation for analog phone devices.
                    </li>
                    <li>
                      <b>Mikrotik DHCP Options:</b>
                      <br />
                      Contains DHCP option settings for Mikrotik routers, such as custom options for VoIP phones (e.g., provisioning server, VLAN assignment) to automate device configuration on the network.
                    </li>
                  </ul>
                </div>
                <p>Use the Mikrotik tab to view and generate these configuration templates.</p>
              </div>
            )}
            {referenceSubtab === 'switches' && (
              <div className="ref-section">
                <h3>Switches Reference</h3>
                <div className="ref-card">
                  <h4>What does each Switch config template do?</h4>
                  <ul>
                    <li>
                      <b>Dynamic Switch Template:</b>
                      <br />
                      This template allows you to generate switch configuration code dynamically based on user input. It is useful for customizing VLANs, port assignments, and other switch features for a variety of deployment scenarios.
                    </li>
                    <li>
                      <b>24-Port Switch Template:</b>
                      <br />
                      Provides a ready-to-use configuration for a standard 24-port managed switch. It typically includes default VLAN assignments, trunk/access port settings, and recommended security options for VoIP and data networks.
                    </li>
                    <li>
                      <b>8-Port Switch Template:</b>
                      <br />
                      Supplies configuration for an 8-port managed switch, optimized for small deployments or edge locations. It includes basic VLAN setup, port roles, and example settings for voice/data separation.
                    </li>
                  </ul>
                </div>
                <p>Use the Switch Templates tab to view and generate these configuration templates for your network switches.</p>
              </div>
            )}
            {referenceSubtab === 'pbx' && (
              <div className="ref-section">
                <h3>PBX Reference</h3>
                <div className="ref-card">
                  <h4>PBX Import/Export and Config Types</h4>
                  <ul>
                    <li>
                      <b>FreePBX:</b>
                      <br />
                      FreePBX is an open-source PBX platform based on Asterisk. The FBPX and VPBX import templates in this app are designed to help you bulk import user/extension data into FreePBX systems, making onboarding and configuration faster and less error-prone.
                    </li>
                    <li>
                      <b>UCaaS (Unified Communications as a Service):</b>
                      <br />
                      UCaaS platforms provide cloud-based PBX and collaboration features. Use the import/export templates to prepare user and device data for onboarding to various UCaaS providers.
                    </li>
                    <li>
                      <b>Fusion:</b>
                      <br />
                      Fusion is a hosted PBX/UCaaS platform. The import templates can be adapted to Fusion’s requirements for bulk provisioning of phones and users.
                    </li>
                    <li>
                      <b>Intermedia:</b>
                      <br />
                      Intermedia is a popular cloud PBX and UCaaS provider. Use the provided templates as a starting point for preparing user and device data for Intermedia’s provisioning tools.
                    </li>
                  </ul>
                </div>
                <p>
                  Use the FBPX and VPBX Import Template tabs to generate and export CSV files for bulk provisioning of users, extensions, and devices on these PBX platforms.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
      {/* Phone Configs Tab */}
      {activeTab === 'phone' && (
        <>
          <h2 className="section-h2">Step 1 — Phone Config Generator</h2>
          {/* Mode banner */}
          {configMode === 'edit' && loadedDeviceMeta ? (
            <div className="edit-mode-banner">
              <span className="edit-mode-label">
                ✎ Edit Existing — {loadedDeviceMeta.handleName || loadedDeviceMeta.handle} &nbsp;·&nbsp;
                {loadedDeviceMeta.directoryName || loadedDeviceMeta.deviceId} &nbsp;·&nbsp;
                ext {loadedDeviceMeta.extension} &nbsp;·&nbsp; {loadedDeviceMeta.make} {loadedDeviceMeta.model}
              </span>
              <button
                type="button"
                className="edit-mode-clear-btn"
                onClick={() => {
                  setConfigMode('new');
                  setLoadedConfigRaw('');
                  setLoadedDeviceMeta(null);
                  setScraperHandle('');
                  setScraperDevices([]);
                  setScraperDevice('');
                  setScraperLiveConfig('');
                }}
              >
                ✕ Clear — start new config
              </button>
            </div>
          ) : (
            <div className="new-mode-banner">
              <span className="new-mode-label">⊕ New Config mode</span>
              <span className="new-mode-hint">Load a device from the scraper panel below to switch to Edit mode</span>
            </div>
          )}
          <div className="info-box">
            <h3>What does each config generator do?</h3>
            <ul>
              <li><b>Base Config Options:</b> Generates the main configuration for Polycom or Yealink phones, including park/BLF keys, static settings, and model-specific options.</li>
              <li><b>Polycom MWI (Message Waiting Indicator):</b> Generates config lines to enable voicemail message waiting light for a specific extension and PBX IP.</li>
              <li><b>Linekey/BLF/Speed/Transfer/Hotkey Generator:</b> Creates config for individual programmable keys (BLF, speed dial, transfer, macros) for Yealink or Polycom phones.</li>
              <li><b>External Number Speed Dial:</b> Generates config for a button that dials an external number directly from the phone.</li>
            </ul>
          </div>
          {/* ── Webscraper: handle + device selectors ── */}
          <div className="scraper-panel">
            <div className="scraper-header">
              <strong className="scraper-strong">Load from Webscraper</strong>
              <span className={scraperOnlinePhone === null ? 'scraper-status-pending' : scraperOnlinePhone ? 'scraper-status-online' : 'scraper-status-offline'}>
                {scraperOnlinePhone === null ? '…' : scraperOnlinePhone ? '● connected' : '○ offline'}
              </span>
            </div>
            <div className="scraper-select-row">
              <label htmlFor="phone-scraper-handle" className="scraper-label">Handle:</label>
              <select
                id="phone-scraper-handle"
                value={scraperHandle}
                onChange={e => { setScraperHandle(e.target.value); loadScraperDevices(e.target.value); }}
                disabled={!scraperOnlinePhone}
                className="scraper-handle-select"
                title="Select a company handle to load scraped devices"
              >
                <option value="">— select handle —</option>
                {scraperHandles.map(h => (
                  <option key={h.handle} value={h.handle}>{h.handle} — {h.name}</option>
                ))}
              </select>
              {scraperDevices.length > 0 && (
                <>
                  <label htmlFor="phone-scraper-device" className="scraper-label">Device:</label>
                  <select
                    id="phone-scraper-device"
                    value={scraperDevice}
                    onChange={e => applyScraperDevice(e.target.value)}
                    className="scraper-device-select"
                    title="Select a device to view its current scraped config"
                  >
                    <option value="">— select device —</option>
                    {scraperDevices.map(d => (
                      <option key={d.device_id} value={d.device_id}>
                        {d.directory_name || d.device_id} · ext {d.extension || '?'} · {d.make} {d.model}
                      </option>
                    ))}
                  </select>
                </>
              )}
            </div>
            {!scraperOnlinePhone && scraperOnlinePhone !== null && (
              <p className="scraper-offline">
                Webscraper offline — start it at localhost:8788 to enable live load.
              </p>
            )}
          </div>

          {/* ── Current Scraped Config ────────────────── */}
          {scraperDevice && (
            <div className="current-config-panel">
              <div className="current-config-header">
                <span className="current-config-title">Current Scraped Config</span>
                {loadedDeviceMeta && (
                  <div className="current-config-meta">
                    <span className="current-config-meta-item"><b>Device:</b> {loadedDeviceMeta.directoryName || loadedDeviceMeta.deviceId}</span>
                    <span className="current-config-meta-sep">·</span>
                    <span className="current-config-meta-item"><b>Ext:</b> {loadedDeviceMeta.extension || '—'}</span>
                    <span className="current-config-meta-sep">·</span>
                    <span className="current-config-meta-item"><b>Model:</b> {loadedDeviceMeta.make} {loadedDeviceMeta.model}</span>
                    {loadedDeviceMeta.mac && (
                      <>
                        <span className="current-config-meta-sep">·</span>
                        <span className="current-config-meta-item"><b>MAC:</b> {loadedDeviceMeta.mac}</span>
                      </>
                    )}
                    {(() => {
                      const dev = scraperDevices.find(d => d.device_id === scraperDevice);
                      return dev && (dev as unknown as Record<string, string>)['last_seen_utc'] ? (
                        <>
                          <span className="current-config-meta-sep">·</span>
                          <span className="current-config-meta-item"><b>Last scraped:</b> {(dev as unknown as Record<string, string>)['last_seen_utc'].replace('T', ' ').replace('Z', ' UTC')}</span>
                        </>
                      ) : null;
                    })()}
                  </div>
                )}
              </div>

              {currentConfigLoading && (
                <p className="current-config-loading">Loading config…</p>
              )}
              {currentConfigError && !currentConfigLoading && (
                <p className="current-config-error">{currentConfigError}</p>
              )}
              {!currentConfigLoading && !currentConfigError && scraperLiveConfig && (
                <>
                  {currentConfigParsed && currentConfigParsed.unparsedCount > 0 && (
                    <p className="current-config-warning">
                      ⚠ {currentConfigParsed.unparsedCount} line{currentConfigParsed.unparsedCount !== 1 ? 's' : ''} in this config are not mapped to editable fields — they will be preserved as-is.
                    </p>
                  )}
                  <textarea
                    className="current-config-textarea"
                    readOnly
                    rows={12}
                    value={scraperLiveConfig}
                    title="Current scraped config for selected device"
                  />
                  <div className="current-config-actions">
                    <button
                      type="button"
                      className="current-config-load-btn"
                      onClick={loadCurrentConfigIntoForm}
                      title="Map known config values into the generator form fields below"
                    >
                      ↓ Load Current Config Into Form
                    </button>
                    {configMode === 'edit' && (
                      <button
                        type="button"
                        className="scraper-reset-btn"
                        onClick={resetToLoaded}
                        title="Reset form fields back to what was loaded from this config"
                      >
                        ↺ Reset to loaded
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
          {/* Base Config Options Form */}
          <div className="form-section">
            <h3>Base Config Options</h3>
            <div className="config-grid">
              <div className="config-field">
                <label className="config-label">Phone Type <span className="info-icon" title={FIELD_TOOLTIPS.phoneType}><FaInfoCircle /></span></label>
                <select value={phoneType} title="Select phone type" onChange={e => setPhoneType(e.target.value as 'Polycom' | 'Yealink')}>
                  <option value="Polycom">Polycom</option>
                  <option value="Yealink">Yealink</option>
                </select>
              </div>
              <div className="config-field config-field--wide">
                <label className="config-label">Model <span className="info-icon" title={FIELD_TOOLTIPS.model}><FaInfoCircle /></span></label>
                <select value={model} title="Select phone model" onChange={e => setModel(e.target.value)}>
                  {MODEL_OPTIONS.map(opt => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              </div>
              <div className="config-field">
                <label className="config-label">IP Address <span className="info-icon" title={FIELD_TOOLTIPS.ip}><FaInfoCircle /></span></label>
                <input type="text" value={ip} onChange={e => setIp(e.target.value)} placeholder="e.g. 192.168.1.100" />
              </div>
              <div className="config-field">
                <label className="config-label">Start Extension <span className="info-icon" title={FIELD_TOOLTIPS.startExt}><FaInfoCircle /></span></label>
                <input type="number" value={startExt} title="Start extension" onChange={e => setStartExt(e.target.value)} />
              </div>
              <div className="config-field">
                <label className="config-label">End Extension <span className="info-icon" title={FIELD_TOOLTIPS.endExt}><FaInfoCircle /></span></label>
                <input type="number" value={endExt} title="End extension" onChange={e => setEndExt(e.target.value)} />
              </div>
              <div className="config-field">
                <label className="config-label">Label Prefix <span className="info-icon" title={FIELD_TOOLTIPS.labelPrefix}><FaInfoCircle /></span></label>
                <input type="text" value={labelPrefix} title="Label prefix" onChange={e => setLabelPrefix(e.target.value)} />
              </div>
              <div className="config-field">
                <label className="config-label">Time Offset <span className="info-icon" title={FIELD_TOOLTIPS.timeOffset}><FaInfoCircle /></span></label>
                <input type="number" value={timeOffset} title="Time offset (e.g. -5)" onChange={e => setTimeOffset(e.target.value)} />
              </div>
              <div className="config-field">
                <label className="config-label">Admin Password <span className="info-icon" title={FIELD_TOOLTIPS.adminPassword}><FaInfoCircle /></span></label>
                <input type="text" value={adminPassword} title="Admin password" onChange={e => setAdminPassword(e.target.value)} />
              </div>
              <div className="config-field config-field--checkboxes">
                <label className="config-label">Yealink Options</label>
                <div className="config-checkboxes">
                  <label><input type="checkbox" checked={yealinkLabelLength} onChange={e => setYealinkLabelLength(e.target.checked)} /> Long DSS key labels <span className="info-icon" title={FIELD_TOOLTIPS.yealinkLabelLength}><FaInfoCircle /></span></label>
                  <label><input type="checkbox" checked={yealinkDisableMissedCall} onChange={e => setYealinkDisableMissedCall(e.target.checked)} /> Disable missed call alert <span className="info-icon" title={FIELD_TOOLTIPS.yealinkDisableMissedCall}><FaInfoCircle /></span></label>
                  <label><input type="checkbox" checked={yealinkCallStealing} onChange={e => setYealinkCallStealing(e.target.checked)} /> Enable BLF call stealing <span className="info-icon" title={FIELD_TOOLTIPS.yealinkCallStealing}><FaInfoCircle /></span></label>
                </div>
              </div>
            </div>
            <button onClick={generateConfig} className="btn-mt">Generate Config</button>
            <div className="output">
              <textarea title="Generated config output" value={output} readOnly rows={10} className="full-width-ta" />
            </div>
          </div>
          {/* Polycom MWI Section — collapsible */}
          <hr />
          <div className="form-section">
            <button
              type="button"
              className="adv-section-toggle"
              onClick={() => setShowMWI(v => !v)}
            >
              <span className="adv-section-chevron">{showMWI ? '▾' : '▸'}</span>
              Polycom MWI (Message Waiting Indicator)
              <span className="adv-section-badge">Advanced</span>
            </button>
            {showMWI && (
              <div className="adv-section-body">
                <div className="form-group">
                  <label>Extension:
                    <span className="info-icon" title={FIELD_TOOLTIPS.polycomMWIExt}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={polycomMWI.ext} title="MWI extension" onChange={e => setPolycomMWI(mwi => ({ ...mwi, ext: e.target.value }))} />
                  <label className="label-ml">PBX IP:
                    <span className="info-icon" title={FIELD_TOOLTIPS.polycomMWIPbxIp}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={polycomMWI.pbxIp} title="PBX IP for MWI" onChange={e => setPolycomMWI(mwi => ({ ...mwi, pbxIp: e.target.value }))} />
                </div>
                <button onClick={generatePolycomMWI} className="btn-mt">Generate Polycom MWI Config</button>
                <div className="output">
                  <textarea title="Generated Polycom MWI config" value={polycomMWI.output} readOnly rows={5} className="full-width-ta" />
                </div>
              </div>
            )}
          </div>
          {/* Linekey Generator Section — collapsible */}
          <hr />
          <div className="form-section">
            <button
              type="button"
              className="adv-section-toggle"
              onClick={() => setShowLinekeyGen(v => !v)}
            >
              <span className="adv-section-chevron">{showLinekeyGen ? '▾' : '▸'}</span>
              Linekey / BLF / Speed Dial Generator
              <span className="adv-section-badge">Advanced</span>
            </button>
            {showLinekeyGen && (
              <div className="adv-section-body">
                <div className="form-group">
                  <label>Brand:</label>
                  <select value={linekeyGen.brand} title="Select phone brand" onChange={e => setLinekeyGen(lk => ({ ...lk, brand: e.target.value }))}>
                    <option value="Yealink">Yealink</option>
                    <option value="Polycom">Polycom</option>
                  </select>
                  <label className="label-ml">Line Key Number:
                    <span className="info-icon" title={FIELD_TOOLTIPS.linekeyNum}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={linekeyGen.lineNum} title="Line key number" onChange={e => setLinekeyGen(lk => ({ ...lk, lineNum: e.target.value }))} />
                  <label className="label-ml">Label:
                    <span className="info-icon" title={FIELD_TOOLTIPS.linekeyLabel}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={linekeyGen.label} title="Label for the key" onChange={e => setLinekeyGen(lk => ({ ...lk, label: e.target.value }))} />
                  <label className="label-ml">Register Line:
                    <span className="info-icon" title={FIELD_TOOLTIPS.linekeyRegLine}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={linekeyGen.regLine} title="Register line number" onChange={e => setLinekeyGen(lk => ({ ...lk, regLine: e.target.value }))} />
                  <label className="label-ml">Type:
                    <span className="info-icon" title={FIELD_TOOLTIPS.linekeyType}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <select value={linekeyGen.type} title="Linekey type" onChange={e => setLinekeyGen(lk => ({ ...lk, type: parseInt(e.target.value) }))}>
                    {YEALINK_LINEKEY_TYPES.map(t => (
                      <option key={t.code} value={t.code}>{t.code} - {t.label}</option>
                    ))}
                  </select>
                  <label className="label-ml">Value:
                    <span className="info-icon" title={FIELD_TOOLTIPS.linekeyValue}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={linekeyGen.value} title="Extension or number value" onChange={e => setLinekeyGen(lk => ({ ...lk, value: e.target.value }))} />
                </div>
                <button type="button" onClick={generateLinekey} className="btn-mt">Generate Linekey Config</button>
                <div className="output">
                  <textarea title="Generated linekey config" value={linekeyGen.output} readOnly rows={5} className="full-width-ta" />
                </div>
              </div>
            )}
          </div>
          {/* External Number Speed Dial Section — collapsible */}
          <hr />
          <div className="form-section">
            <button
              type="button"
              className="adv-section-toggle"
              onClick={() => setShowExternalSpeed(v => !v)}
            >
              <span className="adv-section-chevron">{showExternalSpeed ? '▾' : '▸'}</span>
              External Number Speed Dial
              <span className="adv-section-badge">Advanced</span>
            </button>
            {showExternalSpeed && (
              <div className="adv-section-body">
                <div className="form-group">
                  <label>Brand:
                    <span className="info-icon" title={FIELD_TOOLTIPS.externalBrand}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <select value={externalSpeed.brand} title="Select phone brand" onChange={e => setExternalSpeed(s => ({ ...s, brand: e.target.value }))}>
                    <option value="Yealink">Yealink</option>
                    <option value="Polycom">Polycom</option>
                  </select>
                  <label className="label-ml">Line Key Number:
                    <span className="info-icon" title={FIELD_TOOLTIPS.externalLineNum}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={externalSpeed.lineNum} title="Line key number" onChange={e => setExternalSpeed(s => ({ ...s, lineNum: e.target.value }))} />
                  <label className="label-ml">Label:
                    <span className="info-icon" title={FIELD_TOOLTIPS.externalLabel}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={externalSpeed.label} title="Speed dial label" onChange={e => setExternalSpeed(s => ({ ...s, label: e.target.value }))} />
                  <label className="label-ml">External Number:
                    <span className="info-icon" title={FIELD_TOOLTIPS.externalNumber}>
                      <FaInfoCircle />
                    </span>
                  </label>
                  <input type="text" value={externalSpeed.number} title="External number to dial" onChange={e => setExternalSpeed(s => ({ ...s, number: e.target.value }))} />
                  {externalSpeed.brand === 'Polycom' && (
                    <>
                      <label className="label-ml">EFK Index:</label>
                      <input type="text" value={externalSpeed.efkIndex} title="EFK index for Polycom" onChange={e => setExternalSpeed(s => ({ ...s, efkIndex: e.target.value }))} />
                    </>
                  )}
                  <button type="button" onClick={generateExternalSpeed} className="label-ml">Generate External Speed Dial</button>
                </div>
                <div className="output">
                  <textarea title="Generated speed dial config" value={externalSpeedOutput} readOnly rows={5} className="full-width-ta" />
                </div>
              </div>
            )}
          </div>
        </>
      )}
      {activeTab === 'expansion' && (
        <div className="expansion-container">
          <h2 className="expansion-h2">Step 2 — Expansion Module Code Generators</h2>
          <div className="expansion-flex">
            {/* Yealink Section */}
            <div className="expansion-col">
              <img src="/expansion/yealinkexp40.jpeg" alt="Yealink EXP40" className="expansion-img" />
              <img src="/expansion/yealinkexp50.jpeg" alt="Yealink EXP50" className="expansion-img" />
              <div className="expansion-instructions">
                <b>Instructions:</b> Fill out the form below to generate a config for a Yealink expansion key. Use the page &amp; line to preview the key visually. Hover over any icon for field details.
              </div>
              <div className="form-group expansion-form-group">
                <label>Template Type:
                  <span title="BLF for Busy Lamp Field, Speed Dial for quick dial keys" className="info-icon">
                    <FaInfoCircle />
                  </span>
                </label>
                <select value={yealinkSection.templateType} title="Expansion template type" onChange={e => setYealinkSection(s => ({ ...s, templateType: e.target.value }))}>
                  <option value="BLF">BLF</option>
                  <option value="SpeedDial">Speed Dial</option>
                </select>
                <label className="label-ml">Sidecar Page:
                  <span title="Sidecar page number (1, 2, etc.)" className="info-icon">
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="number" min={1} max={3} value={yealinkSection.sidecarPage} title="Sidecar page (1-3)" onChange={e => setYealinkSection(s => ({ ...s, sidecarPage: e.target.value }))} className="narrow-input" />
                <label className="label-ml">Sidecar Line:
                  <span title="Button position on the sidecar (1-20)" className="info-icon">
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="number" min={1} max={20} value={yealinkSection.sidecarLine} title="Button position (1-20)" onChange={e => setYealinkSection(s => ({ ...s, sidecarLine: e.target.value }))} className="narrow-input" />
                <label className="label-ml">Label:
                  <span title="Text label shown on the phone's display for this key." className="info-icon">
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="text" value={yealinkSection.label} title="Key label text" onChange={e => setYealinkSection(s => ({ ...s, label: e.target.value }))} />
                <label className="label-ml">Value (Phone/ext):
                  <span title="Extension, number, or SIP URI for this key." className="info-icon">
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="text" value={yealinkSection.value} title="Extension or SIP URI" onChange={e => setYealinkSection(s => ({ ...s, value: e.target.value }))} />
                <label className="label-ml">PBX IP:
                  <span title="PBX IP address for BLF keys (required for BLF type)." className="info-icon">
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="text" value={yealinkSection.pbxIp} title="PBX IP for BLF" onChange={e => setYealinkSection(s => ({ ...s, pbxIp: e.target.value }))} />
              </div>
              <button onClick={generateYealinkExpansion} className="btn-mt btn-mr">Generate Yealink Expansion Config</button>
              <button onClick={generateYealinkExpansionAll} className="btn-mt">Generate All 20 Keys</button>
              <div className="output">
                <textarea title="Generated Yealink expansion config" value={yealinkOutput} readOnly rows={5} className="full-width-ta" />
              </div>
              {/* Yealink Preview Grid */}
              <div className="expansion-preview">
                <b>Preview: Page {yealinkSection.sidecarPage}</b>
                <div className="expansion-grid expansion-grid-2col">
                  {Array.from({ length: 20 }).map((_, idx) => (
                    <div
                      key={idx}
                      className={`expansion-key${parseInt(yealinkSection.sidecarLine) === idx + 1 ? ' expansion-key-selected' : ''}`}
                      title={`Key ${idx + 1}${parseInt(yealinkSection.sidecarLine) === idx + 1 ? ' (Selected)' : ''}`}
                    >
                      {idx + 1}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {/* Polycom Section */}
            <div className="expansion-col">
              <img src="/expansion/polycomVVX_Color_Exp_Module_2201.jpeg" alt="Polycom VVX Color Expansion Module" className="expansion-img" />
              <div className="expansion-instructions">
                <b>Instructions:</b> Fill out the form below to generate a config for a Polycom expansion key. The preview grid below shows the button layout. Hover over any key for details.
              </div>
              <div className="form-group expansion-form-group">
                <label>Linekey Index (1-28):</label>
                <input type="number" min={1} max={28} value={polycomSection.linekeyIndex} title="Linekey index (1-28)" onChange={e => setPolycomSection(s => ({ ...s, linekeyIndex: e.target.value }))} />
                <label className="label-ml">Address (e.g. 100@PBX):</label>
                <input type="text" value={polycomSection.address} title="Address (e.g. 100@PBX)" onChange={e => setPolycomSection(s => ({ ...s, address: e.target.value }))} />
                <label className="label-ml">Label:</label>
                <input type="text" value={polycomSection.label} title="Label for the key" onChange={e => setPolycomSection(s => ({ ...s, label: e.target.value }))} />
                <label className="label-ml">Type:</label>
                <select value={polycomSection.type} title="Key type" onChange={e => setPolycomSection(s => ({ ...s, type: e.target.value }))}>
                  <option value="automata">Automata</option>
                  <option value="normal">Normal</option>
                </select>
                <label className="label-ml">Linekey Category:</label>
                <input type="text" value={polycomSection.linekeyCategory} title="Linekey category" onChange={e => setPolycomSection(s => ({ ...s, linekeyCategory: e.target.value }))} />
              </div>
              <button onClick={generatePolycomExpansion} className="btn-mt btn-mr">Generate Polycom Expansion Config</button>
              <button onClick={generatePolycomExpansionAll} className="btn-mt">Generate All 28 Keys</button>
              <div className="output">
                <textarea title="Generated Polycom expansion config" value={polycomOutput} readOnly rows={5} className="full-width-ta" />
              </div>
              {/* Polycom Preview Grid */}
              <div className="expansion-preview">
                <b>Preview: 28 keys (4 columns × 7 rows)</b>
                <div className="expansion-grid expansion-grid-4col">
                  {Array.from({ length: 28 }).map((_, idx) => (
                    <div
                      key={idx}
                      className={`expansion-key${parseInt(polycomSection.linekeyIndex) === idx + 1 ? ' expansion-key-selected' : ''}`}
                      title={`Key ${idx + 1}${parseInt(polycomSection.linekeyIndex) === idx + 1 ? ' (Selected)' : ''}`}
                    >
                      {idx + 1}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      {activeTab === 'fullconfig' && (
        <div className="fullconfig-container">
          <h2>Step 3 — Full Config Composer</h2>
          <div className="fullconfig-step-info">
            <p>
              Compose a final config from your Phone Config (Step 1) and Expansion Module (Step 2) outputs.
              Generate each section first, then click <strong>Compose Full Config</strong>.
            </p>
          </div>
          {/* Status: what has been generated so far */}
          <div className="fullconfig-status-row">
            <span className={output.trim() ? 'fullconfig-status-ok' : 'fullconfig-status-empty'}>
              {output.trim() ? '✔ Phone Config ready' : '— Phone Config not generated'}
            </span>
            <span className="fullconfig-status-sep">+</span>
            <span className={(phoneType === 'Yealink' ? yealinkOutput : polycomOutput).trim() ? 'fullconfig-status-ok' : 'fullconfig-status-empty'}>
              {(phoneType === 'Yealink' ? yealinkOutput : polycomOutput).trim()
                ? '✔ Expansion Module ready'
                : '— Expansion Module not generated (optional)'}
            </span>
          </div>
          <button type="button" className="btn-mt" onClick={composeFullConfig}>
            Compose Full Config
          </button>
          {fullConfigOutput ? (
            <div className="output fullconfig-output">
              <textarea
                title="Composed full config"
                value={fullConfigOutput}
                readOnly
                rows={20}
                className="full-width-ta"
              />
            </div>
          ) : (
            <p className="fullconfig-empty-state">
              No output yet — generate a Phone Config and/or Expansion Module config first, then click Compose.
            </p>
          )}
        </div>
      )}
      {activeTab === 'fbpx' && (
        <div>
          <h2>FBPX Import</h2>
          <input type="file" accept=".csv" title="Import CSV file" onChange={handleFpbxImport} />
          <button onClick={handleFpbxExport}>Export CSV</button>
          <a ref={fpbxDownloadRef} className="hidden-link">Download</a>
          <table>
            <thead>
              <tr>
                {FPBX_FIELDS.map(f => <th key={f}>{f}</th>)}
              </tr>
            </thead>
            <tbody>
              {fpbxRows.map((row, idx) => (
                <tr key={idx}>
                  {FPBX_FIELDS.map(f => (
                    <td key={f}>
                      <input
                        title={f}
                        name={f}
                        value={row[f] || ''}
                        onChange={e => handleFpbxChange(idx, e)}
                      />
                    </td>
                  ))}
                  <td>
                    <button onClick={() => handleFpbxDeleteRow(idx)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={() => handleFpbxAddRow(1)}>Add Row</button>
        </div>
      )}
      {activeTab === 'vpbx' && <VpbxImportTab />}
      {activeTab === 'phonegen' && <PhoneConfigGeneratorTab />}
      {activeTab === 'audit' && <ConfigAuditTab />}
      {activeTab === 'mikrotik' && (
        <MikrotikTab
          ottFields={ottFields}
          setOttFields={setOttFields}
          getOttTemplate={getOttTemplate}
          scraperHandles={scraperHandles}
          scraperOnline={scraperOnlinePhone}
        />
      )}
      {activeTab === 'switch' && (
        <div>
          <h2>Switch Templates</h2>
          <SwitchDynamicTemplate />
          <Switch24DynamicTemplate />
          <Switch8DynamicTemplate />
        </div>
      )}
      {activeTab === 'ordertracker' && (
        <div>
          <h2>Order Tracker</h2>
          <HostedOrderTrackerTab />
        </div>
      )}
      {activeTab === 'streeto' && (
        <div>
          <h2>Stretto Import</h2>
          <StrettoImportExportTab />
        </div>
      )}
      {activeTab === 'diagnostics' && (
        <DiagnosticsTab />
      )}
      </main>
    </div>
  );
}

export default App;
