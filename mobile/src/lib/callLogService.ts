import AsyncStorage from "@react-native-async-storage/async-storage";
import { PermissionsAndroid, Platform } from "react-native";

import * as CallLog from "../../modules/call-log";
import { api } from "./api";
import {
  callPayload,
  matchRecordingsToCalls,
  newestTimestamp,
  prepareBatch,
  type CallLogCall,
} from "./callLogSync";
import { importRefFor, mimeTypeFor } from "./callRecordings";
import { markImported, recordingFolder, scanRecordingFolder } from "./importer";
import { uploadQueue } from "./uploadQueue";

/**
 * Keeping the server's picture of the day complete.
 *
 * Every call the phone made or took is reported, whether or not it was
 * recorded. A call with audio also gets a transcript and analysis; a call
 * without still counts towards volume, talk time and who was called.
 *
 * That distinction is the whole point of this module. A dashboard that only
 * knows about recorded calls under-reports the floor's work, and the gap is
 * invisible — which is worse than a gap you can see.
 */

const CURSOR_KEY = "call_analytics_call_log_cursor";
const SYNCED_KEY = "call_analytics_synced_log_ids";
const ENABLED_KEY = "call_analytics_call_log_enabled";

/** Bounded so the ledger cannot grow without limit on a long-lived handset. */
const LEDGER_LIMIT = 10_000;
/** A first sync on a phone with years of history is paged, not read at once. */
const BATCH_SIZE = 400;
/** How far back a first sync reaches. Older calls predate the deployment. */
const FIRST_SYNC_WINDOW_DAYS = 7;

export interface SyncReport {
  reported: number;
  withRecording: number;
  metadataOnly: number;
  skippedUnreportable: number;
  skippedNoNumber: number;
  refusedByPolicy: number;
  failed: number;
  errors: string[];
}

export const callLogEnabled = {
  async get(): Promise<boolean> {
    return (await AsyncStorage.getItem(ENABLED_KEY)) === "true";
  },
  async set(value: boolean): Promise<void> {
    await AsyncStorage.setItem(ENABLED_KEY, String(value));
  },
};

export function isSupported(): boolean {
  return Platform.OS === "android" && CallLog.isAvailable();
}

export function hasPermission(): boolean {
  return isSupported() && CallLog.hasPermission();
}

export async function requestPermission(): Promise<boolean> {
  if (!isSupported()) return false;
  const granted = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.READ_CALL_LOG,
    {
      title: "Allow access to your call log",
      message:
        "Used to report the calls you handled — the number, when it happened and " +
        "how long it lasted. Calls without a recording are still counted this way.",
      buttonPositive: "Allow",
      buttonNegative: "Not now",
    },
  );
  return granted === PermissionsAndroid.RESULTS.GRANTED;
}

// ------------------------------------------------------------------ ledger

