// Shared logic for the "Bulk Sidecar Directory Update" panel.
// A sidecar "directory" is the set of expansion_module.<page>.key.<key>.{label,value,type}
// entries that make up the company speed-dial/BLF list duplicated across every phone.

export interface DirectoryEntry {
  label: string;
  value: string;
  type: string;
}

const EXP_KEY_RE = /^expansion_module\.(\d+)\.key\.(\d+)\.(label|type|value)=(.*)$/;

export const KEYS_PER_PAGE = 20;
export const MAX_PAGES = 3;
export const MAX_DIRECTORY_ENTRIES = KEYS_PER_PAGE * MAX_PAGES;

/** Extract every expansion_module key that has a label, in no particular order. */
export function parseDirectoryEntries(configText: string): DirectoryEntry[] {
  const byPosition = new Map<string, Partial<DirectoryEntry>>();
  for (const raw of configText.split('\n')) {
    const m = EXP_KEY_RE.exec(raw.trim());
    if (!m) continue;
    const posKey = `${m[1]}.${m[2]}`;
    const entry = byPosition.get(posKey) || {};
    entry[m[3] as 'label' | 'value' | 'type'] = m[4].trim();
    byPosition.set(posKey, entry);
  }
  const entries: DirectoryEntry[] = [];
  for (const e of byPosition.values()) {
    if (e.label) entries.push({ label: e.label, value: e.value || '', type: e.type || '' });
  }
  return entries;
}

/** Remove every expansion_module.*.key.* line from a raw device config/attribute blob. */
export function stripDirectoryLines(configText: string): string {
  return configText
    .split('\n')
    .filter(l => !EXP_KEY_RE.test(l.trim()))
    .join('\n');
}

/** The most common key "type" among existing entries — used as the default for new additions. */
export function majorityType(entries: DirectoryEntry[], fallback = '13'): string {
  const counts = new Map<string, number>();
  for (const e of entries) counts.set(e.type, (counts.get(e.type) || 0) + 1);
  let best = fallback;
  let bestCount = 0;
  for (const [type, count] of counts) {
    if (count > bestCount) { best = type; bestCount = count; }
  }
  return best;
}

/**
 * Merge additions/removals into an existing directory, de-duplicated by label
 * (an addition with the same label as an existing entry updates its value),
 * sorted alphabetically by label.
 */
export function buildDirectory(
  current: DirectoryEntry[],
  additions: { label: string; value: string }[],
  removeLabels: Set<string>,
  defaultType: string
): DirectoryEntry[] {
  const byLabel = new Map<string, DirectoryEntry>();
  for (const e of current) {
    if (!removeLabels.has(e.label)) byLabel.set(e.label, e);
  }
  for (const a of additions) {
    const label = a.label.trim();
    const value = a.value.trim();
    if (!label) continue;
    byLabel.set(label, { label, value, type: defaultType });
  }
  return Array.from(byLabel.values()).sort((a, b) => a.label.localeCompare(b.label));
}

/** Render a directory as expansion_module.<page>.key.<key>.* lines, packed sequentially. */
export function renderDirectoryLines(entries: DirectoryEntry[]): string {
  const lines: string[] = [];
  entries.slice(0, MAX_DIRECTORY_ENTRIES).forEach((e, idx) => {
    const page = Math.floor(idx / KEYS_PER_PAGE) + 1;
    const key = (idx % KEYS_PER_PAGE) + 1;
    const prefix = `expansion_module.${page}.key.${key}`;
    lines.push(`${prefix}.type=${e.type}`);
    lines.push(`${prefix}.value=${e.value}`);
    lines.push(`${prefix}.label=${e.label}`);
  });
  return lines.join('\n');
}

/**
 * Build the full attribute blob for pasting into the vendor's "Bulk Attribute Edit"
 * box: every non-directory line from the device untouched, plus the freshly
 * renumbered directory. Safe against both whole-blob replace and per-key upsert
 * semantics since stale expansion_module keys never survive the strip.
 */
export function buildFullDeviceAttributeText(rawConfigText: string, entries: DirectoryEntry[]): string {
  const other = stripDirectoryLines(rawConfigText)
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean);
  const directory = renderDirectoryLines(entries);
  return [...other, directory].filter(Boolean).join('\n');
}
