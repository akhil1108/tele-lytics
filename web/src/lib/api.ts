"use client";

import type {
  ActionItem,
  Agent,
  Call,
  CallDetail,
  CallListItem,
  LeaderboardRow,
  NumberCoverage,
  Overview,
  Page,
  PolicyDecision,
  Presence,
  RecordingPolicy,
  RiskSummary,
  SentimentBreakdown,
  Session,
  TermCount,
  TimeseriesPoint,
  Transcript,
  User,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const ACCESS_KEY = "ca.access_token";
const REFRESH_KEY = "ca.refresh_token";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const tokenStore = {
  get access() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    window.localStorage.setItem(ACCESS_KEY, access);
    window.localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    window.localStorage.removeItem(ACCESS_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  },
};

/** Refresh in flight, so a burst of 401s triggers exactly one token exchange. */
let refreshing: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refresh_token = tokenStore.refresh;
  if (!refresh_token) return false;

  const response = await fetch(`${API_BASE_URL}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });
  if (!response.ok) {
    tokenStore.clear();
    return false;
  }
  const tokens = await response.json();
  tokenStore.set(tokens.access_token, tokens.refresh_token ?? refresh_token);
  return true;
}

async function parseError(response: Response): Promise<ApiError> {
  let message = response.statusText || "Request failed";
  let code: string | undefined;
  try {
    const body = await response.json();
    if (body?.error) {
      message = body.error.message ?? message;
      code = body.error.code;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body?.detail)) {
      // FastAPI validation errors: surface the first field problem plainly.
      const first = body.detail[0];
      const field = Array.isArray(first?.loc) ? first.loc.slice(1).join(".") : "";
      message = field ? `${field}: ${first.msg}` : first.msg;
    }
  } catch {
    /* a non-JSON body leaves the status text in place */
  }
  return new ApiError(response.status, message, code);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const access = tokenStore.access;
  if (access) headers.set("Authorization", `Bearer ${access}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (response.status === 401 && retry && tokenStore.refresh) {
    refreshing ??= refreshAccessToken().finally(() => {
      refreshing = null;
    });
    if (await refreshing) return request<T>(path, init, false);
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

export interface CallFilters {
  days?: number;
  agent_id?: string;
  team?: string;
  direction?: string;
  status?: string;
  sentiment?: string;
  satisfied?: boolean;
  has_recording?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  login: (email: string, password: string) =>
    request<Session>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/v1/auth/me"),

  overview: (days: number) => request<Overview>(`/v1/analytics/overview${query({ days })}`),
  timeseries: (days: number, bucket?: string) =>
    request<TimeseriesPoint[]>(`/v1/analytics/timeseries${query({ days, bucket })}`),
  sentimentBreakdown: (days: number) =>
    request<SentimentBreakdown[]>(`/v1/analytics/sentiment${query({ days })}`),
  leaderboard: (days: number, limit = 20) =>
    request<LeaderboardRow[]>(`/v1/analytics/agents${query({ days, limit })}`),
  fillers: (days: number, speaker = "agent") =>
    request<TermCount[]>(`/v1/analytics/fillers${query({ days, speaker })}`),
  risks: (days: number) => request<RiskSummary[]>(`/v1/analytics/risks${query({ days })}`),
  recordingCoverage: (days: number) =>
    request<NumberCoverage[]>(`/v1/analytics/recording-coverage${query({ days })}`),

  agents: (days = 7) => request<Agent[]>(`/v1/agents${query({ days })}`),
  presence: () => request<Presence>("/v1/agents/presence"),
  createAgent: (body: Record<string, unknown>) =>
    request<Agent>("/v1/agents", { method: "POST", body: JSON.stringify(body) }),
  pairingCode: (agentId: string) =>
    request<{ code: string; agent_id: string; expires_at: string }>(
      `/v1/auth/agents/${agentId}/pairing-code`,
      { method: "POST" },
    ),

  calls: (filters: CallFilters) =>
    request<Page<CallListItem>>(`/v1/calls${query(filters as Record<string, unknown>)}`),
  call: (id: string) => request<CallDetail>(`/v1/calls/${id}`),
  transcript: (id: string) => request<Transcript>(`/v1/calls/${id}/transcript`),
  reprocess: (id: string, stage: "transcribe" | "analyze") =>
    request<{ ok: boolean; message: string }>(
      `/v1/calls/${id}/reprocess${query({ stage })}`,
      { method: "POST" },
    ),

  policies: (params: Record<string, unknown> = {}) =>
    request<Page<RecordingPolicy>>(`/v1/numbers${query(params)}`),
  createPolicy: (body: Record<string, unknown>) =>
    request<RecordingPolicy>("/v1/numbers", { method: "POST", body: JSON.stringify(body) }),
  updatePolicy: (id: string, body: Record<string, unknown>) =>
    request<RecordingPolicy>(`/v1/numbers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deletePolicy: (id: string) =>
    request<{ ok: boolean; message: string }>(`/v1/numbers/${id}`, { method: "DELETE" }),
  lookupPolicy: (number: string, direction = "outbound") =>
    request<PolicyDecision>(`/v1/numbers/lookup${query({ number, direction })}`),

  tasks: (params: Record<string, unknown> = {}) =>
    request<Page<ActionItem>>(`/v1/tasks${query(params)}`),
  updateTask: (id: string, body: Record<string, unknown>) =>
    request<ActionItem>(`/v1/tasks/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
};

/**
 * Audio is fetched with the bearer token and turned into an object URL: the
 * endpoint is tenant-checked on every play, so a bare `<audio src>` pointing at
 * it would 401.
 */
export async function fetchAudioUrl(callId: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/v1/calls/${callId}/audio`, {
    headers: { Authorization: `Bearer ${tokenStore.access ?? ""}` },
  });
  if (!response.ok) throw await parseError(response);
  return URL.createObjectURL(await response.blob());
}

export type { Call };