async function readSynced(): Promise<Set<string>> {
  try {
    const raw = await AsyncStorage.getItem(SYNCED_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

async function writeSynced(ids: Set<string>): Promise<void> {
  await AsyncStorage.setItem(SYNCED_KEY, JSON.stringify([...ids].slice(-LEDGER_LIMIT)));
}

async function readCursor(): Promise<number> {
  const raw = await AsyncStorage.getItem(CURSOR_KEY);
  if (raw) return Number(raw);
  return Date.now() - FIRST_SYNC_WINDOW_DAYS * 24 * 60 * 60 * 1000;
}

async function writeCursor(value: number): Promise<void> {
  await AsyncStorage.setItem(CURSOR_KEY, String(value));
}

export async function syncedCount(): Promise<number> {
  return (await readSynced()).size;
}

/** Re-report everything in the window — for a sync that filed calls wrongly. */
export async function resetSyncState(): Promise<void> {
  await AsyncStorage.multiRemove([CURSOR_KEY, SYNCED_KEY]);
}

// -------------------------------------------------------------------- sync

/**
 * Read new call-log entries, pair them with any recordings on disk, and report
 * them.
 *
 * Safe to call repeatedly: entries already reported are skipped locally, and
 * the server treats a repeated `external_ref` as the same call.
 */
export async function syncCallLog(deviceId: string): Promise<SyncReport> {
  const report: SyncReport = {
    reported: 0,
    withRecording: 0,
    metadataOnly: 0,
    skippedUnreportable: 0,
    skippedNoNumber: 0,
    refusedByPolicy: 0,
    failed: 0,
    errors: [],
  };

  if (!hasPermission()) {
    report.errors.push("Call log access has not been granted");
    return report;
  }

  const cursor = await readCursor();
  const entries = await CallLog.getEntries(cursor, BATCH_SIZE);
  if (entries.length === 0) return report;

  const synced = await readSynced();
  const batch = prepareBatch(entries, synced);
  report.skippedUnreportable = batch.skippedUnreportable;
  report.skippedNoNumber = batch.skippedNoNumber;

  // Recordings are optional. Without a folder every call is metadata-only,
  // which is exactly the intended behaviour on a phone that cannot record.
  const folderConfigured = Boolean(await recordingFolder.get());
  let available: Awaited<ReturnType<typeof scanRecordingFolder>> = null;
  if (folderConfigured) {
    try {
      available = await scanRecordingFolder();
    } catch (caught) {
      report.errors.push(
        caught instanceof Error ? caught.message : "Could not read the recordings folder",
      );
    }
  }

  const { matched, unmatchedCalls } = matchRecordingsToCalls(
    batch.calls,
    available?.detected ?? [],
  );

  for (const pair of matched) {
    const ok = await reportCall(pair.call, {
      deviceId,
      deviceCanRecord: folderConfigured,
      recording: pair.recording,
      report,
    });
    if (ok) {
      synced.add(pair.call.logId);
      report.withRecording += 1;
    }
  }

  for (const call of unmatchedCalls) {
    const ok = await reportCall(call, {
      deviceId,
      deviceCanRecord: folderConfigured,
      recording: null,
      report,
    });
    if (ok) {
      synced.add(call.logId);
      report.metadataOnly += 1;
    }
  }

  report.reported = report.withRecording + report.metadataOnly;

  await writeSynced(synced);
  // The cursor only advances past what was actually read, so an interrupted
  // sync resumes rather than skipping the remainder of the batch.
  await writeCursor(newestTimestamp(entries, cursor));

  return report;
}

type RecordingCandidate = NonNullable<
  Awaited<ReturnType<typeof scanRecordingFolder>>
>["detected"][number];

async function reportCall(
  call: CallLogCall,
  options: {
    deviceId: string;
    deviceCanRecord: boolean;
    recording: RecordingCandidate | null;
    report: SyncReport;
  },
): Promise<boolean> {
  const { report } = options;

  try {
    // Audio is only uploaded when policy allows it. A metadata-only call is
    // just a record that a call happened, so it is always reportable — hiding
    // the day's work would not protect anyone.
    let mayUploadAudio = false;
    if (options.recording) {
      const decision = await api.recordingPolicy(call.number, call.direction);
      mayUploadAudio = decision.should_record;
      if (!mayUploadAudio) report.refusedByPolicy += 1;
    }

    const created = await api.logCall(
      callPayload(call, {
        deviceId: options.deviceId,
        hasRecording: Boolean(options.recording) && mayUploadAudio,
        deviceCanRecord: options.deviceCanRecord,
        originalFilename: options.recording?.fileName,
      }),
    );

    if (options.recording && mayUploadAudio) {
      await uploadQueue.enqueue({
        callId: created.id,
        fileUri: options.recording.uri,
        mimeType: mimeTypeFor(options.recording.fileName),
        fileName: options.recording.fileName,
        durationSeconds: call.durationSeconds || null,
        // Nothing in a dialler recording attests to a consent announcement.
        consentCaptured: false,
        customerNumber: call.number,
        startedAt: call.startedAt.toISOString(),
      });
      await markImported([options.recording.fileName]);
    }

    return true;
  } catch (caught) {
    report.failed += 1;
    const message = caught instanceof Error ? caught.message : "Could not report the call";
    if (!report.errors.includes(message)) report.errors.push(message);
    return false;
  }
}

/** Kept for the audit trail alongside the import reference. */
export { importRefFor };
