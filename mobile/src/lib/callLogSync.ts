import type { CallLogEntry, CallLogType } from "../../modules/call-log";
import { isUntracked, type NameSource } from "./callInsights";
import type { ParsedRecording } from "./callRecordings";

/**
 * Turning the phone's call log into calls, and pairing them with recordings.
 *
 * The call log is the spine of the Android flow. It knows every call the phone
 * made or took, with the exact duration and which way it went — things a
 * recording's filename does not reliably carry, and things that stay true even
 * when there is no recording at all.
 *
 * Recordings enrich that spine. A recording is matched to a log entry by number
 * and time, so the call gets its real duration and direction from the log and
 * its audio from the file. A call with no matching recording is still a call:
 * it counts towards volume and talk time, it just has no transcript.
 *
 * This module is pure — no React Native, no native module, no network — so the
 * matching rules can be tested directly. That matters because getting a
 * recording attached to the wrong call would put one customer's words under
 * another customer's name.
 */

export type SyncDirection = "inbound" | "outbound" | "unknown";
export type SyncStatus = "completed" | "missed";

export interface CallLogCall {
  /** Provider row id, used to dedupe against the ledger. */
  logId: string;
  number: string;
  startedAt: Date;
  endedAt: Date | null;
  durationSeconds: number;
  direction: SyncDirection;
  status: SyncStatus;
  /** The original call-log type, kept for the audit trail. */
  logType: CallLogType;
  /** The dialler's caller-ID name for the number, when it had one. */
  cachedName: string | null;
}

/** Call-log types that represent a real call worth reporting. */
const REPORTABLE: CallLogType[] = ["incoming", "outgoing", "missed"];

/**
 * Voicemail and blocked entries are not calls the agent handled, and a
 * rejected call is the agent declining rather than working. Reporting them
 * would inflate the day's call count with things nobody spoke on.
 */
export function isReportable(entry: CallLogEntry): boolean {
  return REPORTABLE.includes(entry.type);
}

export function directionFor(type: CallLogType): SyncDirection {
  if (type === "outgoing") return "outbound";
  if (type === "incoming" || type === "missed") return "inbound";
  return "unknown";
}

/** Private, withheld and unknown callers arrive with no usable number. */
export function hasUsableNumber(entry: CallLogEntry): boolean {
  const digits = (entry.number ?? "").replace(/\D/g, "");
  return digits.length >= 6;
}

export function toCall(entry: CallLogEntry): CallLogCall {
  const startedAt = new Date(entry.timestamp);
  const duration = Math.max(0, Math.round(entry.durationSeconds));
  // A missed call has no talk time; giving it an end equal to its start keeps
  // the record honest rather than implying a zero-length conversation.
  const endedAt = entry.type === "missed" ? startedAt : new Date(entry.timestamp + duration * 1000);

  return {
    logId: entry.id,
    number: entry.number,
    startedAt,
    endedAt,
    durationSeconds: entry.type === "missed" ? 0 : duration,
    direction: directionFor(entry.type),
    status: entry.type === "missed" ? "missed" : "completed",
    logType: entry.type,
    cachedName: entry.name?.trim() || null,
  };
}

/** Filter, convert and order a raw batch from the provider. */
export function prepareBatch(
  entries: CallLogEntry[],
  alreadySynced: ReadonlySet<string>,
  untracked: ReadonlySet<string> = new Set(),
): {
  calls: CallLogCall[];
  skippedUnreportable: number;
  skippedNoNumber: number;
  /**
   * Log ids of calls with numbers the agent chose not to track. The caller
   * adds them to the ledger so they stay unreported even if the number is
   * tracked again later — un-hiding a number is not consent to back-fill.
   */
  untrackedIds: string[];
} {
  const calls: CallLogCall[] = [];
  const untrackedIds: string[] = [];
  let skippedUnreportable = 0;
  let skippedNoNumber = 0;

  for (const entry of entries) {
    if (alreadySynced.has(entry.id)) continue;
    if (!isReportable(entry)) {
      skippedUnreportable += 1;
      continue;
    }
    if (!hasUsableNumber(entry)) {
      skippedNoNumber += 1;
      continue;
    }
    if (isUntracked(entry.number, untracked)) {
      untrackedIds.push(entry.id);
      continue;
    }
    calls.push(toCall(entry));
  }

  calls.sort((a, b) => a.startedAt.getTime() - b.startedAt.getTime());
  return { calls, skippedUnreportable, skippedNoNumber, untrackedIds };
}

// ------------------------------------------------------- matching recordings

/**
 * How far a recording's timestamp may sit from a call-log entry's and still be
 * the same call.
 *
 * Recorders stamp the filename at different moments — some when recording
 * starts, some when the file is finalised at the end — so the gap can be the
 * length of the call plus clock skew. Three minutes covers ordinary calls;
 * beyond that the number match alone is not enough to be sure.
 */
