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
  explanation: string;
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

  const explanationParts: string[] = [];
  if (noResponse) {
    explanationParts.push("No reply (common on TCP traces / firewalled hops)");
  } else if (responded) {
    explanationParts.push("Responded hop (TTL-expired reply received)");
  }
  if (privateIp) {
    explanationParts.push("Private IP (RFC1918)");
  } else if (publicIp) {
    explanationParts.push("Public IP");
  }
  if (destination) {
    explanationParts.push("Destination hop");
  }

  return {
    flags: {
      responded,
      no_response: noResponse,
      private_ip: privateIp,
      public_ip: publicIp,
      destination,
    },
    explanation: explanationParts.join(". "),
  };
}
