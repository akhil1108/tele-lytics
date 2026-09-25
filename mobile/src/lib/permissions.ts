import { Platform } from "react-native";

import {
  callLogEnabled,
  hasPermission as hasCallLogPermission,
  isSupported as callLogSupported,
  requestPermission as requestCallLogPermission,
} from "./callLogService";
import * as contacts from "./contacts";
import { recordingFolder } from "./importer";
import * as notifications from "./notifications";
import { CallRecorder } from "./recorder";

/**
 * Everything the app needs from the phone, in one place.
 *
 * The setup screen and the home screen's "finish setup" prompt both read this,
 * so the two can never disagree about what is still missing.
 */

export type PermissionId = "callLog" | "contacts" | "microphone" | "notifications" | "folder";

export interface PermissionState {
  id: PermissionId;
  title: string;
  why: string;
  granted: boolean;
  /** Optional ones do not block "setup complete". */
  optional: boolean;
}

const COPY: Record<PermissionId, { title: string; why: string; optional: boolean }> = {
  callLog: {
    title: "Call log",
    why: "Reports every call you make or take, and spots missed calls to follow up.",
    optional: false,
  },
  contacts: {
    title: "Contacts",
    why: "Shows who called. Unsaved numbers use the caller ID name from your dialler (e.g. Truecaller).",
    optional: false,
  },
  notifications: {
    title: "Notifications",
    why: "Reminds you to call back when you miss a call.",
    optional: false,
  },
  microphone: {
    title: "Microphone",
    why: "Records a call inside the app when your phone's dialler cannot.",
    optional: false,
  },
  folder: {
    title: "Call recordings folder",
    why: "Lets the app pick up recordings your dialler saves and upload them for analysis.",
    optional: true,
  },
};

function state(id: PermissionId, granted: boolean): PermissionState {
  return { id, granted, ...COPY[id] };
}

/** Only what applies on this phone: iOS has no call log or recordings folder. */
export async function permissionStatus(): Promise<PermissionState[]> {
  const android = Platform.OS === "android" && callLogSupported();
  const [contactsOk, notificationsOk, micOk, folder] = await Promise.all([
    contacts.hasPermission(),
    notifications.hasPermission(),
    CallRecorder.hasPermission(),
    recordingFolder.get(),
  ]);

  return [
    ...(android ? [state("callLog", hasCallLogPermission())] : []),
    state("contacts", contactsOk),
    state("notifications", notificationsOk),
    state("microphone", micOk),
    ...(android ? [state("folder", Boolean(folder))] : []),
  ];
}

/** Request one permission. The folder is chosen on the setup screen instead. */
export async function requestOne(id: Exclude<PermissionId, "folder">): Promise<boolean> {
  switch (id) {
    case "callLog": {
      const granted = await requestCallLogPermission();
      if (granted) await callLogEnabled.set(true);
      return granted;
    }
    case "contacts":
      return contacts.requestPermission();
    case "notifications":
      return notifications.requestPermission();
    case "microphone":
      return CallRecorder.requestPermission();
  }
}

/** Ask for every missing system permission, one dialog after another. */
export async function requestAll(): Promise<PermissionState[]> {
  for (const item of await permissionStatus()) {
    if (!item.granted && item.id !== "folder") await requestOne(item.id);
  }
  return permissionStatus();
}

export function setupComplete(states: PermissionState[]): boolean {
  return states.every((item) => item.granted || item.optional);
}
