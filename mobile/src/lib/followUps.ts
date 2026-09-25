import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";

import * as CallLog from "../../modules/call-log";
import {
  followUpId,
  isUntracked,
  pendingFollowUps,
  resolveName,
  type FollowUp,
  type NameSource,
} from "./callInsights";
import { contactIndex } from "./contacts";
import { untrackedNumbers } from "./untracked";

/**
 * The agent's own recent calls, read straight from the phone's call log.
 *
 * This is deliberately local. It works offline, it includes calls the agent
 * chose not to track (so they can change their mind), and a missed call shows
 * up the moment it happens rather than after the next sync.
 */

/** How far back the Calls tab and missed-call follow-ups reach. */
export const RECENT_WINDOW_DAYS = 7;

const DISMISSED_KEY = "call_analytics_dismissed_follow_ups";
const DISMISSED_LIMIT = 500;

export interface RecentCall {
  id: string;
  number: string;
  name: string | null;
  nameSource: NameSource | null;
  type: CallLog.CallLogType;
  startedAt: Date;
  durationSeconds: number;
  untracked: boolean;
}

export function isSupported(): boolean {
  return Platform.OS === "android" && CallLog.isAvailable() && CallLog.hasPermission();
}

async function readWindow(): Promise<CallLog.CallLogEntry[]> {
  if (!isSupported()) return [];
  const since = Date.now() - RECENT_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  return CallLog.getEntries(since, 1000);
}

/** Newest first, with names resolved and the agent's tracking choice applied. */
export async function recentCalls(): Promise<RecentCall[]> {
  const [entries, contacts, untracked] = await Promise.all([
    readWindow(),
    contactIndex(),
    untrackedNumbers.keys(),
  ]);

  return entries
    .map((entry) => {
      const resolved = resolveName(entry.number, contacts, entry.name);
      return {
        id: entry.id,
        number: entry.number,
        name: resolved.name,
        nameSource: resolved.source,
        type: entry.type,
        startedAt: new Date(entry.timestamp),
        durationSeconds: entry.durationSeconds,
        untracked: isUntracked(entry.number, untracked),
      };
    })
    .sort((a, b) => b.startedAt.getTime() - a.startedAt.getTime());
}

// --------------------------------------------------------------- dismissals

async function readDismissed(): Promise<string[]> {
  try {
    const raw = await AsyncStorage.getItem(DISMISSED_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

/** "Done" on a follow-up the call log cannot settle — e.g. handled on WhatsApp. */
export async function dismissFollowUp(followUp: FollowUp): Promise<void> {
  const list = await readDismissed();
  list.push(followUpId(followUp));
  await AsyncStorage.setItem(DISMISSED_KEY, JSON.stringify(list.slice(-DISMISSED_LIMIT)));
}

/** Missed calls still waiting for a call back, newest first. */
export async function followUps(): Promise<FollowUp[]> {
  const [entries, contacts, untracked, dismissed] = await Promise.all([
    readWindow(),
    contactIndex(),
    untrackedNumbers.keys(),
    readDismissed(),
  ]);
  return pendingFollowUps(entries, { contacts, untracked, dismissed: new Set(dismissed) });
}
