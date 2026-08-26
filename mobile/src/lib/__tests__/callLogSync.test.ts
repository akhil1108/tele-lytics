import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { CallLogEntry, CallLogType } from "../../../modules/call-log";
import {
  MATCH_WINDOW_MS,
  callPayload,
  directionFor,
  matchRecordingsToCalls,
  newestTimestamp,
  noAudioReason,
  prepareBatch,
  sameNumber,
  toCall,
  type MatchCandidate,
} from "../callLogSync";
import { parseRecordingFileName } from "../callRecordings";

const BASE = new Date("2026-08-26T10:00:00Z").getTime();
const DEVICE = "69b367f1-5cbe-4c27-b0e3-bb211c1e8b92";

function entry(overrides: Partial<CallLogEntry> = {}): CallLogEntry {
  return {
    id: "1",
    number: "+919876543210",
    timestamp: BASE,
    durationSeconds: 120,
    type: "outgoing" as CallLogType,
    ...overrides,
  };
}

function recording(fileName: string): MatchCandidate {
  return { fileName, parsed: parseRecordingFileName(fileName) };
}

describe("reading the call log", () => {
  it("maps call types to a direction", () => {
    assert.equal(directionFor("outgoing"), "outbound");
    assert.equal(directionFor("incoming"), "inbound");
    // A missed call is one somebody tried to make to the agent.
    assert.equal(directionFor("missed"), "inbound");
    assert.equal(directionFor("voicemail"), "unknown");
  });

  it("gives a missed call no talk time", () => {
    const call = toCall(entry({ type: "missed", durationSeconds: 0 }));
    assert.equal(call.durationSeconds, 0);
    assert.equal(call.status, "missed");
    assert.equal(call.endedAt?.getTime(), call.startedAt.getTime());
  });

  it("derives the end from the start plus duration", () => {
    const call = toCall(entry({ durationSeconds: 185 }));
    assert.equal((call.endedAt!.getTime() - call.startedAt.getTime()) / 1000, 185);
  });

  it("skips entries that are not calls the agent handled", () => {
    const batch = prepareBatch(
      [
        entry({ id: "a", type: "outgoing" }),
        entry({ id: "b", type: "voicemail" }),
        entry({ id: "c", type: "blocked" }),
        entry({ id: "d", type: "rejected" }),
        entry({ id: "e", type: "incoming" }),
      ],
      new Set(),
    );
    assert.equal(batch.calls.length, 2);
    assert.equal(batch.skippedUnreportable, 3);
  });

  it("skips withheld and private numbers", () => {
    const batch = prepareBatch(
      [entry({ id: "a", number: "" }), entry({ id: "b", number: "Private" })],
      new Set(),
    );
    assert.equal(batch.calls.length, 0);
    assert.equal(batch.skippedNoNumber, 2);
  });

  it("does not re-sync an entry already sent", () => {
    const batch = prepareBatch([entry({ id: "a" }), entry({ id: "b" })], new Set(["a"]));
    assert.deepEqual(batch.calls.map((call) => call.logId), ["b"]);
  });

  it("returns a batch oldest first", () => {
    const batch = prepareBatch(
      [
        entry({ id: "late", timestamp: BASE + 60_000 }),
        entry({ id: "early", timestamp: BASE }),
      ],
      new Set(),
    );
    assert.deepEqual(batch.calls.map((call) => call.logId), ["early", "late"]);
  });

  it("advances the cursor to the newest entry seen", () => {
    const newest = newestTimestamp(
      [entry({ timestamp: BASE }), entry({ timestamp: BASE + 5_000 })],
      0,
    );
    assert.equal(newest, BASE + 5_000);
    // An empty batch must not rewind the cursor.
    assert.equal(newestTimestamp([], BASE), BASE);
  });
});

describe("comparing numbers across formats", () => {
  it("matches the same number written differently", () => {
    assert.equal(sameNumber("+919876543210", "9876543210"), true);
    assert.equal(sameNumber("09876543210", "+91 98765 43210"), true);
    assert.equal(sameNumber("+919876543210", "919876543210"), true);
  });

  it("does not match different numbers", () => {
    assert.equal(sameNumber("+919876543210", "+919876543211"), false);
    assert.equal(sameNumber("9876543210", "1234567890"), false);
  });

  it("refuses to match when either side is unusable", () => {
    assert.equal(sameNumber("", "9876543210"), false);
    assert.equal(sameNumber("Private", "9876543210"), false);
  });
});

