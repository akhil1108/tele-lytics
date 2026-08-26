/**
 * Filename shapes taken from what the common Android recorders actually write.
 *
 * Run with `npm test`. The module under test has no React Native imports, so
 * these run in plain Node — the point is that a handset nobody has is still
 * covered.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  fileNameFromUri,
  importRefFor,
  isAudioFile,
  mimeTypeFor,
  parseRecordingFileName,
} from "../callRecordings";

function at(date: Date | null): string | null {
  if (!date) return null;
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

describe("OEM recorder filenames", () => {
  it("reads Samsung's two-digit-year format", () => {
    const parsed = parseRecordingFileName("Call recording 9876543210_250826_143012.m4a");
    assert.equal(parsed.customerNumber, "9876543210");
    assert.equal(at(parsed.recordedAt), "2025-08-26 14:30:12");
    assert.equal(parsed.confidence, "high");
  });

  it("reads Samsung's contact-name variant, leaving the number for the agent", () => {
    const parsed = parseRecordingFileName("Call recording Rohit Verma_250826_143012.m4a");
    assert.equal(parsed.customerNumber, null);
    assert.equal(parsed.contactName, "Rohit Verma");
    assert.equal(at(parsed.recordedAt), "2025-08-26 14:30:12");
    // Enough to file, not enough to attribute — the agent must confirm.
    assert.equal(parsed.confidence, "medium");
  });

  it("reads Xiaomi's epoch-millis-first format", () => {
    const parsed = parseRecordingFileName("1756218612000_9876543210.mp3");
    assert.equal(parsed.customerNumber, "9876543210");
    assert.equal(parsed.recordedAt?.getFullYear(), 2025);
    assert.equal(parsed.pattern, "epoch");
  });

  it("reads Oppo/OnePlus compact datetime", () => {
    const parsed = parseRecordingFileName("Call@9876543210_20260826143012.amr");
    assert.equal(parsed.customerNumber, "9876543210");
    assert.equal(at(parsed.recordedAt), "2026-08-26 14:30:12");
  });

  it("reads Vivo's split date and time", () => {
    const parsed = parseRecordingFileName("9876543210_20260826_143012.wav");
    assert.equal(parsed.customerNumber, "9876543210");
    assert.equal(at(parsed.recordedAt), "2026-08-26 14:30:12");
  });

  it("reads the Google Phone app's ISO format with an E.164 number", () => {
    const parsed = parseRecordingFileName("+919876543210 2026-08-26 14:30:12.m4a");
    assert.equal(parsed.customerNumber, "+919876543210");
    assert.equal(at(parsed.recordedAt), "2026-08-26 14:30:12");
    assert.equal(parsed.pattern, "iso-date");
  });

  it("reads a third-party recorder's direction token", () => {
    const outgoing = parseRecordingFileName("20260826_143012_+919876543210_out.mp3");
    assert.equal(outgoing.direction, "outbound");
    assert.equal(outgoing.customerNumber, "+919876543210");

    const incoming = parseRecordingFileName("Call_+919876543210_20260826143012_in.amr");
    assert.equal(incoming.direction, "inbound");
  });

  it("reads Truecaller's prefixed format", () => {
    const parsed = parseRecordingFileName("Truecaller_9876543210_20260826_143012.m4a");
    assert.equal(parsed.customerNumber, "9876543210");
    assert.equal(at(parsed.recordedAt), "2026-08-26 14:30:12");
    // "Truecaller" is the recorder's own label, not somebody's name.
    assert.equal(parsed.contactName, null);
  });
});

describe("the ten-digit ambiguity", () => {
  it("treats a leading-1 ten-digit run as epoch seconds, not a number", () => {
    // 1756218612 is a real timestamp; no national mobile number starts with 1.
    const parsed = parseRecordingFileName("1756218612_9876543210.mp3");
    assert.equal(parsed.customerNumber, "9876543210");
    assert.equal(parsed.recordedAt?.getFullYear(), 2025);
  });

  it("treats a leading-9 ten-digit run as a number even when alone", () => {
    const parsed = parseRecordingFileName("9876543210.amr");
    assert.equal(parsed.customerNumber, "9876543210");
    assert.equal(parsed.recordedAt, null);
    assert.equal(parsed.confidence, "medium");
  });
});

describe("refusing to guess", () => {
  it("returns low confidence when nothing is readable", () => {
    const parsed = parseRecordingFileName("recording.m4a");
    assert.equal(parsed.customerNumber, null);
    assert.equal(parsed.recordedAt, null);
    assert.equal(parsed.confidence, "low");
  });

  it("rejects an impossible date rather than rolling it over", () => {
    // 2026-02-31 would silently become 3 March if handed to Date().
    const parsed = parseRecordingFileName("9876543210_20260231_143012.wav");
    assert.equal(parsed.recordedAt, null);
    assert.equal(parsed.customerNumber, "9876543210");
  });

  it("rejects a date outside the smartphone era", () => {
    const parsed = parseRecordingFileName("9876543210_19850826_143012.wav");
    assert.equal(parsed.recordedAt, null);
  });

  it("handles an empty stem without throwing", () => {
    assert.equal(parseRecordingFileName(".mp3").confidence, "low");
    assert.equal(parseRecordingFileName("").confidence, "low");
  });
});

describe("file helpers", () => {
  it("recognises the audio formats phone recorders emit", () => {
    for (const name of ["a.m4a", "a.mp3", "a.amr", "a.3gp", "a.wav", "a.awb", "a.opus"]) {
      assert.equal(isAudioFile(name), true, name);
    }
    for (const name of ["notes.txt", "photo.jpg", "archive.zip", "noextension"]) {
      assert.equal(isAudioFile(name), false, name);
    }
  });

  it("maps extensions to the MIME types the API accepts", () => {
    assert.equal(mimeTypeFor("call.m4a"), "audio/mp4");
    assert.equal(mimeTypeFor("call.amr"), "audio/amr");
    assert.equal(mimeTypeFor("call.wav"), "audio/wav");
    assert.equal(mimeTypeFor("call.3gp"), "audio/3gpp");
  });

  it("pulls the filename back out of a SAF document URI", () => {
    const uri =
      "content://com.android.externalstorage.documents/tree/primary%3ARecordings%2FCall/" +
      "document/primary%3ARecordings%2FCall%2FCall%20recording%209876543210_250826_143012.m4a";
    assert.equal(fileNameFromUri(uri), "Call recording 9876543210_250826_143012.m4a");
  });

  it("survives a malformed percent escape in a URI", () => {
    const name = fileNameFromUri("content://x/document/primary%3Abad%ZZname.mp3");
    assert.ok(name.endsWith(".mp3"));
  });

  it("keeps a clock time in the filename intact", () => {
    // The Google Phone app writes the time with colons. Splitting the URI on
    // ":" as well as "/" would deliver this as "30.m4a".
    const uri =
      "content://com.android.externalstorage.documents/tree/primary%3ARecordings/" +
      "document/primary%3ARecordings%2F%2B919876543210%202026-08-26%2016%3A45%3A30.m4a";
    assert.equal(fileNameFromUri(uri), "+919876543210 2026-08-26 16:45:30.m4a");
  });

  it("strips the volume prefix when the tree is rooted at the volume", () => {
    assert.equal(fileNameFromUri("content://x/document/primary%3ACall.m4a"), "Call.m4a");
  });
});

describe("import references", () => {
  const DEVICE = "69b367f1-5cbe-4c27-b0e3-bb211c1e8b92";

  it("stays inside the server's 80-character limit for long OEM names", () => {
    const longest =
      "Call recording Very Long Contact Name Here_20260826_143012_outgoing_backup.m4a";
    const ref = importRefFor(DEVICE, longest);
    assert.ok(ref.length <= 80, `ref was ${ref.length} chars`);
    assert.ok(ref.length < 40);
  });

  it("is stable, so a retry maps to the same call", () => {
    const name = "Call recording 9876543210_260820_091400.m4a";
    assert.equal(importRefFor(DEVICE, name), importRefFor(DEVICE, name));
  });

  it("separates different files and different handsets", () => {
    const a = importRefFor(DEVICE, "call-a.m4a");
    const b = importRefFor(DEVICE, "call-b.m4a");
    const other = importRefFor("11111111-2222-3333-4444-555555555555", "call-a.m4a");
    assert.notEqual(a, b);
    assert.notEqual(a, other);
  });

  it("does not collide across a realistic day of recordings", () => {
    const refs = new Set<string>();
    for (let hour = 0; hour < 24; hour += 1) {
      for (let minute = 0; minute < 60; minute += 1) {
        const name =
          `Call recording 98765432${String(minute).padStart(2, "0")}_260826_` +
          `${String(hour).padStart(2, "0")}${String(minute).padStart(2, "0")}00.m4a`;
        refs.add(importRefFor(DEVICE, name));
      }
    }
    assert.equal(refs.size, 24 * 60);
  });
});
