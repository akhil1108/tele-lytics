import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { followUpId, type FollowUp } from "./callInsights";

/**
 * Missed-call reminders.
 *
 * One notification per missed caller, posted by the sync — whether the app is
 * open or the background task ran it. Tapping it opens the Calls tab.
 */

const CHANNEL_ID = "missed-calls";
const NOTIFIED_KEY = "call_analytics_notified_follow_ups";
const NOTIFIED_LIMIT = 500;

/**
 * Only fresh missed calls raise a notification. Without this, turning the
 * feature on would fire one for every missed call in the last week at once.
 */
const NOTIFY_WITHIN_MS = 2 * 60 * 60 * 1000;

let configured = false;

export async function configureNotifications(): Promise<void> {
  if (configured) return;
  configured = true;

  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
      name: "Missed calls",
      description: "Reminders to call back customers you missed",
      importance: Notifications.AndroidImportance.HIGH,
    });
  }
}

export async function hasPermission(): Promise<boolean> {
  try {
    return (await Notifications.getPermissionsAsync()).granted;
  } catch {
    return false;
  }
}

export async function requestPermission(): Promise<boolean> {
  try {
    await configureNotifications();
    return (await Notifications.requestPermissionsAsync()).granted;
  } catch {
    return false;
  }
}

async function readNotified(): Promise<string[]> {
  try {
    const raw = await AsyncStorage.getItem(NOTIFIED_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

/** Post a reminder for each follow-up not already notified. Returns how many. */
export async function notifyFollowUps(pending: FollowUp[]): Promise<number> {
  if (pending.length === 0 || !(await hasPermission())) return 0;
  await configureNotifications();

  const notified = await readNotified();
  const seen = new Set(notified);
  const cutoff = Date.now() - NOTIFY_WITHIN_MS;
  let posted = 0;

  for (const followUp of pending) {
    const id = followUpId(followUp);
    if (seen.has(id)) continue;
    seen.add(id);
    notified.push(id);
    if (followUp.lastMissedAt.getTime() < cutoff) continue;

    const who = followUp.name ?? followUp.number;
    await Notifications.scheduleNotificationAsync({
      content: {
        title: followUp.missedCount > 1 ? `${followUp.missedCount} missed calls` : "Missed call",
        body: `${who} — tap to call back`,
        data: { route: "/calls", number: followUp.number },
      },
      trigger: Platform.OS === "android" ? { channelId: CHANNEL_ID } : null,
    });
    posted += 1;
  }

  await AsyncStorage.setItem(NOTIFIED_KEY, JSON.stringify(notified.slice(-NOTIFIED_LIMIT)));
  return posted;
}
