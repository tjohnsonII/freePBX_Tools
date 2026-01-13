// Re-add Mikrotik template modules and OTT template function
import { mikrotik5009Bridge } from './mikrotik5009BridgeTemplate';
import { mikrotik5009Passthrough } from './mikrotik5009PassthroughTemplate';
import { onNetMikrotikConfigTemplate } from './onNetMikrotikConfigTemplate';
import { ottMikrotikTemplate } from './ottMikrotikTemplate';
import { mikrotikStandAloneATATemplate } from './mikrotikStandAloneATATemplate';
import { mikrotikDhcpOptions } from './mikrotikDhcpOptionsTemplate';
import React, { useState, useRef } from 'react';
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
  { key: 'reference', label: 'Reference' },
  { key: 'fullconfig', label: 'Full Config' },
  { key: 'fbpx', label: 'FBPX Import' },
  { key: 'vpbx', label: 'VPBX Import' },
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

// Field definitions for VPBX import/export template (adds MAC/model)
const VPBX_FIELDS = [
  "mac", "model", "extension",
  ...FPBX_FIELDS.filter(f => !["extension"].includes(f)),
];

// Type definitions for FBPX and VPBX forms (for type safety)
type FpbxFormType = Record<typeof FPBX_FIELDS[number], string>;
type VpbxFormType = Record<typeof VPBX_FIELDS[number], string>;

// Helper to create an empty FBPX row
const createEmptyFpbxRow = (): FpbxFormType => FPBX_FIELDS.reduce((acc, f) => ({ ...acc, [f]: '' }), {} as FpbxFormType);
// Helper to create an empty VPBX row
const createEmptyVpbxRow = (): VpbxFormType => VPBX_FIELDS.reduce((acc, f) => ({ ...acc, [f]: '' }), {} as VpbxFormType);

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



