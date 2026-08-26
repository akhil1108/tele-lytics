import AsyncStorage from "@react-native-async-storage/async-storage";
import * as FileSystem from "expo-file-system";
import { Platform } from "react-native";

import { api } from "./api";
import {
  fileNameFromUri,
  importRefFor,
  isAudioFile,
  mimeTypeFor,
  parseRecordingFileName,
  type ParsedRecording,
} from "./callRecordings";
import { uploadQueue } from "./uploadQueue";

/**
 * Importing the recordings the phone's own dialler already made.
 *
 * This is the primary path on Android: the agent turns on call recording in
 * their phone app, and this module watches the folder those recordings land in
 * and feeds them to the pipeline.
 *
 * Two things make it safe to run repeatedly:
 *
 * * **A ledger.** Every filename that has been imported is remembered, so a
 *   re-scan never uploads the same call twice — the server's `external_ref`
 *   idempotency is a second net, not the only one.
 * * **No guessing.** A file whose number could not be read is surfaced for the
 *   agent to label rather than being filed against a wrong customer.
 *
 * Folder access uses the Storage Access Framework: the agent grants the
 * recordings folder once, and the grant persists across restarts. This is the
 * route that works on Android 11+ without the `MANAGE_EXTERNAL_STORAGE`
 * permission, which Play will not approve for an app like this.
 */

const FOLDER_KEY = "call_analytics_recording_folder";
const LEDGER_KEY = "call_analytics_imported_files";
const DEFAULT_DIRECTION_KEY = "call_analytics_default_direction";

/** Bounded so the ledger cannot grow without limit on a long-lived handset. */
const LEDGER_LIMIT = 5_000;

export interface DetectedRecording {
  uri: string;
  fileName: string;
  parsed: ParsedRecording;
  sizeBytes: number | null;
  /** Set when the file cannot be imported without the agent's help. */
  needsNumber: boolean;
}

export interface ScanResult {
  folderUri: string;
  detected: DetectedRecording[];
  skippedAlreadyImported: number;
  skippedNotAudio: number;
}

export const recordingFolder = {
  async get(): Promise<string | null> {
    return AsyncStorage.getItem(FOLDER_KEY);
  },
  async set(uri: string): Promise<void> {
    await AsyncStorage.setItem(FOLDER_KEY, uri);
  },
  async clear(): Promise<void> {
    await AsyncStorage.removeItem(FOLDER_KEY);
  },
};

/**
 * Ask for a folder. `initialFolder` seeds the picker at a manufacturer's usual
 * location so the agent is not hunting through storage.
 */
export async function chooseRecordingFolder(initialFolder?: string): Promise<string | null> {
  if (Platform.OS !== "android") return null;

  const initialUri = initialFolder
    ? FileSystem.StorageAccessFramework.getUriForDirectoryInRoot(initialFolder)
    : undefined;

  const permission =
    await FileSystem.StorageAccessFramework.requestDirectoryPermissionsAsync(initialUri);
  if (!permission.granted) return null;

  await recordingFolder.set(permission.directoryUri);
  return permission.directoryUri;
}

// ------------------------------------------------------------------ ledger

