import { ApiRequestError, apiPost } from "./api";

export type BrowserSyncTarget = "chrome" | "edge";

export type BrowserSyncResponse = {
  status?: string;
  imported_count?: number;
  domain?: string;
  message?: string;
  detail?: string;
};

const BROWSER_SYNC_ENDPOINTS = [
  "/api/auth/import_from_browser",
  "/api/auth/sync_from_browser",
  "/api/auth/import-from-browser",
  "/api/auth/import-browser",
  "/api/auth/sync-from-browser",
];

export async function syncAuthFromBrowser(args: {
  browser: BrowserSyncTarget;
  domain: string;
  profile: string;
}): Promise<BrowserSyncResponse> {
  const query = new URLSearchParams({
    browser: args.browser,
    domain: args.domain,
    profile: args.profile,
  }).toString();

  let lastError: unknown = null;
  for (const endpoint of BROWSER_SYNC_ENDPOINTS) {
    try {
      return await apiPost<BrowserSyncResponse>(`${endpoint}?${query}`, {});
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 404) {
        lastError = error;
        continue;
      }
      throw error;
    }
  }

  throw lastError instanceof Error ? lastError : new Error("Browser sync endpoint not found.");
}

