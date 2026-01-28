import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import xlsx from "xlsx";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(__dirname, "..", "..", "backend");
const outputPath = path.resolve(
  __dirname,
  "..",
  "src",
  "app",
  "data",
  "ipOwnership.json",
);

const fallbackEntries = [
  {
    cidr: "10.255.0.0/16",
    owner: "mpls_core",
    label: "MPLS Core",
    source: "fallback",
  },
  {
    cidr: "10.120.0.0/16",
    owner: "123net_pop",
    label: "123NET POP",
    source: "fallback",
  },
  {
    cidr: "192.168.0.0/16",
    owner: "customer_lan",
    label: "Customer LAN",
    source: "fallback",
  },
  {
    cidr: "10.0.0.0/8",
    owner: "customer_lan",
    label: "Customer LAN",
    source: "fallback",
  },
];

const ownerTypes = ["customer_lan", "123net_pop", "mpls_core", "transit", "unknown"];

const cidrRegex = /\b(\d{1,3}(?:\.\d{1,3}){3})\/(\d{1,2})\b/;
const ipRegex = /\b(\d{1,3}(?:\.\d{1,3}){3})\b/;

function safeReadDir(dir) {
  try {
    return fs.readdirSync(dir);
  } catch (err) {
    console.warn(`[ownership] Unable to read backend dir: ${dir}`, err);
    return [];
  }
}

function isValidIp(ip) {
  const parts = ip.split(".").map(Number);
  if (parts.length !== 4 || parts.some(Number.isNaN)) return false;
  return parts.every(part => part >= 0 && part <= 255);
}

function normalizeCidr(value) {
  if (!value) return null;
  const trimmed = String(value).trim();
  const cidrMatch = trimmed.match(cidrRegex);
  if (cidrMatch) {
    const ip = cidrMatch[1];
    const prefix = Number(cidrMatch[2]);
    if (!isValidIp(ip) || prefix < 0 || prefix > 32) return null;
    return `${ip}/${prefix}`;
  }
  const ipMatch = trimmed.match(ipRegex);
  if (ipMatch) {
    const ip = ipMatch[1];
    if (!isValidIp(ip)) return null;
    return `${ip}/32`;
  }
  return null;
}

function inferOwner({ cidr, label, popExplicit }) {
  if (popExplicit) return "123net_pop";
  if (cidr.startsWith("10.255.")) return "mpls_core";
  if (cidr.startsWith("10.120.") || cidr.startsWith("10.124.") || cidr.startsWith("10.250.")) {
    return "123net_pop";
  }
  if (cidr.startsWith("192.168.")) return "customer_lan";
  if (cidr.startsWith("10.")) return "customer_lan";
  if (label && /transit|carrier|upstream/i.test(label)) return "transit";
  return "unknown";
}