function App() {
  // --- Yealink/Polycom advanced options state (move to top, single source of truth) ---
  const [yealinkLabelLength, setYealinkLabelLength] = useState(false);
  const [yealinkDisableMissedCall, setYealinkDisableMissedCall] = useState(false);
  const [yealinkCallStealing, setYealinkCallStealing] = useState(false);

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
    let config = '';
    yealinkKeys.forEach((key, i) => {
      const idx = i + 1;
      config += `expansion_module.1.key.${idx}.label=${key.label}\n`;
      config += `expansion_module.1.key.${idx}.type=16\n`; // or 13 for SpeedDial
      config += `expansion_module.1.key.${idx}.value=${key.value}${key.ip ? '@' + key.ip : ''}\n`;
      config += `expansion_module.1.key.${idx}.line=1\n`;
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

  // Yealink record templates for quick config (voicemail, busy, etc)
  const yealinkRecordTemplates = [
    { label: 'Record Unavailable', value: '*97$Cwc$$Cp1$01$Tdtmf$' },
    { label: 'Record Busy', value: '*97$Cwc$$Cp1$02$Tdtmf$' },
    { label: 'Record Name', value: '*97$Cwc$$Cp1$03$Tdtmf$' },
    { label: 'Record Unreachable/DND', value: '*97$Cwc$$Cp1$04$Tdtmf$' },
  ];

  // Polycom record templates for quick config (voicemail, busy, etc)
  const polycomRecordTemplates = [
    { label: 'Record Unavailable', value: '*97$Tinvite$$Cpause2$01$Tdtmf$' },
    { label: 'Record Busy', value: '*97$Tinvite$$Cpause2$02$Tdtmf$' },
    { label: 'Record Name', value: '*97$Tinvite$$Cpause2$03$Tdtmf$' },
    { label: 'Record DND', value: '*97$Tinvite$$Cpause2$04$Tdtmf$' },
  ];

  // State for record template section (quick record macros)
  // ...existing code...

  // Helper: Generate Yealink transfer-to-VM config (special feature)
  function generateYealinkTransferToVM(lineNum: string, extNum: string, pbxIp: string) {
    return (
      `linekey.${lineNum}.extension=${extNum}\n` +
      `linekey.${lineNum}.label=Transfer-2-VM\n` +
      `linekey.${lineNum}.line=1\n` +
      `linekey.${lineNum}.type=3\n` +
      `linekey.${lineNum}.value=*${extNum}@${pbxIp}\n`
    );
  }

  // Helper: Generate Yealink speed dial config (special feature)
  function generateYealinkSpeedDial(lineNum: string, label: string, value: string) {
    return (
      `linekey.${lineNum}.line=1\n` +
      `linekey.${lineNum}.label=${label}\n` +
      `linekey.${lineNum}.type=13\n` +
      `linekey.${lineNum}.value=${value}\n`
    );
  }

  // Helper: Generate Polycom external number config (special feature)
  function generatePolycomExternal(lineNum: string, efkIndex: string, label: string, externalNum: string) {
    return (
      'feature.enhancedFeatureKeys.enabled=1\n' +
      'feature.EFKLineKey.enabled=1\n' +
      `efk.efklist.${efkIndex}.mname=${label}\n` +
      `efk.efklist.${efkIndex}.status=1\n` +
      `efk.efklist.${efkIndex}.action.string=${externalNum}$Tinvite$\n` +
      `linekey.${lineNum}.category=EFK\n` +
      `linekey.${lineNum}.index=${efkIndex}\n`
    );
  }

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

  // FBPX dynamic fields (columns)
  function handleFpbxDeleteField(field: string) {
    setFpbxRows(rows => rows.map(row => {
      const newRow = { ...row };
      delete newRow[field];
      return newRow;
    }));
  }

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

  // State and handlers for VPBX import/export form (PBX CSV import/export)
  const [vpbxRows, setVpbxRows] = useState<VpbxFormType[]>(Array(10).fill(0).map(createEmptyVpbxRow));
  const vpbxDownloadRef = useRef<HTMLAnchorElement>(null);

  // VPBX dynamic fields (columns)
  function handleVpbxDeleteField(field: string) {
    setVpbxRows(rows => rows.map(row => {
      const newRow = { ...row };
      delete newRow[field];
      return newRow;
    }));
  }

  function handleVpbxChange(rowIdx: number, e: React.ChangeEvent<HTMLInputElement>) {
    setVpbxRows(rows => {
      const updated = [...rows];
      updated[rowIdx] = { ...updated[rowIdx], [e.target.name]: e.target.value };
      return updated;
    });
  }

  function handleVpbxExport() {
    const csvHeader = VPBX_FIELDS.join(',') + '\n';
    const csvRows = vpbxRows.map(row => VPBX_FIELDS.map(f => `"${(row[f] || '').replace(/"/g, '""')}"`).join(',')).join('\n') + '\n';
    const csv = csvHeader + csvRows;
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    if (vpbxDownloadRef.current) {
      vpbxDownloadRef.current.href = url;
      vpbxDownloadRef.current.download = 'vpbx_import.csv';
      vpbxDownloadRef.current.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  function handleVpbxImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    Papa.parse(file, {
      header: true,
      complete: (results: Papa.ParseResult<Record<string, string>>) => {
        const rows = (results.data as VpbxFormType[]).filter(row => row && Object.values(row).some(Boolean));
        setVpbxRows(rows.length ? rows : [createEmptyVpbxRow()]);
      },
    });
  }

  function handleVpbxAddRow(count = 1) {
    setVpbxRows(rows => [...rows, ...Array(count).fill(0).map(createEmptyVpbxRow)]);
  }
  function handleVpbxDeleteRow(idx: number) {
    setVpbxRows(rows => rows.length === 1 ? rows : rows.filter((_, i) => i !== idx));
  }

  // New state for time offset and admin password
  const [timeOffset, setTimeOffset] = useState('-5');
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
    <div className="container">
      {/* App title and tab navigation */}
      <h1>Hosted Config Generator</h1>
      <div className="tabs" style={{ display: 'flex', gap: 0, marginBottom: 16 }}>
        {TABS.map((tab, idx) => (
          <button
            key={tab.key}
            className={activeTab === tab.key ? 'active' : ''}
            onClick={() => setActiveTab(tab.key)}
            style={{
              border: 'none',
              borderBottom: activeTab === tab.key ? '3px solid #0078d4' : '2px solid #ccc',
              background: activeTab === tab.key ? '#f7fbff' : '#f4f4f4',
              color: activeTab === tab.key ? '#0078d4' : '#333',
              fontWeight: activeTab === tab.key ? 600 : 400,
              padding: '10px 24px',
              borderTopLeftRadius: idx === 0 ? 8 : 0,
              borderTopRightRadius: idx === TABS.length - 1 ? 8 : 0,
              marginRight: 2,
              outline: 'none',
              cursor: 'pointer',
              transition: 'background 0.2s, color 0.2s, border-bottom 0.2s',
              boxShadow: activeTab === tab.key ? '0 2px 8px rgba(0,0,0,0.04)' : 'none',
              minWidth: 120,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <hr />
      {/* Tab content rendering */}
      {activeTab === 'reference' && (
        <div
          style={{
            margin: '24px 0',
            maxWidth: 900,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center', // Center the content horizontally
          }}
        >
          <h2 style={{ alignSelf: 'flex-start', textAlign: 'left', width: '100%' }}>Reference</h2>
          {/* Sub-navigation menu */}
          <div
            style={{
              display: 'flex',
              gap: 8,
              marginBottom: 24,
              alignSelf: 'center', // Center the subnav
            }}
          >
            {REFERENCE_SUBTABS.map(sub => (
              <button
                key={sub.key}
                className={referenceSubtab === sub.key ? 'active' : ''}
                onClick={() => setReferenceSubtab(sub.key)}
                style={{
                  border: 'none',
                  borderBottom: referenceSubtab === sub.key ? '3px solid #0078d4' : '2px solid #ccc',
                  background: referenceSubtab === sub.key ? '#f7fbff' : '#f4f4f4',
                  color: referenceSubtab === sub.key ? '#0078d4' : '#333',
                  fontWeight: referenceSubtab === sub.key ? 600 : 400,
                  padding: '8px 20px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  minWidth: 100,
                }}
              >
                {sub.label}
              </button>
            ))}
          </div>
          {/* Subtab content */}
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            {referenceSubtab === 'phones' && (
              <div style={{ width: '100%', textAlign: 'left' }}>
                <h2 style={{ textAlign: 'left' }}>Phone Config Reference (Legend)</h2>
                <div style={{ marginTop: 16, display: 'flex', gap: 40, flexWrap: 'wrap', justifyContent: 'center' }}>
                  {/* Polycom Reference Table */}
                  <div style={{ flex: 1, minWidth: 350, textAlign: 'left' }}>
                    <h3 style={{ textAlign: 'left' }}>Polycom</h3>
                    <table className="reference-table" style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16 }}>
                      <thead>
                        <tr style={{ background: '#f4f4f4' }}>
                          <th style={{ textAlign: 'left', padding: '6px 12px', borderBottom: '2px solid #ccc' }}>Setting</th>
                          <th style={{ textAlign: 'left', padding: '6px 12px', borderBottom: '2px solid #ccc' }}>Description</th>
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
                    <h4 style={{ marginTop: 12, textAlign: 'left' }}>Common Polycom Features</h4>
                    <ul style={{ marginLeft: 20, textAlign: 'left' }}>
                      <li><b>BLF (Busy Lamp Field):</b> Monitors extension/park status, lights up when in use.</li>
                      <li><b>Speed Dial:</b> Quick dial to a number or extension.</li>
                      <li><b>EFK (Enhanced Feature Key):</b> Macro for advanced actions (e.g. transfer, record, external call).</li>
                      <li><b>Expansion Module:</b> Extra programmable keys for sidecar modules.</li>
                    </ul>
                  </div>
                  {/* Yealink Reference Table */}
                  <div style={{ flex: 1, minWidth: 350, textAlign: 'left' }}>
                    <h3 style={{ textAlign: 'left' }}>Yealink</h3>
                    <table className="reference-table" style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16 }}>
                      <thead>
                        <tr style={{ background: '#f4f4f4' }}>
                          <th style={{ textAlign: 'left', padding: '6px 12px', borderBottom: '2px solid #ccc' }}>Setting</th>
                          <th style={{ textAlign: 'left', padding: '6px 12px', borderBottom: '2px solid #ccc' }}>Description</th>
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
                    <h4 style={{ marginTop: 12, textAlign: 'left' }}>Common Yealink Features</h4>
                    <ul style={{ marginLeft: 20, textAlign: 'left' }}>
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
              <div style={{ width: '100%', textAlign: 'left' }}>
                <h3>Mikrotik Reference</h3>
                <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 32 }}>
                  <h4 style={{ marginTop: 0 }}>What does each Mikrotik config template do?</h4>
                  <ul style={{ marginLeft: 20 }}>
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
              <div style={{ width: '100%', textAlign: 'left' }}>
                <h3>Switches Reference</h3>
                <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 32 }}>
                  <h4 style={{ marginTop: 0 }}>What does each Switch config template do?</h4>
                  <ul style={{ marginLeft: 20 }}>
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
              <div style={{ width: '100%', textAlign: 'left' }}>
                <h3>PBX Reference</h3>
                <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 32 }}>
                  <h4 style={{ marginTop: 0 }}>PBX Import/Export and Config Types</h4>
                  <ul style={{ marginLeft: 20 }}>
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
          <h2 style={{marginTop:0}}>Phone Config Generator</h2>
          <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 24, maxWidth: 700, marginLeft: 'auto', marginRight: 'auto', textAlign: 'left' }}>
            <h3 style={{ marginTop: 0 }}>What does each config generator do?</h3>
            <ul style={{ marginLeft: 20 }}>
              <li><b>Base Config Options:</b> Generates the main configuration for Polycom or Yealink phones, including park/BLF keys, static settings, and model-specific options.</li>
              <li><b>Polycom MWI (Message Waiting Indicator):</b> Generates config lines to enable voicemail message waiting light for a specific extension and PBX IP.</li>
              <li><b>Linekey/BLF/Speed/Transfer/Hotkey Generator:</b> Creates config for individual programmable keys (BLF, speed dial, transfer, macros) for Yealink or Polycom phones.</li>
              <li><b>External Number Speed Dial:</b> Generates config for a button that dials an external number directly from the phone.</li>
            </ul>
          </div>
          {/* Base Config Options Form */}
          <div className="form-section" style={{marginBottom:24}}>
            <h3>Base Config Options</h3>
            <div className="form-group">
              <label>Phone Type:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.phoneType}>
                  <FaInfoCircle />
                </span>
              </label>
              <select value={phoneType} onChange={e => setPhoneType(e.target.value as 'Polycom' | 'Yealink')}>
                <option value="Polycom">Polycom</option>
                <option value="Yealink">Yealink</option>
              </select>
              <label style={{marginLeft:16}}>Model:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.model}>
                  <FaInfoCircle />
                </span>
              </label>
              <select value={model} onChange={e => setModel(e.target.value)}>
                {MODEL_OPTIONS.map(opt => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>IP Address:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.ip}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={ip} onChange={e => setIp(e.target.value)} placeholder="e.g. 192.168.1.100" />
              <label style={{marginLeft:16}}>Start Extension:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.startExt}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="number" value={startExt} onChange={e => setStartExt(e.target.value)} />
              <label style={{marginLeft:16}}>End Extension:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.endExt}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="number" value={endExt} onChange={e => setEndExt(e.target.value)} />
              <label style={{marginLeft:16}}>Label Prefix:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.labelPrefix}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={labelPrefix} onChange={e => setLabelPrefix(e.target.value)} />
            </div>
            <div className="form-group">
              <label>Time Offset (e.g. -5):
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.timeOffset}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="number" value={timeOffset} onChange={e => setTimeOffset(e.target.value)} />
              <label style={{marginLeft:16}}>Admin Password:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.adminPassword}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={adminPassword} onChange={e => setAdminPassword(e.target.value)} />
            </div>
            <div className="form-group">
              <label><input type="checkbox" checked={yealinkLabelLength} onChange={e => setYealinkLabelLength(e.target.checked)} /> Enable long DSS key labels
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.yealinkLabelLength}>
                  <FaInfoCircle />
                </span>
              </label>
              <label style={{ marginLeft: 16 }}><input type="checkbox" checked={yealinkDisableMissedCall} onChange={e => setYealinkDisableMissedCall(e.target.checked)} /> Disable missed call notification
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.yealinkDisableMissedCall}>
                  <FaInfoCircle />
                </span>
              </label>
              <label style={{ marginLeft: 16 }}><input type="checkbox" checked={yealinkCallStealing} onChange={e => setYealinkCallStealing(e.target.checked)} /> Enable BLF call stealing
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.yealinkCallStealing}>
                  <FaInfoCircle />
                </span>
              </label>
            </div>
            <button onClick={generateConfig} style={{marginTop:8}}>Generate Config</button>
            <div className="output">
              <textarea value={output} readOnly rows={10} style={{ width: '100%', marginTop: 16 }} />
            </div>
          </div>
          {/* Polycom MWI Section */}
          <hr />
          <div className="form-section" style={{marginBottom:24}}>
            <h3>Polycom MWI (Message Waiting Indicator)</h3>
            <div className="form-group">
              <label>Extension:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.polycomMWIExt}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={polycomMWI.ext} onChange={e => setPolycomMWI(mwi => ({ ...mwi, ext: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>PBX IP:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.polycomMWIPbxIp}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={polycomMWI.pbxIp} onChange={e => setPolycomMWI(mwi => ({ ...mwi, pbxIp: e.target.value }))} />
            </div>
            <button onClick={generatePolycomMWI} style={{ marginTop: 8 }}>Generate Polycom MWI Config</button>
            <div className="output" style={{ marginTop: 16 }}>
              <textarea value={polycomMWI.output} readOnly rows={5} style={{ width: '100%' }} />
            </div>
          </div>
          {/* Yealink Expansion Module Section */}
          <hr />
          <div className="form-section" style={{marginBottom:24}}>
            <h3>Yealink Expansion Module Config</h3>
            <div className="form-group">
              <label>Template Type:</label>
              <select value={yealinkSection.templateType} onChange={e => setYealinkSection(s => ({ ...s, templateType: e.target.value }))}>
                <option value="BLF">BLF</option>
                <option value="SpeedDial">Speed Dial</option>
              </select>
              <label style={{ marginLeft: 16 }}>Sidecar Page:</label>
              <input type="text" value={yealinkSection.sidecarPage} onChange={e => setYealinkSection(s => ({ ...s, sidecarPage: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Sidecar Line:</label>
              <input type="text" value={yealinkSection.sidecarLine} onChange={e => setYealinkSection(s => ({ ...s, sidecarLine: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Label:</label>
              <input type="text" value={yealinkSection.label} onChange={e => setYealinkSection(s => ({ ...s, label: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Value:</label>
              <input type="text" value={yealinkSection.value} onChange={e => setYealinkSection(s => ({ ...s, value: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>PBX IP:</label>
              <input type="text" value={yealinkSection.pbxIp} onChange={e => setYealinkSection(s => ({ ...s, pbxIp: e.target.value }))} />
            </div>
            <button onClick={generateYealinkExpansion} style={{ marginTop: 8, marginRight: 8 }}>Generate Yealink Expansion Config</button>
            <button onClick={generateYealinkExpansionAll} style={{ marginTop: 8 }}>Generate All 20 Keys</button>
            <div className="output" style={{ marginTop: 16 }}>
              <textarea value={yealinkOutput} readOnly rows={5} style={{ width: '100%' }} />
            </div>
          </div>
          {/* Polycom Expansion Module Section */}
          <hr />
          <div className="form-section" style={{marginBottom:24}}>
            <h3>Polycom Expansion Module Config</h3>
            <div className="form-group">
              <label>Address:</label>
              <input type="text" value={polycomSection.address} onChange={e => setPolycomSection(s => ({ ...s, address: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Label:</label>
              <input type="text" value={polycomSection.label} onChange={e => setPolycomSection(s => ({ ...s, label: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Type:</label>
              <select value={polycomSection.type} onChange={e => setPolycomSection(s => ({ ...s, type: e.target.value }))}>
                <option value="automata">Automata</option>
                <option value="normal">Normal</option>
              </select>
              <label style={{ marginLeft: 16 }}>Linekey Category:</label>
              <input type="text" value={polycomSection.linekeyCategory} onChange={e => setPolycomSection(s => ({ ...s, linekeyCategory: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Linekey Index:</label>
              <input type="text" value={polycomSection.linekeyIndex} onChange={e => setPolycomSection(s => ({ ...s, linekeyIndex: e.target.value }))} />
            </div>
            <button onClick={generatePolycomExpansion} style={{ marginTop: 8, marginRight: 8 }}>Generate Polycom Expansion Config</button>
            <button onClick={generatePolycomExpansionAll} style={{ marginTop: 8 }}>Generate All 28 Keys</button>
            <div className="output" style={{ marginTop: 16 }}>
              <textarea value={polycomOutput} readOnly rows={5} style={{ width: '100%' }} />
            </div>
          </div>
          {/* Linekey Generator Section */}
          <hr />
          <div className="form-section" style={{marginBottom:24}}>
            <h3>Linekey/BLF/Speed Dial Generator</h3>
            <div className="form-group">
              <label>Brand:</label>
              <select value={linekeyGen.brand} onChange={e => setLinekeyGen(lk => ({ ...lk, brand: e.target.value }))}>
                <option value="Yealink">Yealink</option>
                <option value="Polycom">Polycom</option>
              </select>
              <label style={{ marginLeft: 16 }}>Line Key Number:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.linekeyNum}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={linekeyGen.lineNum} onChange={e => setLinekeyGen(lk => ({ ...lk, lineNum: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Label:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.linekeyLabel}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={linekeyGen.label} onChange={e => setLinekeyGen(lk => ({ ...lk, label: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Register Line:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.linekeyRegLine}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={linekeyGen.regLine} onChange={e => setLinekeyGen(lk => ({ ...lk, regLine: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Type:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.linekeyType}>
                  <FaInfoCircle />
                </span>
              </label>
              <select value={linekeyGen.type} onChange={e => setLinekeyGen(lk => ({ ...lk, type: parseInt(e.target.value) }))}>
                {YEALINK_LINEKEY_TYPES.map(t => (
                  <option key={t.code} value={t.code}>{t.code} - {t.label}</option>
                ))}
              </select>
              <label style={{ marginLeft: 16 }}>Value:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.linekeyValue}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={linekeyGen.value} onChange={e => setLinekeyGen(lk => ({ ...lk, value: e.target.value }))} />
            </div>
            <button type="button" onClick={generateLinekey} style={{ marginLeft: 16 }}>Generate Linekey Config</button>
            <div className="output" style={{ marginTop: 16 }}>
              <textarea value={linekeyGen.output} readOnly rows={5} style={{ width: '100%' }} />
            </div>
          </div>
          {/* External Number Speed Dial Section */}
          <hr />
          <div className="form-section" style={{marginBottom:24}}>
            <h3>External Number Speed Dial</h3>
            <div className="form-group">
              <label>Brand:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.externalBrand}>
                  <FaInfoCircle />
                </span>
              </label>
              <select value={externalSpeed.brand} onChange={e => setExternalSpeed(s => ({ ...s, brand: e.target.value }))}>
                <option value="Yealink">Yealink</option>
                <option value="Polycom">Polycom</option>
              </select>
              <label style={{ marginLeft: 16 }}>Line Key Number:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.externalLineNum}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={externalSpeed.lineNum} onChange={e => setExternalSpeed(s => ({ ...s, lineNum: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>Label:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.externalLabel}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={externalSpeed.label} onChange={e => setExternalSpeed(s => ({ ...s, label: e.target.value }))} />
              <label style={{ marginLeft: 16 }}>External Number:
                <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title={FIELD_TOOLTIPS.externalNumber}>
                  <FaInfoCircle />
                </span>
              </label>
              <input type="text" value={externalSpeed.number} onChange={e => setExternalSpeed(s => ({ ...s, number: e.target.value }))} />
              {externalSpeed.brand === 'Polycom' && (
                <>
                  <label style={{ marginLeft: 16 }}>EFK Index:</label>
                  <input type="text" value={externalSpeed.efkIndex} onChange={e => setExternalSpeed(s => ({ ...s, efkIndex: e.target.value }))} />
                </>
              )}
              <button type="button" onClick={generateExternalSpeed} style={{ marginLeft: 16 }}>Generate External Speed Dial</button>
            </div>
            <div className="output" style={{ marginTop: 16 }}>
              <textarea value={externalSpeedOutput} readOnly rows={5} style={{ width: '100%' }} />
            </div>
          </div>
        </>
      )}
      {activeTab === 'expansion' && (
        <div style={{ maxWidth: 1100, margin: '0 auto', textAlign: 'center' }}>
          <h2 style={{ marginBottom: 24 }}>Expansion Module Code Generators</h2>
          <div style={{ display: 'flex', gap: 40, justifyContent: 'center', alignItems: 'flex-start', flexWrap: 'wrap' }}>
            {/* Yealink Section */}
            <div style={{ flex: 1, minWidth: 350 }}>
              <img src="/expansion/yealink-expansion.jpg" alt="Yealink Expansion Module" style={{ maxWidth: 220, marginBottom: 8, borderRadius: 8 }} />
              <img src="/expansion/yealink-expansion2.jpg" alt="Yealink Expansion Module Alt" style={{ maxWidth: 220, marginBottom: 8, borderRadius: 8 }} />
              <div style={{ background: '#eef6fb', border: '1px solid #cce1fa', borderRadius: 8, padding: 10, marginBottom: 12, fontSize: 14 }}>
                <b>Instructions:</b> Fill out the form below to generate a config for a Yealink expansion key. Use the page &amp; line to preview the key visually. Hover over any icon for field details.
              </div>
              <div className="form-group" style={{ textAlign: 'left', margin: '0 auto', maxWidth: 320 }}>
                <label>Template Type:
                  <span title="BLF for Busy Lamp Field, Speed Dial for quick dial keys" style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}>
                    <FaInfoCircle />
                  </span>
                </label>
                <select value={yealinkSection.templateType} onChange={e => setYealinkSection(s => ({ ...s, templateType: e.target.value }))}>
                  <option value="BLF">BLF</option>
                  <option value="SpeedDial">Speed Dial</option>
                </select>
                <label style={{ marginLeft: 16 }}>Sidecar Page:
                  <span title="Sidecar page number (1, 2, etc.)" style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}>
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="number" min={1} max={3} value={yealinkSection.sidecarPage} onChange={e => setYealinkSection(s => ({ ...s, sidecarPage: e.target.value }))} style={{ width: 60 }} />
                <label style={{ marginLeft: 16 }}>Sidecar Line:
                  <span title="Button position on the sidecar (1-20)" style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}>
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="number" min={1} max={20} value={yealinkSection.sidecarLine} onChange={e => setYealinkSection(s => ({ ...s, sidecarLine: e.target.value }))} style={{ width: 60 }} />
                <label style={{ marginLeft: 16 }}>Label:
                  <span title="Text label shown on the phone's display for this key." style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}>
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="text" value={yealinkSection.label} onChange={e => setYealinkSection(s => ({ ...s, label: e.target.value }))} />
                <label style={{ marginLeft: 16 }}>Value (Phone/ext):
                  <span title="Extension, number, or SIP URI for this key." style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}>
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="text" value={yealinkSection.value} onChange={e => setYealinkSection(s => ({ ...s, value: e.target.value }))} />
                <label style={{ marginLeft: 16 }}>PBX IP:
                  <span title="PBX IP address for BLF keys (required for BLF type)." style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}>
                    <FaInfoCircle />
                  </span>
                </label>
                <input type="text" value={yealinkSection.pbxIp} onChange={e => setYealinkSection(s => ({ ...s, pbxIp: e.target.value }))} />
              </div>
              <button onClick={generateYealinkExpansion} style={{ marginTop: 8, marginRight: 8 }}>Generate Yealink Expansion Config</button>
              <button onClick={generateYealinkExpansionAll} style={{ marginTop: 8 }}>Generate All 20 Keys</button>
              <div className="output" style={{ marginTop: 12 }}>
                <textarea value={yealinkOutput} readOnly rows={5} style={{ width: '100%' }} />
              </div>
              {/* Yealink Preview Grid */}
              <div style={{ marginTop: 16, background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
                <b>Preview: Page {yealinkSection.sidecarPage}</b>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 40px)', gap: 8, justifyContent: 'center', marginTop: 8 }}>
                  {Array.from({ length: 20 }).map((_, idx) => (
                    <div
                      key={idx}
                      style={{
                        width: 38,
                        height: 38,
                        border: '1.5px solid #bbb',
                        borderRadius: 6,
                        background: (parseInt(yealinkSection.sidecarLine) === idx + 1) ? '#cce1fa' : '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: (parseInt(yealinkSection.sidecarLine) === idx + 1) ? 700 : 400,
                        color: (parseInt(yealinkSection.sidecarLine) === idx + 1) ? '#0078d4' : '#333',
                        boxShadow: (parseInt(yealinkSection.sidecarLine) === idx + 1) ? '0 0 6px #0078d4' : 'none'
                      }}
                      title={`Key ${idx + 1}${parseInt(yealinkSection.sidecarLine) === idx + 1 ? ' (Selected)' : ''}`}
                    >
                      {idx + 1}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {/* Polycom Section */}
            <div style={{ flex: 1, minWidth: 350 }}>
              <img src="/expansion/polycom-expansion.jpg" alt="Polycom VVX Color Expansion Module" style={{ maxWidth: 220, marginBottom: 8, borderRadius: 8 }} />
              <div style={{ background: '#eef6fb', border: '1px solid #cce1fa', borderRadius: 8, padding: 10, marginBottom: 12, fontSize: 14 }}>
                <b>Instructions:</b> Fill out the form below to generate a config for a Polycom expansion key. The preview grid below shows the button layout. Hover over any key for details.
              </div>
              <div className="form-group" style={{ textAlign: 'left', margin: '0 auto', maxWidth: 320 }}>
                <label>Linekey Index (1-28):</label>
                <input type="number" min={1} max={28} value={polycomSection.linekeyIndex} onChange={e => setPolycomSection(s => ({ ...s, linekeyIndex: e.target.value }))} />
                <label style={{ marginLeft: 16 }}>Address (e.g. 100@PBX):</label>
                <input type="text" value={polycomSection.address} onChange={e => setPolycomSection(s => ({ ...s, address: e.target.value }))} />
                <label style={{ marginLeft: 16 }}>Label:</label>
                <input type="text" value={polycomSection.label} onChange={e => setPolycomSection(s => ({ ...s, label: e.target.value }))} />
                <label style={{ marginLeft: 16 }}>Type:</label>
                <select value={polycomSection.type} onChange={e => setPolycomSection(s => ({ ...s, type: e.target.value }))}>
                  <option value="automata">Automata</option>
                  <option value="normal">Normal</option>
                </select>
                <label style={{ marginLeft: 16 }}>Linekey Category:</label>
                <input type="text" value={polycomSection.linekeyCategory} onChange={e => setPolycomSection(s => ({ ...s, linekeyCategory: e.target.value }))} />
              </div>
              <button onClick={generatePolycomExpansion} style={{ marginTop: 8, marginRight: 8 }}>Generate Polycom Expansion Config</button>
              <button onClick={generatePolycomExpansionAll} style={{ marginTop: 8 }}>Generate All 28 Keys</button>
              <div className="output" style={{ marginTop: 12 }}>
                <textarea value={polycomOutput} readOnly rows={5} style={{ width: '100%' }} />
              </div>
              {/* Polycom Preview Grid */}
              <div style={{ marginTop: 16, background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>
                <b>Preview: 28 keys (4 columns × 7 rows)</b>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 40px)', gap: 8, justifyContent: 'center', marginTop: 8 }}>
                  {Array.from({ length: 28 }).map((_, idx) => (
                    <div
                      key={idx}
                      style={{
                        width: 38,
                        height: 38,
                        border: '1.5px solid #bbb',
                        borderRadius: 6,
                        background: (parseInt(polycomSection.linekeyIndex) === idx + 1) ? '#cce1fa' : '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: (parseInt(polycomSection.linekeyIndex) === idx + 1) ? 700 : 400,
                        color: (parseInt(polycomSection.linekeyIndex) === idx + 1) ? '#0078d4' : '#333',
                        boxShadow: (parseInt(polycomSection.linekeyIndex) === idx + 1) ? '0 0 6px #0078d4' : 'none'
                      }}
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
        <div>
          <h2>Full Config</h2>
          <p>This tab should generate a complete phone config for all supported models. (Restore your previous UI here.)</p>
          <button onClick={generateConfig}>Generate Full Config</button>
          <textarea value={output} readOnly rows={10} style={{ width: '100%', marginTop: 16 }} />
        </div>
      )}
      {activeTab === 'fbpx' && (
        <div>
          <h2>FBPX Import</h2>
          <input type="file" accept=".csv" onChange={handleFpbxImport} />
          <button onClick={handleFpbxExport}>Export CSV</button>
          <a ref={fpbxDownloadRef} style={{ display: 'none' }}>Download</a>
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
      {activeTab === 'vpbx' && (
        <div>
          <h2>VPBX Import</h2>
          <input type="file" accept=".csv" onChange={handleVpbxImport} />
          <button onClick={handleVpbxExport}>Export CSV</button>
          <a ref={vpbxDownloadRef} style={{ display: 'none' }}>Download</a>
          <table>
            <thead>
              <tr>
                {VPBX_FIELDS.map(f => <th key={f}>{f}</th>)}
              </tr>
            </thead>
            <tbody>
              {vpbxRows.map((row, idx) => (
                <tr key={idx}>
                  {VPBX_FIELDS.map(f => (
                    <td key={f}>
                      <input
                        name={f}
                        value={row[f] || ''}
                        onChange={e => handleVpbxChange(idx, e)}
                      />
                    </td>
                  ))}
                  <td>
                    <button onClick={() => handleVpbxDeleteRow(idx)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={() => handleVpbxAddRow(1)}>Add Row</button>
        </div>
      )}
      {activeTab === 'mikrotik' && (
        <div>
          <h2>Mikrotik Templates</h2>
          <div>
            <h3>5009 Bridge</h3>
            <textarea value={mikrotik5009Bridge} readOnly rows={10} style={{ width: '100%' }} />
            <h3>5009 Passthrough</h3>
            <textarea value={mikrotik5009Passthrough} readOnly rows={10} style={{ width: '100%' }} />
            <h3>OnNet Config</h3>
            <textarea value={onNetMikrotikConfigTemplate} readOnly rows={10} style={{ width: '100%' }} />
            <h3>OTT Template (Editable)</h3>
            <textarea value={getOttTemplate(ottFields)} readOnly rows={10} style={{ width: '100%' }} />
            <h3>Standalone ATA</h3>
            <textarea value={mikrotikStandAloneATATemplate} readOnly rows={10} style={{ width: '100%' }} />
            <h3>DHCP Options</h3>
            <textarea value={mikrotikDhcpOptions} readOnly rows={10} style={{ width: '100%' }} />
          </div>
        </div>
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
    </div>
  );
}

export default App;