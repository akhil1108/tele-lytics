import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { CallLogEntry, CallLogType } from "../../../modules/call-log";
import {
  buildContactIndex,
  followUpId,
  isUntracked,
  numberKey,
  pendingFollowUps,
  resolveName,
} from "../callInsights";
import { callPayload, prepareBatch, toCall } from "../callLogSync";

const BASE = new Date("2026-09-20T10:00:00Z").getTime();
const MINUTE = 60_000;
const CUSTOMER = "+919876543210";

let nextId = 1;
function entry(type: CallLogType, minutes: number, overrides: Partial<CallLogEntry> = {}): CallLogEntry {
  return {
    id: String(nextId++),
    number: CUSTOMER,
    timestamp: BASE + minutes * MINUTE,
    durationSeconds: type === "incoming" || type === "outgoing" ? 60 : 0,
    type,
    ...overrides,
  };
}

describe("number keys", () => {
  it("treats every way of writing the same number as one", () => {
    const key = numberKey("+91 98765 43210");
    assert.equal(numberKey("09876543210"), key);
    assert.equal(numberKey("9876543210"), key);
    assert.equal(numberKey("(987) 654-3210"), key);
  });

  it("keeps short numbers whole", () => {
    assert.equal(numberKey("12345"), "12345");
    assert.equal(numberKey(null), "");
  });
});

describe("caller names", () => {
  const contacts = buildContactIndex([
    { name: "Rohit Verma", phoneNumbers: [{ number: "098765 43210" }] },
    { name: "  ", phoneNumbers: [{ number: "+919000000001" }] },
    { name: "Bank", phoneNumbers: [{ number: "121" }] },
  ]);

  it("prefers the agent's own contact name", () => {
    assert.deepEqual(resolveName(CUSTOMER, contacts, "TRUECALLER NAME"), {
      name: "Rohit Verma",
      source: "contact",
    });
  });

  it("falls back to the dialler's caller-ID name", () => {
    assert.deepEqual(resolveName("+919111111111", contacts, " Asha Traders "), {
      name: "Asha Traders",
      source: "caller_id",
    });
  });

  it("returns no name rather than guessing", () => {
    assert.deepEqual(resolveName("+919111111111", contacts, ""), { name: null, source: null });
  });

  it("ignores blank names and service codes", () => {
    assert.equal(contacts.size, 1);
  });
});

describe("tracking", () => {
  it("matches an untracked number however it is written", () => {
    const untracked = new Set([numberKey("09876543210")]);
    assert.equal(isUntracked(CUSTOMER, untracked), true);
    assert.equal(isUntracked("+919000000001", untracked), false);
  });

  it("never reports a call with an untracked number", () => {
    const calls = [entry("incoming", 0), entry("outgoing", 5, { number: "+919000000001" })];
    const batch = prepareBatch(calls, new Set(), new Set([numberKey(CUSTOMER)]));
    assert.equal(batch.calls.length, 1);
    assert.equal(batch.calls[0].number, "+919000000001");
    assert.deepEqual(batch.untrackedIds, [calls[0].id]);
  });
});

describe("the caller name travels with the call", () => {
  it("sends the name and where it came from", () => {
    const call = toCall(entry("incoming", 0, { name: "Asha Traders" }));
    assert.equal(call.cachedName, "Asha Traders");
    const body = callPayload(call, {
      deviceId: "69b367f1-5cbe-4c27-b0e3-bb211c1e8b92",
      hasRecording: false,
      deviceCanRecord: false,
      customerName: "Asha Traders",
      nameSource: "caller_id",
    });
    assert.equal(body.customer_name, "Asha Traders");
    assert.equal((body.metadata as Record<string, unknown>).name_source, "caller_id");
  });

  it("sends no name when there is none", () => {
    const body = callPayload(toCall(entry("incoming", 0)), {
      deviceId: "69b367f1",
      hasRecording: false,
      deviceCanRecord: false,
    });
    assert.equal(body.customer_name, null);
    assert.equal("name_source" in (body.metadata as Record<string, unknown>), false);
  });
});

describe("missed-call follow-ups", () => {
  it("lists a missed call nobody has returned", () => {
    const [followUp] = pendingFollowUps([entry("missed", 0)]);
    assert.equal(followUp.number, CUSTOMER);
    assert.equal(followUp.missedCount, 1);
    assert.equal(followUp.lastAttemptAt, null);
  });

  it("is settled by a connected call back", () => {
    assert.equal(pendingFollowUps([entry("missed", 0), entry("outgoing", 10)]).length, 0);
  });

  it("is settled when the customer gets through on a later try", () => {
    assert.equal(pendingFollowUps([entry("missed", 0), entry("incoming", 10)]).length, 0);
  });

  it("stays open when the call back was not answered, but notes the attempt", () => {
    const [followUp] = pendingFollowUps([
      entry("missed", 0),
      entry("outgoing", 10, { durationSeconds: 0 }),
    ]);
    assert.equal(followUp.lastAttemptAt?.getTime(), BASE + 10 * MINUTE);
  });

  it("collapses repeated missed calls from one number", () => {
    const first = entry("missed", 0);
    const second = entry("missed", 5);
    const [followUp] = pendingFollowUps([second, first]);
    assert.equal(followUp.missedCount, 2);
    assert.equal(followUp.lastMissedId, second.id);
  });

  it("reopens after a new missed call even if the old one was talked about", () => {
    const followUps = pendingFollowUps([
      entry("missed", 0),
      entry("incoming", 5),
      entry("missed", 30),
    ]);
    assert.equal(followUps.length, 1);
    assert.equal(followUps[0].missedCount, 1);
  });

  it("hides a dismissed follow-up until the number misses again", () => {
    const first = entry("missed", 0);
    const [open] = pendingFollowUps([first]);
    const dismissed = new Set([followUpId(open)]);
    assert.equal(pendingFollowUps([first], { dismissed }).length, 0);
    assert.equal(pendingFollowUps([first, entry("missed", 20)], { dismissed }).length, 1);
  });

  it("leaves out untracked numbers", () => {
    const untracked = new Set([numberKey(CUSTOMER)]);
    assert.equal(pendingFollowUps([entry("missed", 0)], { untracked }).length, 0);
  });

  it("names the caller and lists the newest first", () => {
    const contacts = buildContactIndex([
      { name: "Rohit Verma", phoneNumbers: [{ number: CUSTOMER }] },
    ]);
    const followUps = pendingFollowUps(
      [
        entry("missed", 0),
        entry("missed", 10, { number: "+919000000001", name: "Asha Traders" }),
      ],
      { contacts },
    );
    assert.deepEqual(
      followUps.map((item) => [item.name, item.nameSource]),
      [
        ["Asha Traders", "caller_id"],
        ["Rohit Verma", "contact"],
      ],
    );
  });

  it("ignores withheld numbers", () => {
    assert.equal(pendingFollowUps([entry("missed", 0, { number: "" })]).length, 0);
  });
});
