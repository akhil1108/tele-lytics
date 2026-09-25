export type AgentStatus = "offline" | "available" | "on_call" | "wrap_up" | "break";
// "unknown" exists because imported recordings usually cannot tell us which
// way the call went — most OEM recorders leave it out of the filename.
export type Direction = "inbound" | "outbound" | "unknown";

export interface DeviceSession {
  device_token: string;
  device_id: string;
  agent_id: string;
  agent_name: string;
  agent_number: string;
  org_id: string;
  organization_name: string;
}

export interface Agent {
  id: string;
  display_name: string;
  phone_number: string;
  team: string | null;
  status: AgentStatus;
  last_seen_at: string | null;
}

export interface PolicyDecision {
  number: string;
  should_record: boolean;
  reason: string;
  consent_required: boolean;
  consent_prompt: string | null;
  policy_id: string | null;
  retention_days: number | null;
}

export interface Call {
  id: string;
  direction: Direction;
  agent_number: string;
  customer_number: string;
  customer_name: string | null;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  status: string;
  recording_expected: boolean;
  recording_skipped_reason: string | null;
  has_recording: boolean;
}

/** One window of the agent's own figures, as `/v1/mobile/summary` returns it. */
export interface PeriodStats {
  calls: number;
  inbound: number;
  outbound: number;
  missed: number;
  talk_seconds: number;
  recorded: number;
  avg_call_seconds: number | null;
  avg_sentiment: number | null;
}

export interface DaySummary {
  agent_id: string;
  agent_name: string;
  status: AgentStatus;
  calls_today: number;
  talk_seconds_today: number;
  recorded_today: number;
  avg_sentiment_today: number | null;
  uploads_outstanding: number;
  today: PeriodStats;
  /** Today plus the six days before it. */
  week: PeriodStats;
}

/** A recording waiting to be uploaded. Persisted, so it survives a restart. */
export interface PendingUpload {
  id: string;
  callId: string;
  fileUri: string;
  mimeType: string;
  fileName: string;
  durationSeconds: number | null;
  consentCaptured: boolean;
  customerNumber: string;
  startedAt: string;
  attempts: number;
  nextAttemptAt: number;
  lastError: string | null;
  createdAt: number;
}
