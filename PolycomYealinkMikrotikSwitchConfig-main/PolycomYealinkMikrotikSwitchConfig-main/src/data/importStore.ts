// importStore.ts — localStorage-backed row state + CSV utilities for import tabs

// ─── Row types ────────────────────────────────────────────────────────────────

export type AnyRow = Record<string, string>;

export type CopyUserRow = {
  userName: string; extensionNumber: string; email: string;
  directInwardDial: string; callerIdNumber: string;
  sbsAccount: string; softphoneRequired: string;
};

export type FpbxRow = {
  extension: string; name: string; secret: string;
  description: string; voicemail_email: string; voicemail_options: string;
  outboundcid: string; dial: string; tech: string; user: string;
  emergency_cid: string; ringtimer: string; callwaiting: string;
  directdid: string; noanswer_dest: string;
};

export type VpbxRow = {
  extension: string; name: string; secret: string; user: string;
  mac: string; model: string; tech: string;
  description: string; voicemail_email: string; voicemail_options: string;
  outboundcid: string; emergency_cid: string;
};

export type StrRow = {
  username: string; password: string; email: string;
  'account1Sip.credentials.displayName': string;
  'account1Sip.credentials.username': string;
  'account1Sip.domain': string;
  'account1Sip.credentials.password': string;
  'account1Sip.transport': string;
};

export type DidRow = {
  cidnum: string; extension: string; destination: string;
  privacyman: string; mohclass: string; description: string;
  grppre: string; delay_answer: string; pricid: string;
  pmmaxretries: string; pmmaxlength: string; reversal: string;
  rvolume: string; indication_zone: string; callrecording: string;
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
  'extension', 'name', 'secret', 'user', 'description',
  'voicemail_email', 'voicemail_options', 'outboundcid', 'dial',
  'tech', 'emergency_cid', 'ringtimer', 'callwaiting',
  'directdid', 'noanswer_dest',
];

export const VPBX_FIELDS: (keyof VpbxRow)[] = [
  'extension', 'name', 'secret', 'user', 'mac', 'model', 'tech',
  'description', 'voicemail_email', 'voicemail_options',
  'outboundcid', 'emergency_cid',
];

export const STRETTO_FIELDS: (keyof StrRow)[] = [
  'username', 'password', 'email',
  'account1Sip.credentials.displayName',
  'account1Sip.credentials.username',
  'account1Sip.domain',
  'account1Sip.credentials.password',
  'account1Sip.transport',
];

export const DIDS_FIELDS: (keyof DidRow)[] = [
  'cidnum', 'extension', 'destination', 'privacyman', 'mohclass',
  'description', 'grppre', 'delay_answer', 'pricid',
  'pmmaxretries', 'pmmaxlength', 'reversal', 'rvolume',
  'indication_zone', 'callrecording',
];

// ─── Empty row factories ──────────────────────────────────────────────────────

export function emptyCopyUserRow(): CopyUserRow {
  return { userName: '', extensionNumber: '', email: '', directInwardDial: '', callerIdNumber: '', sbsAccount: '', softphoneRequired: '' };
}

export function emptyFpbxRow(): FpbxRow {
  return { extension: '', name: '', secret: '', user: '', description: '', voicemail_email: '', voicemail_options: '', outboundcid: '', dial: '', tech: 'pjsip', emergency_cid: '', ringtimer: '', callwaiting: '', directdid: '', noanswer_dest: '' };
}

export function emptyVpbxRow(): VpbxRow {
  return { extension: '', name: '', secret: '', user: '', mac: '', model: '', tech: 'pjsip', description: '', voicemail_email: '', voicemail_options: '', outboundcid: '', emergency_cid: '' };
}

export function emptyStrRow(): StrRow {
  return { username: '', password: '', email: '', 'account1Sip.credentials.displayName': '', 'account1Sip.credentials.username': '', 'account1Sip.domain': '', 'account1Sip.credentials.password': '', 'account1Sip.transport': 'TLS' };
}

export function emptyDidRow(): DidRow {
  return { cidnum: '', extension: '', destination: '', privacyman: '0', mohclass: 'default', description: '', grppre: '', delay_answer: '0', pricid: '', pmmaxretries: '0', pmmaxlength: '0', reversal: '0', rvolume: '0', indication_zone: '', callrecording: 'dontcare' };
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
  const header = fields.join(',');
  const body = rows.map(r =>
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
    row.extension = u.extensionNumber;
    row.voicemail_email = u.email;
    row.outboundcid = u.callerIdNumber;
    row.directdid = u.directInwardDial;
    row.user = u.extensionNumber;
    return row;
  });
}

export function populateFpbxFields(rows: FpbxRow[]): FpbxRow[] {
  return rows.map(r => ({
    ...r,
    user: r.user || r.extension,
    dial: r.dial || `PJSIP/${r.extension}`,
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
    row.outboundcid = r.outboundcid;
    return row;
  });
}

export function populateStrettoFromFpbx(fpbxRows: FpbxRow[], sipDomain: string): StrRow[] {
  return fpbxRows.map(r => {
    const row = emptyStrRow();
    row.username = r.extension;
    row['account1Sip.credentials.username'] = r.user || r.extension;
    row['account1Sip.credentials.displayName'] = r.name;
    row['account1Sip.credentials.password'] = r.secret;
    row['account1Sip.domain'] = sipDomain;
    row.email = r.voicemail_email;
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
