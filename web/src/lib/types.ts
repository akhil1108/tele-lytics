/** TypeScript mirrors of the API's response shapes (`/openapi.json`). */

export type Role = "owner" | "admin" | "supervisor" | "agent";
export type AgentStatus = "offline" | "available" | "on_call" | "wrap_up" | "break";
export type Sentiment =
  | "very_negative"
  | "negative"
  | "neutral"
  | "positive"
  | "very_positive";
export type Priority = "low" | "medium" | "high" | "urgent";
export type TaskStatus = "open" | "in_progress" | "done" | "dismissed";
export type LeadCategory = "lead" | "other";
export type LeadStatus = "new" | "contacted" | "dismissed";
export type ProcessingStatus =
  | "complete"
  | "analysing"
  | "transcribing"
  | "no_recording"
  | "failed";

export interface User {
  id: string;
  org_id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Session {
  user: User;
  organization_name: string;
  tokens: TokenPair;
}

export interface Agent {
  id: string;
  org_id: string;
  display_name: string;
  phone_number: string;
  employee_code: string | null;
  team: string | null;
  status: AgentStatus;
  status_changed_at: string | null;
  last_seen_at: string | null;
  current_call_id: string | null;
  is_active: boolean;
  calls_today?: number;
  calls_in_range?: number;
  avg_sentiment?: number | null;
  satisfied_rate?: number | null;
  avg_duration_seconds?: number | null;
  open_tasks?: number;
}

export interface Presence {
  total_agents: number;
  online: number;
  available: number;
  on_call: number;
  wrap_up: number;
  on_break: number;
  offline: number;
  updated_at: string;
}

export interface RecordingPolicy {
  id: string;
  org_id: string;
  e164: string;
  label: string | null;
  kind: "agent" | "customer" | "did" | "other";
  owner_agent_id: string | null;
  recording_enabled: boolean;
  record_inbound: boolean;
  record_outbound: boolean;
  consent_required: boolean;
  consent_prompt: string | null;
  retention_days: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
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
  org_id: string;
  agent_id: string;
  external_ref: string | null;
  direction: "inbound" | "outbound" | "unknown";
  agent_number: string;
  customer_number: string;
  customer_name: string | null;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  status: string;
  disposition: string | null;
  recording_expected: boolean;
  recording_skipped_reason: string | null;
  has_recording: boolean;
  created_at: string;
}

export interface CallListItem extends Call {
  agent_name: string | null;
  agent_team: string | null;
  sentiment_overall: Sentiment | null;
  sentiment_score: number | null;
  customer_satisfied: boolean | null;
  csat_score: number | null;
  category_name: string | null;
  has_transcript: boolean;
  has_analysis: boolean;
  processing_status: ProcessingStatus;
  open_tasks: number;
}

export interface Segment {
  id: string;
  idx: number;
  speaker: "agent" | "customer" | "unknown";
  start_ms: number;
  end_ms: number;
  text: string;
  confidence: number | null;
  tone_label: string | null;
  tone_confidence: number | null;
  valence: number | null;
  arousal: number | null;
  sentiment: Sentiment | null;
}

export interface Transcript {
  id: string;
  call_id: string;
  provider: string;
  model: string | null;
  language: string | null;
  full_text: string;
  word_count: number;
  confidence: number | null;
  tone_overall: string | null;
  created_at: string;
  segments: Segment[];
}

export interface SpeakerStopwordStats {
  word_count: number;
  filler_count: number;
  filler_rate_per_100_words: number;
  hedge_count: number;
  stopword_count: number;
  content_word_count: number;
  content_density: number;
  top_fillers: { term: string; count: number }[];
  top_content_words: { term: string; count: number }[];
}

export interface RiskFlag {
  kind: string;
  severity: Priority;
  detail: string;
  source_quote: string | null;
}

export interface SentimentPoint {
  at_ms: number;
  speaker: string;
  score: number;
  label: Sentiment;
  note: string | null;
}

export interface CustomRatingScore {
  parameter_id: string;
  parameter_name: string;
  score: number;
  scale_min: number;
  scale_max: number;
  rationale: string | null;
}

export interface Analysis {
  id: string;
  call_id: string;
  provider: string;
  model: string | null;
  summary: string;
  sentiment_overall: Sentiment;
  sentiment_score: number;
  customer_satisfied: boolean | null;
  csat_score: number | null;
  csat_confidence: number | null;
  csat_evidence: string | null;
  agent_talk_ratio: number | null;
  interruption_count: number | null;
  resolution_status: string | null;
  category_name: string | null;
  category_confidence: number | null;
  custom_ratings: CustomRatingScore[];
  topics: string[];
  keywords: string[];
  stopword_stats: Record<string, SpeakerStopwordStats>;
  filler_stats: Record<string, { assessment: string | null; top_fillers: string[] }>;
  risk_flags: RiskFlag[];
  coaching: {
    strengths?: string[];
    improvements?: string[];
    missed_opportunities?: string[];
  };
  sentiment_timeline: SentimentPoint[];
  tone_summary: Record<string, string>;
  processing_ms: number | null;
  created_at: string;
}

export interface ActionItem {
  id: string;
  call_id: string;
  kind: "task" | "action";
  title: string;
  description: string | null;
  owner_role: string | null;
  assignee_agent_id: string | null;
  priority: Priority;
  due_at: string | null;
  due_hint: string | null;
  status: TaskStatus;
  source_quote: string | null;
  created_at: string;
  completed_at: string | null;
  agent_name?: string | null;
  customer_number?: string | null;
  call_started_at?: string | null;
}

export interface Recording {
  id: string;
  call_id: string;
  status: "pending_upload" | "stored" | "failed" | "purged";
  mime_type: string;
  size_bytes: number | null;
  duration_seconds: number | null;
  consent_captured: boolean;
  uploaded_at: string | null;
  purge_after: string | null;
  purged_at: string | null;
}

export interface Job {
  id: string;
  stage: "transcribe" | "analyze";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  scheduled_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface CallDetail extends Call {
  agent_name: string | null;
  call_metadata: Record<string, unknown>;
  agent_team: string | null;
  recording: Recording | null;
  transcript: Transcript | null;
  analysis: Analysis | null;
  action_items: ActionItem[];
  jobs: Job[];
}

export interface Overview {
  range_start: string;
  range_end: string;
  agents_total: number;
  agents_online: number;
  agents_on_call: number;
  calls_total: number;
  calls_inbound: number;
  calls_outbound: number;
  calls_missed: number;
  total_talk_seconds: number;
  avg_duration_seconds: number | null;
  calls_recorded: number;
  recording_coverage: number | null;
  numbers_with_recording_enabled: number;
  numbers_total: number;
  calls_analysed: number;
  avg_sentiment: number | null;
  satisfied_count: number;
  unsatisfied_count: number;
  unknown_satisfaction_count: number;
  satisfaction_rate: number | null;
  avg_csat: number | null;
  avg_agent_talk_ratio: number | null;
  avg_filler_rate: number | null;
  open_tasks: number;
  overdue_tasks: number;
  risk_flag_count: number;
  pipeline_queued: number;
  pipeline_running: number;
  pipeline_failed: number;
}

export interface TimeseriesPoint {
  bucket: string;
  calls: number;
  recorded: number;
  analysed: number;
  avg_sentiment: number | null;
  satisfied: number;
  unsatisfied: number;
  talk_seconds: number;
}

export interface SentimentBreakdown {
  label: Sentiment;
  count: number;
  share: number;
}

export interface LeaderboardRow {
  agent_id: string;
  agent_name: string;
  team: string | null;
  calls: number;
  avg_sentiment: number | null;
  satisfaction_rate: number | null;
  avg_duration_seconds: number | null;
  filler_rate: number | null;
  open_tasks: number;
}

export interface TermCount {
  term: string;
  count: number;
  speaker: string | null;
}

export interface RiskSummary {
  kind: string;
  count: number;
  severity_high: number;
}

export interface NumberCoverage {
  number: string;
  label: string | null;
  calls: number;
  recorded: number;
  coverage: number;
  recording_enabled: boolean;
  policy_id: string | null;
  configured: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface RatingParameter {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  scale_min: number;
  scale_max: number;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface CallCategory {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  is_default: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface Lead {
  id: string;
  org_id: string;
  call_id: string;
  agent_id: string | null;
  customer_number: string;
  customer_name: string | null;
  lead_name: string | null;
  lead_email: string | null;
  purpose: string | null;
  intent: string | null;
  category: LeadCategory;
  confidence: number;
  reason: string | null;
  source_quote: string | null;
  status: LeadStatus;
  created_at: string;
  updated_at: string;
  agent_name?: string | null;
  call_started_at?: string | null;
}
