// importStore.ts — localStorage-backed row state + CSV utilities for import tabs

// ─── Row types ────────────────────────────────────────────────────────────────

export type AnyRow = Record<string, string>;

export type CopyUserRow = {
  userName: string; extensionNumber: string; email: string;
  directInwardDial: string; callerIdNumber: string;
  sbsAccount: string; softphoneRequired: string;
};

export type FpbxRow = {
  extension: string; name: string; description: string; tech: string;
  secret: string; callwaiting_enable: string;
  voicemail: string; voicemail_enable: string; voicemail_vmpwd: string;
  voicemail_email: string; voicemail_same_exten: string;
  outboundcid: string; id: string; dial: string; user: string;
  max_contacts: string; accountcode: string;
};

export type VpbxRow = {
  extension: string; name: string; secret: string; user: string;
  mac: string; model: string; tech: string;
  description: string; voicemail_email: string; voicemail_options: string;
  voicemail_same_exten: string; outboundcid: string; emergency_cid: string;
  dial: string; max_contacts: string; accountcode: string;
};

export type StrRow = {
  username: string; password: string; email: string;
  profile: string;
  'account1Sip.credentials.authorizationName': string;
  'account1Sip.credentials.password': string;
  'account1Sip.credentials.displayName': string;
  'account1Sip.credentials.username': string;
  'account1Sip.domain': string;
};

export type DidRow = {
  cidnum: string; extension: string; destination: string;
  privacyman: string; mohclass: string; description: string;
  grppre: string; delay_answer: string; pricid: string;
  pmmaxretries: string; pmminlength: string; reversal: string;
  rvolume: string; indication_zone: string; callrecording: string;
};

export type ImDeviceRow = {
  device_id: string; name: string; mac: string; model: string;
  extension: string; site_code: string; description: string;
};

export type ImNumberRow = {
  number: string; description: string; destination: string;
  type: string; site_code: string; status: string;
};

export type ImUserRow = {
  username: string; first_name: string; last_name: string;
  email: string; extension: string; site_code: string; display_name: string;
};

// ─── Field lists ──────────────────────────────────────────────────────────────

export const COPY_USER_FIELDS: (keyof CopyUserRow)[] = [
  'userName', 'extensionNumber', 'email',
  'directInwardDial', 'callerIdNumber', 'sbsAccount', 'softphoneRequired',
];

export const COPY_USER_HEADERS: Record<keyof CopyUserRow, string> = {
  userName: 'User Name',
  extensionNumber: 'Extension Number',
  email: 'Email',
  directInwardDial: 'Direct Inward Dial',
  callerIdNumber: 'Caller ID Number',
  sbsAccount: 'SBS Account?',
  softphoneRequired: 'Softphone Required?',
};

export const FPBX_FIELDS: (keyof FpbxRow)[] = [
  'extension', 'name', 'description', 'tech', 'secret',
  'callwaiting_enable', 'voicemail', 'voicemail_enable', 'voicemail_vmpwd',
  'voicemail_email', 'voicemail_same_exten',
  'outboundcid', 'id', 'dial', 'user', 'max_contacts', 'accountcode',
];

export const VPBX_FIELDS: (keyof VpbxRow)[] = [
  'extension', 'name', 'secret', 'user', 'mac', 'model', 'tech',
  'description', 'voicemail_email', 'voicemail_options', 'voicemail_same_exten',
  'outboundcid', 'emergency_cid', 'dial', 'max_contacts', 'accountcode',
];

export const STRETTO_FIELDS: (keyof StrRow)[] = [
  'username', 'password', 'email', 'profile',
  'account1Sip.credentials.authorizationName',
  'account1Sip.credentials.password',
  'account1Sip.credentials.displayName',
  'account1Sip.credentials.username',
  'account1Sip.domain',
];

export const DIDS_FIELDS: (keyof DidRow)[] = [
  'cidnum', 'extension', 'destination', 'privacyman', 'mohclass',
  'description', 'grppre', 'delay_answer', 'pricid',
  'pmmaxretries', 'pmminlength', 'reversal', 'rvolume',
  'indication_zone', 'callrecording',
];

