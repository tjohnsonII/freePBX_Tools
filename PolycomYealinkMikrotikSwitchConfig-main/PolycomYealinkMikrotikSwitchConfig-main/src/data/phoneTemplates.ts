// phoneTemplates.ts — standard config snippets and generator functions

// ─── Yealink base templates ───────────────────────────────────────────────────

export const YEALINK_STANDARD_BASE = `\
#!version:1.0.0.1
## Standard Yealink Template

## SIP Transport
account.1.sip_server.1.transport_type = 2

## Audio
voice.tone.country = United States
features.call_waiting.enable = 1
features.intercom.allow = 1
features.dnd_mode = 0

## Codecs
account.1.codec.1.enable = 1
account.1.codec.1.payload_type = PCMU
account.1.codec.2.enable = 1
account.1.codec.2.payload_type = PCMA
account.1.codec.3.enable = 1
account.1.codec.3.payload_type = G729

## Time / Date
local_time.time_zone = -5
local_time.time_zone_name = United States(New York)
local_time.ntp_server1 = pool.ntp.org
local_time.summer_time = 2
local_time.date_format = 1
local_time.time_format = 1`;

export const YEALINK_DECT_BASE = `\
#!version:1.0.0.1
## Yealink DECT Base Template

## Base station
base.interdigit_time = 3
base.subsys.call_handover = 1
features.call_waiting.enable = 1

## Time
local_time.time_zone = -5
local_time.time_zone_name = United States(New York)
local_time.ntp_server1 = pool.ntp.org
local_time.summer_time = 2`;

export const YEALINK_HOLD_VOLUME = `\
## Prevent volume from resetting to default on hold
features.play_hold_tone.enable = 0`;

// ─── Polycom config snippets (flat key=value format) ─────────────────────────

export const POLYCOM_DATE_TIME_OVERRIDE = `\
tcpIpApp.sntp.address="pool.ntp.org"
tcpIpApp.sntp.gmtOffset="-18000"
tcpIpApp.sntp.daylightSavings.enable="1"`;

export const POLYCOM_HOLD_RINGBACK = `\
call.hold.localReminder.enabled="1"
call.hold.localReminder.period="60"
call.hold.localReminder.count="3"`;

export const POLYCOM_URL_DIALING_DISABLE = `\
up.urlDial="0"`;

export const POLYCOM_REMOVE_DND = `\
feature.doNotDisturb.enable="0"`;

// ─── Yealink generators ───────────────────────────────────────────────────────

export function generateYealinkParkLines(count: number, pbxIp: string, startIndex: number): string {
  const lines: string[] = [];
  for (let i = 0; i < count; i++) {
    const idx = startIndex + i;
    const park = `*8${String(i + 1).padStart(2, '0')}`;
    lines.push(
      `linekey.${idx}.type = 16`,
      `linekey.${idx}.value = ${park}@${pbxIp}`,
      `linekey.${idx}.label = Park ${i + 1}`,
      `linekey.${idx}.line = 1`,
      `linekey.${idx}.extension = ${park}`,
    );
  }
  return lines.join('\n');
}

export function generateYealinkBLF(keyNum: number, ext: string, label: string, pbxIp: string): string {
  return [
    `linekey.${keyNum}.type = 16`,
    `linekey.${keyNum}.value = ${ext}@${pbxIp}`,
    `linekey.${keyNum}.label = ${label}`,
    `linekey.${keyNum}.line = 1`,
    `linekey.${keyNum}.extension = ${ext}`,
  ].join('\n');
}

export function generateYealinkTransferKey(keyNum: number, ext: string, label: string, pbxIp: string): string {
  return [
    `linekey.${keyNum}.type = 20`,
    `linekey.${keyNum}.value = ${ext}@${pbxIp}`,
    `linekey.${keyNum}.label = ${label}`,
    `linekey.${keyNum}.line = 1`,
  ].join('\n');
}

export function generateYealinkExternalSpeedDial(keyNum: number, number: string, label: string): string {
  return [
    `linekey.${keyNum}.type = 13`,
    `linekey.${keyNum}.value = ${number}`,
    `linekey.${keyNum}.label = ${label}`,
    `linekey.${keyNum}.line = 1`,
  ].join('\n');
}

// ─── Polycom generators ───────────────────────────────────────────────────────

export function generatePolycomParkLines(count: number, pbxIp: string, startIndex: number): string {
  const lines: string[] = [];
  for (let i = 0; i < count; i++) {
    const idx = startIndex + i;
    const park = `*8${String(i + 1).padStart(2, '0')}`;
    lines.push(
      `attendant.${idx}.callAddress="${park}@${pbxIp}"`,
      `attendant.${idx}.label="Park ${i + 1}"`,
      `attendant.${idx}.type="normal"`,
      `attendant.${idx}.action.1.type="SIPTransfer"`,
    );
  }
  return lines.join('\n');
}

export function generatePolycomBLF(keyNum: number, ext: string, label: string, pbxIp: string): string {
  return [
    `attendant.${keyNum}.callAddress="${ext}@${pbxIp}"`,
    `attendant.${keyNum}.label="${label}"`,
    `attendant.${keyNum}.type="normal"`,
  ].join('\n');
}

export function generatePolycomSpeedDial(keyNum: number, number: string, label: string, pbxIp: string): string {
  return [
    `attendant.${keyNum}.callAddress="${number}@${pbxIp}"`,
    `attendant.${keyNum}.label="${label}"`,
    `attendant.${keyNum}.type="normal"`,
    `attendant.${keyNum}.action.1.type="dial"`,
  ].join('\n');
}

export interface EfkOptions {
  efkIndex: number;
  linekeyNum: number;
  mname: string;
  actionString: string;
  promptLabel: string;
  promptType: string;
}

export function generatePolycomEFK(opts: EfkOptions): string {
  const { efkIndex, linekeyNum, mname, actionString, promptLabel, promptType } = opts;
  return [
    `efk.efklist.${efkIndex}.action.string="${actionString}"`,
    `efk.efklist.${efkIndex}.action.use.uui="0"`,
    `efk.efklist.${efkIndex}.functionkey.use.tag="0"`,
    `efk.efklist.${efkIndex}.label="${mname}"`,
    `efk.efklist.${efkIndex}.mname="${mname}"`,
    `efk.efklist.${efkIndex}.status="1"`,
    `efk.efklist.${efkIndex}.prompt.${efkIndex}.label="${promptLabel}"`,
    `efk.efklist.${efkIndex}.prompt.${efkIndex}.type="${promptType}"`,
    `efk.functionkey.${linekeyNum}.action.string="${actionString}"`,
  ].join('\n');
}
