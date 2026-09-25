import AsyncStorage from "@react-native-async-storage/async-storage";

import { numberKey } from "./callInsights";

/**
 * Numbers the agent has chosen not to track.
 *
 * Kept on the handset only. Telling the server "this number is private" would
 * itself be a record of the private number, which is what the agent asked us
 * not to make.
 */

const KEY = "call_analytics_untracked_numbers";

export interface UntrackedNumber {
  key: string;
  number: string;
  name: string | null;
  addedAt: number;
}

type Listener = (list: UntrackedNumber[]) => void;
const listeners = new Set<Listener>();

async function read(): Promise<UntrackedNumber[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as UntrackedNumber[]) : [];
  } catch {
    return [];
  }
}

async function write(list: UntrackedNumber[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(list));
  for (const listener of listeners) listener(list);
}

export const untrackedNumbers = {
  list: read,

  async keys(): Promise<Set<string>> {
    return new Set((await read()).map((entry) => entry.key));
  },

  async add(number: string, name: string | null): Promise<void> {
    const key = numberKey(number);
    if (!key) return;
    const list = await read();
    if (list.some((entry) => entry.key === key)) return;
    await write([...list, { key, number, name, addedAt: Date.now() }]);
  },

  async remove(number: string): Promise<void> {
    const key = numberKey(number);
    await write((await read()).filter((entry) => entry.key !== key));
  },

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    void read().then(listener);
    return () => listeners.delete(listener);
  },
};