export const IM_DEVICE_FIELDS: (keyof ImDeviceRow)[] = [
  'device_id', 'name', 'mac', 'model', 'extension', 'site_code', 'description',
];

export const IM_NUMBER_FIELDS: (keyof ImNumberRow)[] = [
  'number', 'description', 'destination', 'type', 'site_code', 'status',
];

export const IM_USER_FIELDS: (keyof ImUserRow)[] = [
  'username', 'first_name', 'last_name', 'email', 'extension', 'site_code', 'display_name',
];

// ─── Empty row factories ──────────────────────────────────────────────────────

export function emptyCopyUserRow(): CopyUserRow {
  return { userName: '', extensionNumber: '', email: '', directInwardDial: '', callerIdNumber: '', sbsAccount: '', softphoneRequired: '' };
}

export function emptyFpbxRow(): FpbxRow {
  return { extension: '', name: '', description: '', tech: 'pjsip', secret: '', callwaiting_enable: 'ENABLED', voicemail: 'default', voicemail_enable: 'yes', voicemail_vmpwd: '', voicemail_email: '', voicemail_same_exten: 'no', outboundcid: '', id: '', dial: '', user: '', max_contacts: '10', accountcode: '' };
}

export function emptyVpbxRow(): VpbxRow {
  return { extension: '', name: '', secret: '', user: '', mac: '', model: '', tech: 'pjsip', description: '', voicemail_email: '', voicemail_options: '', voicemail_same_exten: '', outboundcid: '', emergency_cid: '', dial: '', max_contacts: '', accountcode: '' };
}

export function emptyStrRow(): StrRow {
  return { username: '', password: '', email: '', profile: 'sip.only', 'account1Sip.credentials.authorizationName': '', 'account1Sip.credentials.password': '', 'account1Sip.credentials.displayName': '', 'account1Sip.credentials.username': '', 'account1Sip.domain': '' };
}

export function emptyDidRow(): DidRow {
  return { cidnum: '', extension: '', destination: '', privacyman: '0', mohclass: 'default', description: '', grppre: '', delay_answer: '0', pricid: '', pmmaxretries: '0', pmminlength: '3', reversal: '0', rvolume: '0', indication_zone: '', callrecording: 'dontcare' };
}

export function emptyImDeviceRow(): ImDeviceRow {
  return { device_id: '', name: '', mac: '', model: '', extension: '', site_code: '', description: '' };
}

export function emptyImNumberRow(): ImNumberRow {
  return { number: '', description: '', destination: '', type: '', site_code: '', status: '' };
}

export function emptyImUserRow(): ImUserRow {
  return { username: '', first_name: '', last_name: '', email: '', extension: '', site_code: '', display_name: '' };
}

// ─── localStorage helpers ─────────────────────────────────────────────────────

