import { requireOptionalNativeModule } from "expo-modules-core";

/**
 * Access to the Android system call log.
 *
 * The native side is optional on purpose. It does not exist in Expo Go or on
 * iOS, and the app has to keep working there — so every consumer checks
 * `isAvailable()` first and the platform degrades to whatever it does have,
 * rather than crashing on a missing module.
 */

export type CallLogType =
  | "incoming"
  | "outgoing"
  | "missed"
  | "rejected"
  | "blocked"
  | "voicemail"
  | "unknown";

export interface CallLogEntry {
  /** The provider's row id. Stable on a device, not across devices. */
  id: string;
  number: string;
  /** Epoch milliseconds when the call started. */
  timestamp: number;
  /** Connected seconds. Zero for missed, rejected and blocked calls. */
  durationSeconds: number;
  type: CallLogType;
}

interface CallLogNativeModule {
  isAvailable(): boolean;
  hasPermission(): boolean;
  getEntries(sinceEpochMs: number, limit: number): Promise<CallLogEntry[]>;
}

const native = requireOptionalNativeModule<CallLogNativeModule>("CallLog");

export function isAvailable(): boolean {
  try {
    return native?.isAvailable() ?? false;
  } catch {
    return false;
  }
}

export function hasPermission(): boolean {
  try {
    return native?.hasPermission() ?? false;
  } catch {
    return false;
  }
}

export async function getEntries(
  sinceEpochMs: number,
  limit = 500,
): Promise<CallLogEntry[]> {
  if (!native) return [];
  return native.getEntries(sinceEpochMs, limit);
}
