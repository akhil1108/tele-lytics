import Constants from "expo-constants";

/**
 * API base URL.
 *
 * `EXPO_PUBLIC_API_BASE_URL` wins so a build can be pointed at staging or
 * production without editing `app.json`. On a physical handset this must be a
 * LAN or public address — `localhost` there means the phone itself.
 */
export const API_BASE_URL: string =
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:8000";

/** Uploads are retried on their own schedule; a slow link should not fail one. */
export const UPLOAD_TIMEOUT_MS = 180_000;
export const REQUEST_TIMEOUT_MS = 20_000;

/** How long the queue waits before retrying a failed upload, by attempt. */
export const RETRY_BACKOFF_MS = [30_000, 120_000, 600_000, 1_800_000];
export const MAX_UPLOAD_ATTEMPTS = 6;
