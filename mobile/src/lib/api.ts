import * as SecureStore from "expo-secure-store";

import { API_BASE_URL, REQUEST_TIMEOUT_MS, UPLOAD_TIMEOUT_MS } from "./config";
import type { Agent, Call, DaySummary, DeviceSession, Direction, PolicyDecision } from "./types";

const TOKEN_KEY = "call_analytics_device_token";
const SESSION_KEY = "call_analytics_session";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** A 401 means the handset was unpaired; retrying will never help. */
  get isAuthFailure(): boolean {
    return this.status === 401 || this.status === 403;
  }

  /** Client errors are permanent; anything else may succeed on a retry. */
  get isRetryable(): boolean {
    return this.status === 0 || this.status === 408 || this.status === 429 || this.status >= 500;
  }
}

/**
 * The device token is the handset's only credential and it is long-lived, so
 * it lives in the platform keystore rather than AsyncStorage.
 */
export const credentials = {
  async save(session: DeviceSession): Promise<void> {
    await SecureStore.setItemAsync(TOKEN_KEY, session.device_token);
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(session));
  },
  async token(): Promise<string | null> {
    return SecureStore.getItemAsync(TOKEN_KEY);
  },
  async session(): Promise<DeviceSession | null> {
    const raw = await SecureStore.getItemAsync(SESSION_KEY);
    return raw ? (JSON.parse(raw) as DeviceSession) : null;
  },
  async clear(): Promise<void> {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(SESSION_KEY);
  },
};

async function parseError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (body?.error?.message) message = body.error.message;
    else if (typeof body?.detail === "string") message = body.detail;
    else if (Array.isArray(body?.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
  } catch {
    /* keep the status-derived message */
  }
  return new ApiError(response.status, message);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const token = await credentials.token();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
    if (!response.ok) throw await parseError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (caught) {
    if (caught instanceof ApiError) throw caught;
    // A network failure or an abort — status 0 marks it retryable.
    const message =
      caught instanceof Error && caught.name === "AbortError"
        ? "The request timed out"
        : "Could not reach the server";
    throw new ApiError(0, message);
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  /** Pairing is the one unauthenticated call: the code itself is the credential. */
  pair: (body: {
    code: string;
    platform: string;
    device_name?: string;
    os_version?: string;
    app_version?: string;
  }) =>
    request<DeviceSession>("/v1/auth/devices/pair", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  me: () => request<Agent>("/v1/mobile/me"),

  setStatus: (status: string, callId?: string) =>
    request<Agent>("/v1/mobile/status", {
      method: "POST",
      body: JSON.stringify({ status, call_id: callId ?? null }),
    }),

  recordingPolicy: (customerNumber: string, direction: Direction) =>
    request<PolicyDecision>(
      `/v1/mobile/recording-policy?customer_number=${encodeURIComponent(customerNumber)}&direction=${direction}`,
    ),

  logCall: (body: Record<string, unknown>) =>
    request<Call>("/v1/mobile/calls", { method: "POST", body: JSON.stringify(body) }),

  myCalls: (limit = 30) => request<Call[]>(`/v1/mobile/calls?limit=${limit}`),

  // The server's "today" is the handset's today, not UTC's.
  summary: () =>
    request<DaySummary>(
      `/v1/mobile/summary?tz_offset_minutes=${-new Date().getTimezoneOffset()}`,
    ),

  unpair: () => request<{ ok: boolean }>("/v1/mobile/unpair", { method: "POST" }),

  uploadRecording: (
    callId: string,
    file: { uri: string; name: string; type: string },
    meta: { durationSeconds: number | null; consentCaptured: boolean },
  ) => {
    const form = new FormData();
    // React Native's FormData takes this shape for a file; the cast is the
    // documented way to satisfy the DOM typings it borrows.
    form.append("file", file as unknown as Blob);
    if (meta.durationSeconds !== null) {
      form.append("duration_seconds", String(meta.durationSeconds));
    }
    form.append("consent_captured", String(meta.consentCaptured));

    return request<{ id: string; status: string }>(
      `/v1/mobile/calls/${callId}/recording`,
      { method: "POST", body: form },
      UPLOAD_TIMEOUT_MS,
    );
  },
};