function parseCsvLine(line) {
  const cells = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === "," && !inQuotes) {
      cells.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

function detectHeaderIndexes(headerCells) {
  const normalized = headerCells.map(cell => String(cell ?? "").toLowerCase());
  const matchIndex = patterns =>
    normalized.findIndex(cell => patterns.some(pattern => cell.includes(pattern)));
  return {
    labelIndex: matchIndex(["site", "pop", "colo", "location", "name"]),
    cityIndex: matchIndex(["city", "town", "metro"]),
    noteIndex: matchIndex(["note", "comment", "desc"]),
    popIndex: matchIndex(["pop", "colo"]),
  };
}

function extractRowLabel(row, headerIndexes) {
  const candidates = [];
  if (headerIndexes.labelIndex >= 0) candidates.push(row[headerIndexes.labelIndex]);
  if (headerIndexes.popIndex >= 0) candidates.push(row[headerIndexes.popIndex]);
  const fallback = row.find(cell =>
    typeof cell === "string" &&
    cell.trim() &&
    !ipRegex.test(cell) &&
    !cidrRegex.test(cell),
  );
  const label = candidates.find(value => typeof value === "string" && value.trim()) ?? fallback;
  return label ? String(label).trim() : "";
}

function extractCity(row, headerIndexes) {
  if (headerIndexes.cityIndex < 0) return "";
  const value = row[headerIndexes.cityIndex];
  return value ? String(value).trim() : "";
}

function extractNote(row, headerIndexes) {
  if (headerIndexes.noteIndex < 0) return "";
  const value = row[headerIndexes.noteIndex];
  return value ? String(value).trim() : "";
}

function popExplicitFromRow(row, headerIndexes) {
  if (headerIndexes.popIndex >= 0) {
    const value = row[headerIndexes.popIndex];
    if (value && String(value).trim()) return true;
  }
  const labelCandidate = extractRowLabel(row, headerIndexes);
  return /\bpop\b|colo/i.test(labelCandidate);
}

function parseCsvFile(filePath) {
  const entries = [];
  let parsedCount = 0;
  try {
    const raw = fs.readFileSync(filePath, "utf8");
    const lines = raw.split(/\r?\n/).filter(line => line.trim());
    if (lines.length === 0) return { entries, parsedCount };
    const headerCells = parseCsvLine(lines[0]);
    const headerIndexes = detectHeaderIndexes(headerCells);
    const hasHeader = headerCells.some(cell => /[a-zA-Z]/.test(cell));
    const dataLines = hasHeader ? lines.slice(1) : lines;

    for (const line of dataLines) {
      const row = parseCsvLine(line);
      const label = extractRowLabel(row, headerIndexes) || "CSV entry";
      const city = extractCity(row, headerIndexes);
      const note = extractNote(row, headerIndexes);
      const popExplicit = popExplicitFromRow(row, headerIndexes);

      row.forEach(cell => {
        const cidr = normalizeCidr(cell);
        if (!cidr) return;
        const owner = inferOwner({ cidr, label, popExplicit });
        entries.push({
          cidr,
          owner,
          label,
          city: city || undefined,
          source: path.basename(filePath),
          note: note || undefined,
        });
        parsedCount += 1;
      });
    }
  } catch (err) {
    console.warn(`[ownership] Failed to parse CSV ${filePath}`, err);
  }
  return { entries, parsedCount };
}

function parseTxtFile(filePath) {
  const entries = [];
  let parsedCount = 0;
  try {
    const raw = fs.readFileSync(filePath, "utf8");
    const lines = raw.split(/\r?\n/).filter(line => line.trim());
    for (const line of lines) {
      const cidrMatch = line.match(cidrRegex);
      const ipMatch = line.match(ipRegex);
      const cidr = normalizeCidr(cidrMatch ? cidrMatch[0] : ipMatch?.[0]);
      if (!cidr) continue;
      const label = line.replace(cidrRegex, "").replace(ipRegex, "").trim() || "TXT entry";
      const owner = inferOwner({ cidr, label, popExplicit: /\bpop\b|colo/i.test(label) });
      entries.push({
        cidr,
        owner,
        label,
        source: path.basename(filePath),
      });
      parsedCount += 1;
    }
  } catch (err) {
    console.warn(`[ownership] Failed to parse TXT ${filePath}`, err);
  }
  return { entries, parsedCount };
}

function parseXlsxFile(filePath) {
  const entries = [];
  const workbook = xlsx.readFile(filePath, { cellDates: false });
  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    const rows = xlsx.utils.sheet_to_json(sheet, { header: 1, defval: "" });
    if (!rows.length) continue;
    const headerCells = rows[0] ?? [];
    const headerIndexes = detectHeaderIndexes(headerCells);
    const hasHeader = headerCells.some(cell => /[a-zA-Z]/.test(String(cell ?? "")));
    const dataRows = hasHeader ? rows.slice(1) : rows;

    let parsedCount = 0;
    for (const row of dataRows) {
      if (!Array.isArray(row)) continue;
      const rowValues = row.map(cell => String(cell ?? "").trim());
      const label = extractRowLabel(rowValues, headerIndexes) || sheetName || "XLSX entry";
      const city = extractCity(rowValues, headerIndexes);
      const note = extractNote(rowValues, headerIndexes);
      const popExplicit = popExplicitFromRow(rowValues, headerIndexes);

      rowValues.forEach(cell => {
        const cidr = normalizeCidr(cell);
        if (!cidr) return;
        const owner = inferOwner({ cidr, label, popExplicit });
        entries.push({
          cidr,
          owner,
          label,
          city: city || undefined,
          source: path.basename(filePath),
          note: note || undefined,
        });
        parsedCount += 1;
      });
    }
    console.log(`[ownership] ${path.basename(filePath)}:${sheetName} -> ${parsedCount} entries`);
  }
  return entries;
}

