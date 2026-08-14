import "server-only";

import { getDriveAccessToken } from "./service-account";

const DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files";
const DRIVE_ABOUT_URL = "https://www.googleapis.com/drive/v3/about";
const DEFAULT_TIMEOUT_MS = 20_000;

export type DriveErrorCode =
  | "drive_unauthorized"
  | "drive_forbidden"
  | "drive_not_found"
  | "drive_rate_limited"
  | "drive_upstream_error"
  | "drive_error"
  | "drive_request_timeout"
  | "drive_network_error";

export class DriveApiError extends Error {
  constructor(public readonly status: number, public readonly code: DriveErrorCode) {
    super(code);
    this.name = "DriveApiError";
  }
}

export function classifyDriveStatus(status: number): DriveErrorCode {
  if (status === 401) return "drive_unauthorized";
  if (status === 403) return "drive_forbidden";
  if (status === 404) return "drive_not_found";
  if (status === 429) return "drive_rate_limited";
  if (status >= 500) return "drive_upstream_error";
  return "drive_error";
}

type DriveFetchInit = { headers?: Record<string, string>; timeoutMs?: number };

async function driveFetch(url: string, init: DriveFetchInit, clientSignal?: AbortSignal): Promise<Response> {
  const token = await getDriveAccessToken();
  const timeoutSignal = AbortSignal.timeout(init.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const signal = clientSignal ? AbortSignal.any([clientSignal, timeoutSignal]) : timeoutSignal;
  try {
    return await fetch(url, { headers: { Authorization: `Bearer ${token}`, ...init.headers }, signal, cache: "no-store" });
  } catch (error) {
    if (clientSignal?.aborted) throw error;
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new DriveApiError(0, "drive_request_timeout");
    }
    throw new DriveApiError(0, "drive_network_error");
  }
}

export type DriveFileMetadata = {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  thumbnailLink?: string;
  modifiedTime?: string;
  driveId?: string;
};

export async function getDriveFileMetadata(fileId: string, fields: string, clientSignal?: AbortSignal): Promise<DriveFileMetadata> {
  const url = `${DRIVE_FILES_URL}/${encodeURIComponent(fileId)}?fields=${encodeURIComponent(fields)}&supportsAllDrives=true`;
  const response = await driveFetch(url, {}, clientSignal);
  if (!response.ok) throw new DriveApiError(response.status, classifyDriveStatus(response.status));
  return (await response.json()) as DriveFileMetadata;
}

// Streams file bytes directly from Drive - the caller pipes response.body to
// the client without buffering. `range`, when present, is forwarded verbatim
// so Drive itself performs the partial-content slicing.
export async function downloadDriveFile(
  fileId: string,
  options: { range?: string | null; clientSignal?: AbortSignal; timeoutMs?: number } = {},
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (options.range) headers.Range = options.range;
  const url = `${DRIVE_FILES_URL}/${encodeURIComponent(fileId)}?alt=media&supportsAllDrives=true`;
  const response = await driveFetch(url, { headers, timeoutMs: options.timeoutMs ?? 120_000 }, options.clientSignal);
  if (!response.ok && response.status !== 206 && response.status !== 416) {
    throw new DriveApiError(response.status, classifyDriveStatus(response.status));
  }
  return response;
}

// thumbnailLink is a short-lived, pre-authorized Google URL. It is fetched
// here, server-side, immediately after being read from file metadata, and
// its bytes (never the URL itself) are what callers forward to the browser.
export async function fetchDriveThumbnailLinkBytes(thumbnailLink: string, clientSignal?: AbortSignal): Promise<Response> {
  let parsed: URL;
  try {
    parsed = new URL(thumbnailLink);
  } catch {
    throw new DriveApiError(0, "drive_error");
  }
  if (parsed.protocol !== "https:" || !parsed.hostname.endsWith("googleusercontent.com")) {
    throw new DriveApiError(0, "drive_error");
  }
  const response = await driveFetch(thumbnailLink, { timeoutMs: 20_000 }, clientSignal);
  if (!response.ok) throw new DriveApiError(response.status, classifyDriveStatus(response.status));
  return response;
}

export async function getDriveAbout(clientSignal?: AbortSignal): Promise<{ user?: { emailAddress?: string }; storageQuota?: unknown }> {
  const response = await driveFetch(`${DRIVE_ABOUT_URL}?fields=user(emailAddress),storageQuota`, {}, clientSignal);
  if (!response.ok) throw new DriveApiError(response.status, classifyDriveStatus(response.status));
  return (await response.json()) as { user?: { emailAddress?: string }; storageQuota?: unknown };
}

export async function getSharedDriveMetadata(driveId: string, clientSignal?: AbortSignal): Promise<{ id: string; name: string }> {
  const url = `https://www.googleapis.com/drive/v3/drives/${encodeURIComponent(driveId)}?fields=id,name`;
  const response = await driveFetch(url, {}, clientSignal);
  if (!response.ok) throw new DriveApiError(response.status, classifyDriveStatus(response.status));
  return (await response.json()) as { id: string; name: string };
}
