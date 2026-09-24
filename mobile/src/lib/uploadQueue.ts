import AsyncStorage from "@react-native-async-storage/async-storage";
import NetInfo from "@react-native-community/netinfo";
import * as FileSystem from "expo-file-system";

import { ApiError, api } from "./api";
import { MAX_UPLOAD_ATTEMPTS, RETRY_BACKOFF_MS } from "./config";
import type { PendingUpload } from "./types";

const QUEUE_KEY = "call_analytics_upload_queue";

/**
 * Durable upload queue.
 *
 * Agents work in lifts, basements and moving vehicles, so an upload failing is
 * the normal case rather than the exception. The queue is written to disk on
 * every change, so a recording survives the app being killed, and it drains on
 * its own the next time the handset has a connection.
 *
 * Ordering is oldest-first: if a day's recordings back up, the earliest call is
 * the one a supervisor is most likely to be waiting on.
 */
type Listener = (queue: PendingUpload[]) => void;

class UploadQueue {
  private queue: PendingUpload[] = [];
  private listeners = new Set<Listener>();
  private draining = false;
  private loaded = false;

  async load(): Promise<PendingUpload[]> {
    if (this.loaded) return this.queue;
    try {
      const raw = await AsyncStorage.getItem(QUEUE_KEY);
      this.queue = raw ? (JSON.parse(raw) as PendingUpload[]) : [];
    } catch {
      this.queue = [];
    }
    this.loaded = true;
    this.emit();
    return this.queue;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.queue);
    return () => this.listeners.delete(listener);
  }

  get items(): PendingUpload[] {
    return this.queue;
  }

  async enqueue(
    item: Omit<PendingUpload, "id" | "attempts" | "nextAttemptAt" | "lastError" | "createdAt">,
  ): Promise<PendingUpload> {
    await this.load();
    const entry: PendingUpload = {
      ...item,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      attempts: 0,
      nextAttemptAt: Date.now(),
      lastError: null,
      createdAt: Date.now(),
    };
    this.queue = [...this.queue, entry];
    await this.persist();
    void this.drain();
    return entry;
  }

  async remove(id: string, { deleteFile }: { deleteFile: boolean }): Promise<void> {
    const entry = this.queue.find((item) => item.id === id);
    this.queue = this.queue.filter((item) => item.id !== id);
    await this.persist();
    if (entry && deleteFile) {
      await FileSystem.deleteAsync(entry.fileUri, { idempotent: true }).catch(() => {});
    }
  }

  /** Clear the backoff so a user tapping "Retry" gets an immediate attempt. */
  async retryNow(id: string): Promise<void> {
    this.queue = this.queue.map((item) =>
      item.id === id ? { ...item, nextAttemptAt: 0, lastError: null } : item,
    );
    await this.persist();
    void this.drain();
  }

  async drain(): Promise<void> {
    if (this.draining) return;
    await this.load();

    const state = await NetInfo.fetch();
    if (!state.isConnected) return;

    this.draining = true;
    try {
      const now = Date.now();
      const due = [...this.queue]
        .filter((item) => item.nextAttemptAt <= now)
        .sort((a, b) => a.createdAt - b.createdAt);

      for (const item of due) {
        // Re-check: a later item may have been removed while we worked.
        if (!this.queue.some((entry) => entry.id === item.id)) continue;
        await this.attempt(item);
      }
    } finally {
      this.draining = false;
    }
  }

  private async attempt(item: PendingUpload): Promise<void> {
    // A file the OS cleaned up will never upload; drop it rather than retry
    // forever and keep the badge count permanently wrong.
    const info = await FileSystem.getInfoAsync(item.fileUri);
    if (!info.exists) {
      await this.fail(item, "The recording file is no longer on this device", true);
      return;
    }

    try {
      await api.uploadRecording(
        item.callId,
        { uri: item.fileUri, name: item.fileName, type: item.mimeType },
        { durationSeconds: item.durationSeconds, consentCaptured: item.consentCaptured },
      );
      await this.remove(item.id, { deleteFile: true });
    } catch (caught) {
      const error = caught instanceof ApiError ? caught : new ApiError(0, String(caught));
      // A rejected upload (bad audio type, unknown call) or an unpaired device
      // will fail identically every time — stop rather than loop.
      const permanent = !error.isRetryable || error.isAuthFailure;
      await this.fail(item, error.message, permanent);
    }
  }

  private async fail(item: PendingUpload, message: string, permanent: boolean): Promise<void> {
    const attempts = item.attempts + 1;
    const exhausted = permanent || attempts >= MAX_UPLOAD_ATTEMPTS;
    const backoff = RETRY_BACKOFF_MS[Math.min(attempts - 1, RETRY_BACKOFF_MS.length - 1)];

    this.queue = this.queue.map((entry) =>
      entry.id === item.id
        ? {
            ...entry,
            attempts,
            lastError: message,
            // An exhausted item stays in the list, visible and retryable by
            // hand: silently dropping a call recording is never right.
            nextAttemptAt: exhausted ? Number.MAX_SAFE_INTEGER : Date.now() + backoff,
          }
        : entry,
    );
    await this.persist();
  }

  private async persist(): Promise<void> {
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(this.queue));
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener(this.queue);
  }
}

export const uploadQueue = new UploadQueue();

/** Drain whenever the handset regains a connection. */
export function startQueueWatcher(): () => void {
  const unsubscribe = NetInfo.addEventListener((state) => {
    if (state.isConnected) void uploadQueue.drain();
  });
  const timer = setInterval(() => void uploadQueue.drain(), 60_000);
  return () => {
    unsubscribe();
    clearInterval(timer);
  };
}

export function isStuck(item: PendingUpload): boolean {
  return item.nextAttemptAt === Number.MAX_SAFE_INTEGER;
}