export function loadStore(key: string): AnyRow[] | null {
  try {
    const raw = localStorage.getItem(`import_store_${key}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveStore(key: string, rows: AnyRow[]): void {
  try {
    localStorage.setItem(`import_store_${key}`, JSON.stringify(rows));
  } catch { /* quota exceeded or private browsing */ }
}

// ─── CSV export ───────────────────────────────────────────────────────────────

export function exportCsv(filename: string, fields: string[], rows: AnyRow[]): void {
  // Find the last row that has at least one non-empty field value
  let lastData = rows.length - 1;
  while (lastData >= 0 && fields.every(f => (rows[lastData][f] ?? '').trim() === '')) {
    lastData--;
  }
  if (lastData < 0) return; // nothing to export

  const exportRows = rows.slice(0, lastData + 1);
  const header = fields.join(',');
  const body = exportRows.map(r =>
    fields.map(f => {
      const v = (r[f] ?? '').replace(/"/g, '""');
      return v.includes(',') || v.includes('"') || v.includes('\n') ? `"${v}"` : v;
    }).join(',')
  ).join('\n');
  const blob = new Blob([header + '\n' + body], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Cross-tab population helpers ────────────────────────────────────────────

export function populateFpbxFromCopyUsers(copyUsers: CopyUserRow[]): FpbxRow[] {
  return copyUsers.map(u => {
    const row = emptyFpbxRow();
    row.name = u.userName;
    row.description = u.userName;
    row.extension = u.extensionNumber;
    row.voicemail_email = u.email;
    row.outboundcid = u.callerIdNumber;
    row.user = u.extensionNumber;
    row.id = u.extensionNumber;
    row.accountcode = u.extensionNumber;
    return row;
  });
}

export function populateFpbxFields(rows: FpbxRow[]): FpbxRow[] {
  return rows.map(r => ({
    ...r,
    user: r.user || r.extension,
    dial: r.dial || (r.extension ? `PJSIP/${r.extension}` : ''),
    id: r.id || r.extension,
    accountcode: r.accountcode || r.extension,
    max_contacts: r.max_contacts || '10',
    callwaiting_enable: r.callwaiting_enable || 'ENABLED',
    voicemail: r.voicemail || 'default',
    voicemail_enable: r.voicemail_enable || 'yes',
    voicemail_same_exten: r.voicemail_same_exten || 'no',
  }));
}

export function generateFpbxSecrets(rows: FpbxRow[]): FpbxRow[] {
  return rows.map(r => ({
    ...r,
    secret: r.secret || Math.random().toString(36).slice(2, 12).toUpperCase(),
  }));
}

export function cleanFpbxOutboundCid(rows: FpbxRow[]): FpbxRow[] {
  return rows.map(r => ({
    ...r,
    outboundcid: r.outboundcid.replace(/\D/g, ''),
  }));
}

export function populateVpbxFromFpbx(fpbxRows: FpbxRow[], _existing?: VpbxRow[]): VpbxRow[] {
  return fpbxRows.map(r => {
    const row = emptyVpbxRow();
    row.extension = r.extension;
    row.name = r.name;
    row.secret = r.secret;
    row.user = r.user || r.extension;
    row.tech = r.tech || 'pjsip';
    row.voicemail_email = r.voicemail_email;
    row.outboundcid = r.outboundcid.replace(/\D/g, '');
    row.dial = r.dial || (r.extension ? `PJSIP/${r.extension}` : '');
    return row;
  });
}

export function populateStrettoFromFpbx(fpbxRows: FpbxRow[], sipDomain: string): StrRow[] {
  return fpbxRows.map(r => {
    const row = emptyStrRow();
    row.username = r.voicemail_email || r.extension;
    row.email = r.voicemail_email;
    row.profile = 'sip.only';
    row['account1Sip.credentials.authorizationName'] = r.user || r.extension;
    row['account1Sip.credentials.password'] = r.secret;
    row['account1Sip.credentials.displayName'] = r.extension;
    row['account1Sip.credentials.username'] = r.user || r.extension;
    row['account1Sip.domain'] = sipDomain;
    return row;
  });
}

export function cleanVpbxMacs(rows: VpbxRow[]): VpbxRow[] {
  return rows.map(r => ({
    ...r,
    mac: r.mac.replace(/[^a-fA-F0-9]/g, '').toUpperCase(),
  }));
}

export function generateVpbxMacs(rows: VpbxRow[]): VpbxRow[] {
  return rows.map(r => ({
    ...r,
    mac: r.mac || Array.from({ length: 6 }, () => Math.floor(Math.random() * 256).toString(16).padStart(2, '0')).join(':').toUpperCase(),
  }));
}

export function generateVpbxSecrets(rows: VpbxRow[]): VpbxRow[] {
  return rows.map(r => ({
    ...r,
    secret: r.secret || Math.random().toString(36).slice(2, 12).toUpperCase(),
  }));
}

export function cleanDidExtensions(rows: DidRow[]): DidRow[] {
  return rows.map(r => ({
    ...r,
    extension: r.extension.replace(/\D/g, ''),
  }));
}

export function clearDidEditableFields(rows: DidRow[]): DidRow[] {
  return rows.map(r => ({
    ...emptyDidRow(),
    cidnum: r.cidnum,
    extension: r.extension,
  }));
}
