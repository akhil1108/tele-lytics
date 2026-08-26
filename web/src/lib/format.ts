import type { ProcessingStatus, Sentiment } from "./types";

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
}

/** `mm:ss` for transcript timestamps. */
export function stamp(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  return `${String(minutes).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString();
}

export function decimal(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function dayLabel(iso: string, bucket: "hour" | "day" | "week"): string {
  const date = new Date(iso);
  if (bucket === "hour") {
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const deltaSeconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (deltaSeconds < 60) return "just now";
  if (deltaSeconds < 3600) return `${Math.floor(deltaSeconds / 60)}m ago`;
  if (deltaSeconds < 86_400) return `${Math.floor(deltaSeconds / 3600)}h ago`;
  return `${Math.floor(deltaSeconds / 86_400)}d ago`;
}

export function maskNumber(e164: string): string {
  if (e164.length <= 7) return e164;
  return `${e164.slice(0, 3)}${"•".repeat(e164.length - 7)}${e164.slice(-4)}`;
}

export const SENTIMENT_LABELS: Record<Sentiment, string> = {
  very_negative: "Very negative",
  negative: "Negative",
  neutral: "Neutral",
  positive: "Positive",
  very_positive: "Very positive",
};

export const PROCESSING_LABELS: Record<ProcessingStatus, string> = {
  complete: "Analysed",
  analysing: "Analysing",
  transcribing: "Transcribing",
  no_recording: "No recording",
  failed: "Failed",
};

/** Recording-policy reasons, written for a supervisor rather than a developer. */
export const POLICY_REASONS: Record<string, string> = {
  policy_enabled: "Recording is on for this number",
  no_policy_configured: "No policy set — calls are not recorded",
  recording_disabled_for_number: "Recording is switched off for this number",
  customer_opted_out: "Customer opted out of recording",
  inbound_calls_not_recorded: "Inbound calls are not recorded",
  outbound_calls_not_recorded: "Outbound calls are not recorded",
  no_direction_recorded: "Recording is off for both call directions",
  // Reported from the phone's call log rather than from a recording. These are
  // real calls with real durations that simply have no audio — not failures.
  device_cannot_record: "This handset cannot record calls",
  no_recording_on_device: "No recording was saved for this call",
  call_not_answered: "The call was not answered",
};

/** Whether a call is metadata-only by design rather than a pipeline failure. */
export function isMetadataOnly(reason: string | null | undefined): boolean {
  return (
    reason === "device_cannot_record" ||
    reason === "no_recording_on_device" ||
    reason === "call_not_answered"
  );
}

export function policyReason(reason: string): string {
  return POLICY_REASONS[reason] ?? reason.replaceAll("_", " ");
}

/** Imported recordings often carry no direction; say so rather than showing a bare word. */
export const DIRECTION_LABELS: Record<string, string> = {
  inbound: "Inbound",
  outbound: "Outbound",
  unknown: "Direction unknown",
};

export function directionLabel(direction: string): string {
  return DIRECTION_LABELS[direction] ?? titleCase(direction);
}

export function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