describe("pairing recordings with calls", () => {
  it("attaches a recording made at the same moment", () => {
    const calls = [toCall(entry({ id: "a", number: "+919876543210", timestamp: BASE }))];
    const files = [recording("Call recording 9876543210_260826_100000.m4a")];

    const result = matchRecordingsToCalls(calls, files);
    assert.equal(result.matched.length, 1);
    assert.equal(result.matched[0].call.logId, "a");
    assert.equal(result.unmatchedCalls.length, 0);
  });

  it("leaves a call unmatched when no recording is close enough", () => {
    const calls = [toCall(entry({ id: "a", timestamp: BASE }))];
    // Same number, but four hours away — a different call entirely.
    const files = [recording("Call recording 9876543210_260826_140000.m4a")];

    const result = matchRecordingsToCalls(calls, files);
    assert.equal(result.matched.length, 0);
    assert.equal(result.unmatchedCalls.length, 1);
    assert.equal(result.unmatchedRecordings.length, 1);
  });

  it("gives a recording to the nearer of two calls to the same number", () => {
    // Two calls to one customer, twenty minutes apart. The recording is stamped
    // at the second, and must not be filed against the first.
    const calls = [
      toCall(entry({ id: "first", number: "+919876543210", timestamp: BASE })),
      toCall(entry({ id: "second", number: "+919876543210", timestamp: BASE + 20 * 60_000 })),
    ];
    const files = [recording("Call recording 9876543210_260826_102000.m4a")];

    const result = matchRecordingsToCalls(calls, files);
    assert.equal(result.matched.length, 1);
    assert.equal(result.matched[0].call.logId, "second");
    assert.deepEqual(result.unmatchedCalls.map((call) => call.logId), ["first"]);
  });

  it("never gives one recording to two calls", () => {
    const calls = [
      toCall(entry({ id: "first", number: "+919876543210", timestamp: BASE })),
      toCall(entry({ id: "second", number: "+919876543210", timestamp: BASE + 30_000 })),
    ];
    const files = [recording("Call recording 9876543210_260826_100000.m4a")];

    const result = matchRecordingsToCalls(calls, files);
    assert.equal(result.matched.length, 1);
    assert.equal(result.unmatchedCalls.length, 1);
  });

  it("does not attach a recording belonging to a different customer", () => {
    const calls = [toCall(entry({ id: "a", number: "+919876543210", timestamp: BASE }))];
    const files = [recording("Call recording 9000000001_260826_100000.m4a")];

    const result = matchRecordingsToCalls(calls, files);
    assert.equal(result.matched.length, 0);
    assert.equal(result.unmatchedRecordings.length, 1);
  });

  it("tolerates a recorder that stamps the file when the call ends", () => {
    // A two-minute call stamped at finalisation still lands inside the window.
    const calls = [
      toCall(entry({ id: "a", number: "+919876543210", timestamp: BASE, durationSeconds: 120 })),
    ];
    const files = [recording("Call recording 9876543210_260826_100200.m4a")];

    const result = matchRecordingsToCalls(calls, files);
    assert.equal(result.matched.length, 1);
  });

  it("ignores a recording whose filename carried no time", () => {
    const calls = [toCall(entry({ id: "a", number: "+919876543210", timestamp: BASE }))];
    const files = [recording("9876543210.amr")];

    const result = matchRecordingsToCalls(calls, files);
    assert.equal(result.matched.length, 0);
    assert.equal(result.unmatchedRecordings.length, 1);
  });

  it("keeps the window at three minutes", () => {
    const calls = [toCall(entry({ id: "a", number: "+919876543210", timestamp: BASE }))];
    const inside = [{ fileName: "x", parsed: { ...recording("x.m4a").parsed,
      customerNumber: "9876543210", recordedAt: new Date(BASE + MATCH_WINDOW_MS - 1_000) } }];
    const outside = [{ fileName: "y", parsed: { ...recording("y.m4a").parsed,
      customerNumber: "9876543210", recordedAt: new Date(BASE + MATCH_WINDOW_MS + 1_000) } }];

    assert.equal(matchRecordingsToCalls(calls, inside).matched.length, 1);
    assert.equal(matchRecordingsToCalls(calls, outside).matched.length, 0);
  });
});

describe("what gets sent to the server", () => {
  it("marks a metadata-only call as not expecting a recording", () => {
    const call = toCall(entry({ id: "a", durationSeconds: 95 }));
    const payload = callPayload(call, {
      deviceId: DEVICE,
      hasRecording: false,
      deviceCanRecord: false,
    });

    assert.equal(payload.recording_expected, false);
    // Coverage measures whether the pipeline worked, so a call that was never
    // going to be recorded must not drag it down.
    assert.equal(payload.recording_skipped_reason, "device_cannot_record");
    assert.equal(payload.duration_seconds, 95);
    assert.equal(payload.direction, "outbound");
  });

  it("distinguishes a phone that cannot record from a missing file", () => {
    const call = toCall(entry({ id: "a" }));
    assert.equal(noAudioReason(call, true), "no_recording_on_device");
    assert.equal(noAudioReason(call, false), "device_cannot_record");
  });

  it("explains a missed call as unanswered rather than unrecorded", () => {
    const missed = toCall(entry({ id: "a", type: "missed", durationSeconds: 0 }));
    assert.equal(noAudioReason(missed, true), "call_not_answered");
  });

  it("records that the direction came from the log, not a guess", () => {
    const payload = callPayload(toCall(entry({ id: "a" })), {
      deviceId: DEVICE,
      hasRecording: true,
      deviceCanRecord: true,
      originalFilename: "Call recording 9876543210_260826_100000.m4a",
    });
    const metadata = payload.metadata as Record<string, unknown>;

    assert.equal(metadata.direction_source, "call_log");
    assert.equal(metadata.source, "call_log_with_recording");
    assert.equal(metadata.original_filename, "Call recording 9876543210_260826_100000.m4a");
  });

  it("keeps external_ref inside the server's 80-character limit", () => {
    const payload = callPayload(toCall(entry({ id: "999999999" })), {
      deviceId: DEVICE,
      hasRecording: false,
      deviceCanRecord: true,
    });
    assert.ok(String(payload.external_ref).length <= 80);
  });

  it("gives the same call the same reference every sync", () => {
    const call = toCall(entry({ id: "42" }));
    const options = { deviceId: DEVICE, hasRecording: false, deviceCanRecord: true };
    assert.equal(
      callPayload(call, options).external_ref,
      callPayload(call, options).external_ref,
    );
  });
});