async function readLedger(): Promise<string[]> {
  try {
    const raw = await AsyncStorage.getItem(LEDGER_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

async function writeLedger(entries: string[]): Promise<void> {
  // Newest kept: an old recording that has already been deleted from the phone
  // will never be offered again anyway.
  const trimmed = entries.slice(-LEDGER_LIMIT);
  await AsyncStorage.setItem(LEDGER_KEY, JSON.stringify(trimmed));
}

export async function markImported(fileNames: string[]): Promise<void> {
  const ledger = await readLedger();
  const merged = new Set(ledger);
  for (const name of fileNames) merged.add(name);
  await writeLedger([...merged]);
}

export async function importedCount(): Promise<number> {
  return (await readLedger()).length;
}

/** Offer everything again — for when a scan filed calls against the wrong numbers. */
export async function resetLedger(): Promise<void> {
  await AsyncStorage.removeItem(LEDGER_KEY);
}

// ------------------------------------------------------------------- scan

export async function scanRecordingFolder(): Promise<ScanResult | null> {
  const folderUri = await recordingFolder.get();
  if (!folderUri) return null;

  let uris: string[];
  try {
    uris = await FileSystem.StorageAccessFramework.readDirectoryAsync(folderUri);
  } catch {
    // The grant is revoked if the folder is deleted or storage is remounted.
    await recordingFolder.clear();
    throw new Error(
      "Access to the recordings folder was lost. Choose it again in Settings.",
    );
  }

  const ledger = new Set(await readLedger());
  const detected: DetectedRecording[] = [];
  let skippedAlreadyImported = 0;
  let skippedNotAudio = 0;

  for (const uri of uris) {
    const fileName = fileNameFromUri(uri);
    if (!isAudioFile(fileName)) {
      skippedNotAudio += 1;
      continue;
    }
    if (ledger.has(fileName)) {
      skippedAlreadyImported += 1;
      continue;
    }

    const parsed = parseRecordingFileName(fileName);
    let sizeBytes: number | null = null;
    try {
      const info = await FileSystem.getInfoAsync(uri);
      sizeBytes = info.exists && !info.isDirectory ? info.size : null;
    } catch {
      /* size is a nicety; a file we cannot stat may still upload */
    }

    detected.push({
      uri,
      fileName,
      parsed,
      sizeBytes,
      needsNumber: parsed.customerNumber === null,
    });
  }

  // Oldest first, so a backlog is uploaded in the order the calls happened.
  detected.sort((a, b) => {
    const left = a.parsed.recordedAt?.getTime() ?? 0;
    const right = b.parsed.recordedAt?.getTime() ?? 0;
    return left - right;
  });

  return { folderUri, detected, skippedAlreadyImported, skippedNotAudio };
}

// ----------------------------------------------------------------- import

export interface ImportOutcome {
  fileName: string;
  ok: boolean;
  callId?: string;
  error?: string;
  /** True when the org's policy forbids ingesting this call at all. */
  refusedByPolicy?: boolean;
}

export const defaultDirection = {
  async get(): Promise<"inbound" | "outbound" | "unknown"> {
    const stored = await AsyncStorage.getItem(DEFAULT_DIRECTION_KEY);
    return stored === "inbound" || stored === "outbound" ? stored : "unknown";
  },
  async set(value: "inbound" | "outbound" | "unknown"): Promise<void> {
    await AsyncStorage.setItem(DEFAULT_DIRECTION_KEY, value);
  },
};

/**
 * Import one detected recording.
 *
 * `numberOverride` is what the agent typed for a file whose name did not carry
 * a number. The policy is consulted first: a customer who has opted out must
 * not have their call ingested, even though it is already sitting on the disk.
 */
export async function importRecording(
  item: DetectedRecording,
  options: {
    numberOverride?: string;
    deviceId: string;
    fallbackDirection: "inbound" | "outbound" | "unknown";
  },
): Promise<ImportOutcome> {
  const customerNumber = (options.numberOverride ?? item.parsed.customerNumber ?? "").trim();
  if (!customerNumber) {
    return { fileName: item.fileName, ok: false, error: "No customer number" };
  }

  const direction =
    item.parsed.direction === "unknown" ? options.fallbackDirection : item.parsed.direction;

  try {
    const decision = await api.recordingPolicy(customerNumber, direction);
    if (!decision.should_record) {
      return {
        fileName: item.fileName,
        ok: false,
        refusedByPolicy: true,
        error: decision.reason,
      };
    }

    // The filename's timestamp is when the call happened. Falling back to now
    // would put a backlog of old calls on today's dashboard.
    const startedAt = (item.parsed.recordedAt ?? new Date()).toISOString();

    const call = await api.logCall({
      // Derived from the filename, so a retry after a crash mid-import maps to
      // the same call rather than creating a second one. Hashed because the
      // server caps this field at 80 characters and OEM filenames are long.
      external_ref: importRefFor(options.deviceId, item.fileName),
      direction,
      customer_number: customerNumber,
      customer_name: item.parsed.contactName,
      started_at: startedAt,
      status: "completed",
      recording_expected: true,
      metadata: {
        source: "device_recording_import",
        original_filename: item.fileName,
        parse_pattern: item.parsed.pattern,
        parse_confidence: item.parsed.confidence,
        number_source: options.numberOverride ? "agent" : "filename",
        direction_source: item.parsed.direction === "unknown" ? "assumed" : "filename",
      },
    });

    // SAF content URIs cannot always be streamed by the upload layer, so the
    // file is copied into the app's cache first. The queue deletes that copy
    // once the server accepts it; the original in the recordings folder is
    // never touched — it is the agent's file, not ours.
    const localUri = await copyIntoCache(item);

    await uploadQueue.enqueue({
      callId: call.id,
      fileUri: localUri,
      mimeType: mimeTypeFor(item.fileName),
      fileName: item.fileName,
      durationSeconds: null,
      // Nothing in the file records that a consent announcement was made, and
      // asserting otherwise would put a false statement in a compliance record.
      consentCaptured: false,
      customerNumber,
      startedAt,
    });

    await markImported([item.fileName]);
    return { fileName: item.fileName, ok: true, callId: call.id };
  } catch (caught) {
    return {
      fileName: item.fileName,
      ok: false,
      error: caught instanceof Error ? caught.message : "Import failed",
    };
  }
}

async function copyIntoCache(item: DetectedRecording): Promise<string> {
  const target = `${FileSystem.cacheDirectory}imports/`;
  await FileSystem.makeDirectoryAsync(target, { intermediates: true }).catch(() => {});
  // Namespaced by a safe form of the original name so two calls cannot collide.
  const safeName = item.fileName.replace(/[^A-Za-z0-9._-]/g, "_");
  const destination = `${target}${Date.now()}-${safeName}`;
  await FileSystem.copyAsync({ from: item.uri, to: destination });
  return destination;
}

/**
 * Import a batch, stopping at nothing — one bad file must not block the rest.
 *
 * Each entry carries its own override so a number the agent typed is recorded
 * as coming from the agent. Folding the override into `parsed` instead would
 * make the audit trail claim the filename supplied it.
 */
export async function importAll(
  entries: { item: DetectedRecording; numberOverride?: string }[],
  options: { deviceId: string; fallbackDirection: "inbound" | "outbound" | "unknown" },
): Promise<ImportOutcome[]> {
  const outcomes: ImportOutcome[] = [];
  for (const entry of entries) {
    outcomes.push(
      await importRecording(entry.item, { ...options, numberOverride: entry.numberOverride }),
    );
  }
  return outcomes;
}
