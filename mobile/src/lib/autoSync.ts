import * as BackgroundFetch from "expo-background-fetch";
import * as TaskManager from "expo-task-manager";
import { Platform } from "react-native";

import { credentials } from "./api";
import { hasPermission as hasCallLogPermission, syncCallLog, type SyncReport } from "./callLogService";
import { followUps } from "./followUps";
import { notifyFollowUps } from "./notifications";
import { uploadQueue } from "./uploadQueue";

/**
 * One sync pass: report new calls, remind about missed ones, push uploads.
 *
 * The same pass runs when the agent opens or refreshes the app and, every
 * fifteen minutes or so, in the background — so calls reach the dashboard and
 * missed-call reminders arrive without anybody remembering to open the app.
 */

export const BACKGROUND_TASK = "tele-lytics-call-sync";

/** Android's floor for background fetch; it may run later, never sooner. */
const INTERVAL_SECONDS = 15 * 60;

export interface CycleResult {
  sync: SyncReport | null;
  notified: number;
}

let running: Promise<CycleResult> | null = null;

export function runSyncCycle(deviceId: string): Promise<CycleResult> {
  // The foreground refresh and the background task can land together; two
  // passes over the same log would race on the ledger.
  running ??= (async () => {
    try {
      let sync: SyncReport | null = null;
      if (Platform.OS === "android" && hasCallLogPermission()) {
        sync = await syncCallLog(deviceId);
      }

      let notified = 0;
      try {
        notified = await notifyFollowUps(await followUps());
      } catch {
        /* a reminder failing must not fail the sync */
      }

      await uploadQueue.load();
      await uploadQueue.drain();
      return { sync, notified };
    } finally {
      running = null;
    }
  })();
  return running;
}

// Must be defined at module scope: Android starts the JS runtime headless and
// looks the task up by name before any screen mounts.
TaskManager.defineTask(BACKGROUND_TASK, async () => {
  try {
    const session = await credentials.session();
    if (!session) return BackgroundFetch.BackgroundFetchResult.NoData;
    const result = await runSyncCycle(session.device_id);
    const changed = (result.sync?.reported ?? 0) > 0 || result.notified > 0;
    return changed
      ? BackgroundFetch.BackgroundFetchResult.NewData
      : BackgroundFetch.BackgroundFetchResult.NoData;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerBackgroundSync(): Promise<boolean> {
  if (Platform.OS !== "android") return false;
  try {
    const status = await BackgroundFetch.getStatusAsync();
    if (status !== BackgroundFetch.BackgroundFetchStatus.Available) return false;
    if (!(await TaskManager.isTaskRegisteredAsync(BACKGROUND_TASK))) {
      await BackgroundFetch.registerTaskAsync(BACKGROUND_TASK, {
        minimumInterval: INTERVAL_SECONDS,
        // Keep syncing after the agent swipes the app away and after a reboot.
        stopOnTerminate: false,
        startOnBoot: true,
      });
    }
    return true;
  } catch {
    return false;
  }
}

export async function unregisterBackgroundSync(): Promise<void> {
  try {
    if (await TaskManager.isTaskRegisteredAsync(BACKGROUND_TASK)) {
      await BackgroundFetch.unregisterTaskAsync(BACKGROUND_TASK);
    }
  } catch {
    /* nothing registered */
  }
}