function sortBySpecificity(entries) {
  return entries.sort((a, b) => {
    const prefixA = Number(a.cidr.split("/")[1] ?? 0);
    const prefixB = Number(b.cidr.split("/")[1] ?? 0);
    if (prefixA !== prefixB) return prefixB - prefixA;
    return a.cidr.localeCompare(b.cidr);
  });
}

function dedupeEntries(entries) {
  const map = new Map();
  for (const entry of entries) {
    const existing = map.get(entry.cidr);
    if (!existing || entry.priority > existing.priority) {
      map.set(entry.cidr, entry);
    }
  }
  return Array.from(map.values());
}

function ensureOwner(value) {
  if (ownerTypes.includes(value)) return value;
  return "unknown";
}

function buildEntries() {
  const allEntries = [];
  fallbackEntries.forEach(entry => {
    allEntries.push({ ...entry, priority: 0 });
  });

  const files = safeReadDir(backendDir);
  const csvFiles = files.filter(file => file.toLowerCase().endsWith(".csv"));
  const txtFiles = files.filter(file => file.toLowerCase() === "all_assignments.txt");
  const xlsxFiles = files.filter(file => file.toLowerCase().endsWith(".xlsx"));

  if (csvFiles.length === 0) {
    console.log(`[ownership] No CSV files found in ${backendDir}`);
  }
  if (txtFiles.length === 0) {
    console.log(`[ownership] All_Assignments.txt not found in ${backendDir}`);
  }
  if (xlsxFiles.length === 0) {
    console.log(`[ownership] No XLSX files found in ${backendDir}`);
  }

  for (const file of csvFiles) {
    const filePath = path.join(backendDir, file);
    const { entries, parsedCount } = parseCsvFile(filePath);
    entries.forEach(entry => allEntries.push({ ...entry, priority: 2 }));
    console.log(`[ownership] ${file} -> ${parsedCount} entries`);
  }

  for (const file of txtFiles) {
    const filePath = path.join(backendDir, file);
    const { entries, parsedCount } = parseTxtFile(filePath);
    entries.forEach(entry => allEntries.push({ ...entry, priority: 1 }));
    console.log(`[ownership] ${file} -> ${parsedCount} entries`);
  }

  for (const file of xlsxFiles) {
    const filePath = path.join(backendDir, file);
    let parsedEntries = [];
    try {
      parsedEntries = parseXlsxFile(filePath);
    } catch (err) {
      console.warn(`[ownership] Failed to parse XLSX ${file}`, err);
    }
    parsedEntries.forEach(entry => allEntries.push({ ...entry, priority: 3 }));
  }

  const deduped = dedupeEntries(allEntries).map(entry => ({
    cidr: entry.cidr,
    owner: ensureOwner(entry.owner),
    label: entry.label,
    city: entry.city || undefined,
    source: entry.source,
    note: entry.note || undefined,
  }));

  const sorted = sortBySpecificity(deduped);
  const ownerCounts = sorted.reduce((acc, entry) => {
    acc[entry.owner] = (acc[entry.owner] ?? 0) + 1;
    return acc;
  }, {});
  console.log("[ownership] Owner counts:");
  ownerTypes.forEach(type => {
    console.log(`  ${type}: ${ownerCounts[type] ?? 0}`);
  });

  return sorted;
}

function main() {
  const entries = buildEntries();
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(entries, null, 2)}\n`, "utf8");
  console.log(`[ownership] Wrote ${entries.length} entries -> ${outputPath}`);
}

main();
