import * as Contacts from "expo-contacts";

import { buildContactIndex } from "./callInsights";

/**
 * The agent's address book, indexed by number for caller-name lookups.
 *
 * Read on the handset only — names are sent with a call so the dashboard can
 * show who it was with, but the address book itself never leaves the phone.
 */

/** Long enough that a sync does not re-read thousands of contacts each run. */
const CACHE_MS = 10 * 60 * 1000;

let cached: { index: Map<string, string>; at: number } | null = null;

export async function hasPermission(): Promise<boolean> {
  try {
    return (await Contacts.getPermissionsAsync()).granted;
  } catch {
    return false;
  }
}

export async function requestPermission(): Promise<boolean> {
  try {
    const result = await Contacts.requestPermissionsAsync();
    if (result.granted) cached = null;
    return result.granted;
  } catch {
    return false;
  }
}

/** Empty, not an error, without permission: names then come from caller ID. */
export async function contactIndex(): Promise<Map<string, string>> {
  if (cached && Date.now() - cached.at < CACHE_MS) return cached.index;
  if (!(await hasPermission())) return new Map();

  try {
    const { data } = await Contacts.getContactsAsync({
      fields: [Contacts.Fields.Name, Contacts.Fields.PhoneNumbers],
    });
    cached = { index: buildContactIndex(data), at: Date.now() };
    return cached.index;
  } catch {
    return new Map();
  }
}