export const MATCH_WINDOW_MS = 3 * 60 * 1000;

/** Compare numbers by their last nine digits, which survives formatting. */
export function sameNumber(left: string, right: string): boolean {
  const normalise = (value: string) => (value ?? "").replace(/\D/g, "");
  const a = normalise(left);
  const b = normalise(right);
  if (!a || !b) return false;
  const length = Math.min(9, a.length, b.length);
  if (length < 6) return a === b;
  return a.slice(-length) === b.slice(-length);
}

export interface MatchCandidate {
  fileName: string;
  parsed: ParsedRecording;
}

export interface MatchResult<T extends MatchCandidate> {
  /** Recording paired with a call-log entry — the good case. */
  matched: { call: CallLogCall; recording: T }[];
  /** Calls the log knows about with no recording on disk. */
  unmatchedCalls: CallLogCall[];
  /** Recordings with no call-log entry — usually history older than the sync. */
  unmatchedRecordings: T[];
}

/**
 * Pair recordings with call-log entries.
 *
 * Greedy nearest-in-time within the window, one recording per call. A
 * recording that could fit two calls goes to the closer one; a call that has
 * already taken a recording is not offered a second.
 */
export function matchRecordingsToCalls<T extends MatchCandidate>(
  calls: CallLogCall[],
  recordings: T[],
): MatchResult<T> {
  const matched: { call: CallLogCall; recording: T }[] = [];
  const takenRecordings = new Set<T>();
  const unmatchedCalls: CallLogCall[] = [];

  for (const call of calls) {
    let best: T | null = null;
    let bestDistance = Number.POSITIVE_INFINITY;

    for (const recording of recordings) {
      if (takenRecordings.has(recording)) continue;
      if (!recording.parsed.recordedAt) continue;
      if (!recording.parsed.customerNumber) continue;
      if (!sameNumber(recording.parsed.customerNumber, call.number)) continue;

      const distance = Math.abs(
        recording.parsed.recordedAt.getTime() - call.startedAt.getTime(),
      );
      if (distance <= MATCH_WINDOW_MS && distance < bestDistance) {
        best = recording;
        bestDistance = distance;
      }
    }

    if (best) {
      matched.push({ call, recording: best });
      takenRecordings.add(best);
    } else {
      unmatchedCalls.push(call);
    }
  }

  return {
    matched,
    unmatchedCalls,
    unmatchedRecordings: recordings.filter((recording) => !takenRecordings.has(recording)),
  };
}

// ------------------------------------------------------------- API payloads

/** The reason recorded on a call the log knows about but nothing recorded. */
export type NoAudioReason =
  | "no_recording_on_device"
  | "device_cannot_record"
  | "call_not_answered";

export function noAudioReason(call: CallLogCall, deviceCanRecord: boolean): NoAudioReason {
  if (call.status === "missed") return "call_not_answered";
  return deviceCanRecord ? "no_recording_on_device" : "device_cannot_record";
}

/**
 * Build the `POST /v1/mobile/calls` body for a call-log entry.
 *
 * `recording_expected` is false for a metadata-only call, which keeps it out of
 * the dashboard's recording-coverage figure — coverage measures whether the
 * pipeline worked, not how many calls happened to be recorded.
 */
export function callPayload(
  call: CallLogCall,
  options: {
    deviceId: string;
    hasRecording: boolean;
    deviceCanRecord: boolean;
    originalFilename?: string;
    customerName?: string | null;
    nameSource?: NameSource | null;
  },
): Record<string, unknown> {
  return {
    external_ref: `log-${options.deviceId.replace(/-/g, "").slice(0, 8)}-${call.logId}`,
    direction: call.direction,
    customer_number: call.number,
    customer_name: options.customerName?.slice(0, 160) || null,
    started_at: call.startedAt.toISOString(),
    ended_at: call.endedAt?.toISOString() ?? null,
    duration_seconds: call.durationSeconds,
    status: call.status,
    recording_expected: options.hasRecording,
    recording_skipped_reason: options.hasRecording
      ? null
      : noAudioReason(call, options.deviceCanRecord),
    metadata: {
      source: options.hasRecording ? "call_log_with_recording" : "call_log_only",
      call_log_type: call.logType,
      direction_source: "call_log",
      ...(options.customerName && options.nameSource ? { name_source: options.nameSource } : {}),
      ...(options.originalFilename ? { original_filename: options.originalFilename } : {}),
    },
  };
}

/** Newest entry timestamp in a batch, for advancing the sync cursor. */
export function newestTimestamp(entries: CallLogEntry[], fallback: number): number {
  return entries.reduce((latest, entry) => Math.max(latest, entry.timestamp), fallback);
}
