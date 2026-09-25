import type { CallLogEntry } from "../../modules/call-log";

/**
 * What the agent sees about their own calls: who called, which calls still
 * need a call back, and which numbers they have chosen not to track.
 *
 * Pure — no React Native, no native module, no storage — so the rules are
 * tested directly in Node, the same way the recording matcher is.
 */

// ------------------------------------------------------------------ numbers

/**
 * A comparable key for a phone number: its last nine digits.
 *
 * The same number reaches the phone as `+91 98765 43210`, `09876543210` and
 * `9876543210` depending on who dialled and how the contact was saved. Nine
 * digits survives all of those without collapsing distinct local numbers.
 */
export function numberKey(number: string | null | undefined): string {
  const digits = (number ?? "").replace(/\D/g, "");
  return digits.length > 9 ? digits.slice(-9) : digits;
}

// -------------------------------------------------------------- caller name

export type NameSource = "contact" | "caller_id";

export interface ResolvedName {
  name: string | null;
  source: NameSource | null;
}

export interface ContactLike {
  name?: string | null;
  phoneNumbers?: { number?: string | null; digits?: string | null }[] | null;
}

/** Index the address book by number key, for lookups during a sync. */
export function buildContactIndex(contacts: ContactLike[]): Map<string, string> {
  const index = new Map<string, string>();
  for (const contact of contacts) {
    const name = contact.name?.trim();
    if (!name) continue;
    for (const phone of contact.phoneNumbers ?? []) {
      const key = numberKey(phone.digits || phone.number);
      // Six digits is the shortest number worth matching; shorter keys are
      // service codes that would collide across contacts.
      if (key.length >= 6 && !index.has(key)) index.set(key, name);
    }
  }
  return index;
}

/**
 * Who the caller is.
 *
 * The agent's own address book wins: it is the name they chose. After that,
 * the name the dialler cached in the call log — which is where a caller-ID app
 * such as Truecaller leaves its lookup when it is the phone's default dialler.
 */
export function resolveName(
  number: string,
  contacts: ReadonlyMap<string, string>,
  cachedName?: string | null,
): ResolvedName {
  const fromContacts = contacts.get(numberKey(number));
  if (fromContacts) return { name: fromContacts, source: "contact" };
  const cached = cachedName?.trim();
  if (cached) return { name: cached, source: "caller_id" };
  return { name: null, source: null };
}

// ---------------------------------------------------------------- tracking

/**
 * Numbers the agent has marked "don't track" — a family member, a personal
 * line. Calls with them are never reported and their recordings never leave
 * the phone.
 */
export function isUntracked(number: string, untracked: ReadonlySet<string>): boolean {
  const key = numberKey(number);
  return key.length > 0 && untracked.has(key);
}

// ---------------------------------------------------------------- follow-up

export interface FollowUp {
  key: string;
  number: string;
  name: string | null;
  nameSource: NameSource | null;
  /** Missed calls from this number since it was last spoken to. */
  missedCount: number;
  lastMissedAt: Date;
  /** Call-log id of the newest missed call; dismissals are pinned to it. */
  lastMissedId: string;
  /** An outgoing call to them that did not connect, if the agent has tried. */
  lastAttemptAt: Date | null;
}

/** The dismissal key: a new missed call from the same number reopens it. */
export function followUpId(followUp: Pick<FollowUp, "key" | "lastMissedId">): string {
  return `${followUp.key}:${followUp.lastMissedId}`;
}

/**
 * Missed calls that still need a call back.
 *
 * A missed call is settled by any later call with the same number that
 * actually connected, in either direction — the agent rang back, or the
 * customer tried again and got through. An outgoing call that did not connect
 * is an attempt, shown on the card, but it does not settle anything: the
 * customer still has not been spoken to.
 *
 * Several missed calls from one number collapse into one follow-up, because
 * one call back answers all of them.
 */
export function pendingFollowUps(
  entries: CallLogEntry[],
  options: {
    contacts?: ReadonlyMap<string, string>;
    untracked?: ReadonlySet<string>;
    dismissed?: ReadonlySet<string>;
  } = {},
): FollowUp[] {
  const contacts = options.contacts ?? new Map<string, string>();
  const untracked = options.untracked ?? new Set<string>();
  const dismissed = options.dismissed ?? new Set<string>();

  const open = new Map<string, FollowUp>();
  const ordered = [...entries].sort((a, b) => a.timestamp - b.timestamp);

  for (const entry of ordered) {
    const key = numberKey(entry.number);
    if (key.length < 6 || untracked.has(key)) continue;

    if (entry.type === "missed") {
      const existing = open.get(key);
      const resolved = resolveName(entry.number, contacts, entry.name);
      open.set(key, {
        key,
        number: entry.number,
        name: resolved.name ?? existing?.name ?? null,
        nameSource: resolved.source ?? existing?.nameSource ?? null,
        missedCount: (existing?.missedCount ?? 0) + 1,
        lastMissedAt: new Date(entry.timestamp),
        lastMissedId: entry.id,
        lastAttemptAt: existing?.lastAttemptAt ?? null,
      });
      continue;
    }

    const pending = open.get(key);
    if (!pending) continue;

    const connected =
      (entry.type === "incoming" || entry.type === "outgoing") && entry.durationSeconds > 0;
    if (connected) {
      open.delete(key);
    } else if (entry.type === "outgoing") {
      pending.lastAttemptAt = new Date(entry.timestamp);
    }
  }

  return [...open.values()]
    .filter((followUp) => !dismissed.has(followUpId(followUp)))
    .sort((a, b) => b.lastMissedAt.getTime() - a.lastMissedAt.getTime());
}
