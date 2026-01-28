import ownershipEntries from "../data/ipOwnership.json";

export type Hop = {
  hop: number;
  ip: string;
  hostname: string;
  latency: string;
  geo: {
    city: string;
    country: string;
    lat?: number;
    lon?: number;
  };
};

export type HopClassification = {
  flags: {
    responded: boolean;
    no_response: boolean;
    private_ip: boolean;
    public_ip: boolean;
    destination: boolean;
  };
  ownership?: {
    owner: "customer_lan" | "123net_pop" | "mpls_core" | "transit" | "unknown";
    label: string;
    city?: string;
  };
  explanation: string;
};

type OwnershipEntry = {
  cidr: string;
  owner: "customer_lan" | "123net_pop" | "mpls_core" | "transit";
  label: string;
  city?: string;
};

const NO_RESPONSE_IP_VALUES = new Set(["no response", "---", "*"]);
const NO_RESPONSE_LATENCY_VALUES = new Set(["---", "—", "*", "no response"]);

function isValidIpv4(ip: string): boolean {
  const parts = ip.split(".");
  if (parts.length !== 4) return false;
  return parts.every(part => {
    if (!/^(\d+)$/.test(part)) return false;
    const num = Number(part);
    return num >= 0 && num <= 255;
  });
}

function isPrivateIpv4(ip: string): boolean {
  const parts = ip.split(".").map(Number);
  if (parts.length !== 4 || parts.some(Number.isNaN)) return false;
  const [first, second] = parts;
  if (first === 10) return true;
  if (first === 172 && second >= 16 && second <= 31) return true;
  if (first === 192 && second === 168) return true;
  return false;
}

function isNoResponseValue(value: string, set: Set<string>): boolean {
  const normalized = value.trim().toLowerCase();
  if (set.has(normalized)) return true;
  return normalized.includes("*");
}

export function ipv4ToInt(ip: string): number | null {
  if (!isValidIpv4(ip)) return null;
  const parts = ip.split(".").map(Number);
  if (parts.length !== 4 || parts.some(Number.isNaN)) return null;
  return (
    (((parts[0] << 24) >>> 0) +
      ((parts[1] << 16) >>> 0) +
      ((parts[2] << 8) >>> 0) +
      (parts[3] >>> 0)) >>>
    0
  );
}

export function cidrToRange(cidr: string): { start: number; end: number } | null {
  const [baseIp, prefixRaw] = cidr.split("/");
  if (!baseIp || prefixRaw == null) return null;
  const prefix = Number(prefixRaw);
  if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) return null;
  const baseInt = ipv4ToInt(baseIp.trim());
  if (baseInt == null) return null;
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0;
  const start = baseInt & mask;
  const end = start | (~mask >>> 0);
  return { start: start >>> 0, end: end >>> 0 };
}

export function cidrContains(cidr: string, ip: string): boolean {
  const range = cidrToRange(cidr);
  const ipInt = ipv4ToInt(ip);
  if (!range || ipInt == null) return false;
  return ipInt >= range.start && ipInt <= range.end;
}

export function classifyHop(hop: Hop, target: string): HopClassification {
  const normalizedIp = hop.ip?.trim() ?? "";
  const normalizedLatency = hop.latency?.trim() ?? "";
  const noResponseIp = isNoResponseValue(normalizedIp, NO_RESPONSE_IP_VALUES);
  const noResponseLatency = isNoResponseValue(normalizedLatency, NO_RESPONSE_LATENCY_VALUES);
  const noResponse = noResponseIp || noResponseLatency;

  const validIp = isValidIpv4(normalizedIp);
  const hasLatency = !Number.isNaN(parseFloat(normalizedLatency));
  const responded = validIp && hasLatency && !noResponse;

  const privateIp = validIp && isPrivateIpv4(normalizedIp);
  const publicIp = validIp && !privateIp;

  const normalizedTarget = target.trim().toLowerCase();
  const destination =
    validIp &&
    normalizedTarget.length > 0 &&
    (normalizedIp.toLowerCase() === normalizedTarget ||
      hop.hostname?.trim().toLowerCase() === normalizedTarget);

  let ownership: HopClassification["ownership"];
  if (validIp) {
    const matched = (ownershipEntries as OwnershipEntry[]).find(entry =>
      cidrContains(entry.cidr, normalizedIp),
    );
    ownership = matched
      ? {
          owner: matched.owner,
          label: matched.label,
          city: matched.city,
        }
      : {
          owner: "unknown",
          label: "Unknown network",
        };
  }

  const explanationParts: string[] = [];
  if (noResponse) {
    explanationParts.push("No reply (common on TCP traces / firewalled hops)");
    if (ownership?.owner === "customer_lan") {
      explanationParts.push("Likely filtered by customer firewall");
    }
    if (ownership?.owner === "mpls_core") {
      explanationParts.push("Likely filtered inside MPLS core");
    }
  } else if (responded) {
    explanationParts.push("Responded hop (TTL-expired reply received)");
    if (ownership?.owner === "123net_pop") {
      explanationParts.push("123NET POP hop");
    }
  }
  if (privateIp) {
    explanationParts.push("Private IP (RFC1918)");
  } else if (publicIp) {
    explanationParts.push("Public IP");
  }
  if (destination) {
    explanationParts.push("Destination hop");
  }
  if (ownership?.label && ownership.label !== "Unknown network") {
    const location = ownership.city ? ` (${ownership.city})` : "";
    explanationParts.push(`Site: ${ownership.label}${location}`);
  }

  return {
    flags: {
      responded,
      no_response: noResponse,
      private_ip: privateIp,
      public_ip: publicIp,
      destination,
    },
    ownership,
    explanation: explanationParts.join(". "),
  };
}
