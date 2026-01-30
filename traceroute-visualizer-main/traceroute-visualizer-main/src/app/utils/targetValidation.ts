const HOSTNAME_LABEL_REGEX = /^[a-zA-Z0-9-]{1,63}$/;

function isValidIpv4(ip: string): boolean {
  const parts = ip.split(".");
  if (parts.length !== 4) return false;
  return parts.every(part => {
    if (!/^\d+$/.test(part)) return false;
    const num = Number(part);
    return num >= 0 && num <= 255;
  });
}

function isValidHostname(target: string): boolean {
  const normalized = target.endsWith(".") ? target.slice(0, -1) : target;
  if (!normalized || normalized.length > 253) return false;
  const labels = normalized.split(".");
  return labels.every(label => {
    if (!label) return false;
    if (label.startsWith("-") || label.endsWith("-")) return false;
    return HOSTNAME_LABEL_REGEX.test(label);
  });
}

export function getTargetValidationError(target: string): string | null {
  const trimmed = target.trim();
  if (!trimmed) return "Enter a hostname or IPv4 address.";
  if (isValidIpv4(trimmed)) return null;
  if (isValidHostname(trimmed)) return null;
  return "Target must be a valid IPv4 address or hostname.";
}
