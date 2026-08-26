/**
 * Reading an OEM call recording's filename.
 *
 * Android phone apps that record calls encode the other party's number and the
 * time into the filename, and every manufacturer does it differently. This
 * module turns those filenames into something the importer can act on.
 *
 * It is deliberately free of React Native imports so the parsing can be tested
 * as plain TypeScript — this is the part most likely to be wrong on a handset
 * nobody tested against, so it is the part that earns tests.
 *
 * Nothing here guesses. When the number or the time cannot be read with
 * confidence the file is returned as needing the agent to confirm it, because
 * a recording filed against the wrong customer is worse than one the agent had
 * to label by hand.
 */

export type ParsedDirection = "inbound" | "outbound" | "unknown";
export type ParseConfidence = "high" | "medium" | "low";

export interface ParsedRecording {
  /** Filename as it appeared on disk, including extension. */
  fileName: string;
  /** Digits as written in the filename — not yet normalised to E.164. */
  customerNumber: string | null;
  /** Some recorders write a saved contact's name instead of the number. */
  contactName: string | null;
  recordedAt: Date | null;
  direction: ParsedDirection;
  confidence: ParseConfidence;
  /** Which recogniser produced this, for support and for the tests. */
  pattern: string;
}

const AUDIO_EXTENSIONS = new Set([
  "m4a", "mp3", "wav", "amr", "3gp", "3gpp", "aac", "ogg", "opus", "flac", "mp4", "awb",
]);

export const MIME_BY_EXTENSION: Record<string, string> = {
  m4a: "audio/mp4",
  mp4: "audio/mp4",
  mp3: "audio/mpeg",
  wav: "audio/wav",
  amr: "audio/amr",
  awb: "audio/amr",
  "3gp": "audio/3gpp",
  "3gpp": "audio/3gpp",
  aac: "audio/aac",
  ogg: "audio/ogg",
  opus: "audio/opus",
  flac: "audio/flac",
};

/** Folders the common Android OEMs write call recordings into. */
export const KNOWN_RECORDING_FOLDERS: { label: string; path: string }[] = [
  { label: "Samsung", path: "Recordings/Call" },
  { label: "Samsung (older)", path: "Sounds" },
  { label: "Xiaomi / Redmi / POCO", path: "MIUI/sound_recorder/call_rec" },
  { label: "OnePlus / Oppo / Realme", path: "Recordings/Call Recordings" },
  { label: "Oppo (alternate)", path: "Music/Recordings/Call Recordings" },
  { label: "Vivo", path: "Record/Call" },
  { label: "Generic", path: "CallRecordings" },
  { label: "Generic (spaced)", path: "Call Recordings" },
  { label: "Cube ACR", path: "CubeCallRecorder/All" },
  { label: "Truecaller", path: "Truecaller/Recordings" },
];

const DIRECTION_TOKENS: Record<string, ParsedDirection> = {
  in: "inbound",
  inc: "inbound",
  incoming: "inbound",
  received: "inbound",
  recv: "inbound",
  out: "outbound",
  outg: "outbound",
  outgoing: "outbound",
  dialed: "outbound",
  dialled: "outbound",
  sent: "outbound",
};

export function extensionOf(fileName: string): string {
  const dot = fileName.lastIndexOf(".");
  return dot === -1 ? "" : fileName.slice(dot + 1).toLowerCase();
}

export function isAudioFile(fileName: string): boolean {
  return AUDIO_EXTENSIONS.has(extensionOf(fileName));
}

export function mimeTypeFor(fileName: string): string {
  return MIME_BY_EXTENSION[extensionOf(fileName)] ?? "audio/mpeg";
}

/**
 * A SAF document URI hides the filename inside a percent-encoded path.
 * `content://…/document/primary%3ARecordings%2FCall%2FCall%20rec.m4a`
 */
export function fileNameFromUri(uri: string): string {
  let decoded = uri;
  try {
    decoded = decodeURIComponent(uri);
  } catch {
    /* a malformed escape leaves the raw string, which still usually ends in a name */
  }
  const cleaned = decoded.split("?")[0].replace(/\/+$/, "");

  // Split on "/" only. Splitting on ":" as well would cut a filename that
  // contains a clock time — the Google Phone app writes exactly that
  // ("+919876543210 2026-08-26 16:45:30.m4a") and it would arrive as "30.m4a".
  const lastSlash = cleaned.lastIndexOf("/");
  const afterSlash = lastSlash === -1 ? cleaned : cleaned.slice(lastSlash + 1);

  // A tree rooted at the volume itself has no slash: "primary:Recording.m4a".
  return afterSlash.replace(/^[A-Za-z0-9]+:/, "");
}

// ---------------------------------------------------------------- internals

/** Digit runs that are really timestamps, not phone numbers. */
interface TimeCandidate {
  date: Date;
  /** Index of the token consumed, so it is not also read as a number. */
  tokenIndex: number;
  /** How many tokens the timestamp spanned (date and time are often split). */
  span: number;
}

function isPlausibleYear(year: number): boolean {
  // Call recording did not exist before smartphones, and a far-future date is
  // a misread rather than a real recording.
  return year >= 2005 && year <= 2100;
}

function makeDate(
  year: number,
  month: number,
  day: number,
  hour = 0,
  minute = 0,
  second = 0,
): Date | null {
  if (!isPlausibleYear(year)) return null;
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  if (hour > 23 || minute > 59 || second > 59) return null;

  const date = new Date(year, month - 1, day, hour, minute, second);
  // Rejects 31 February and friends, which JS would silently roll over.
  if (date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date;
}

function fromEpoch(token: string): Date | null {
  if (!/^\d{10}$|^\d{13}$/.test(token)) return null;
  const value = Number(token);
  const millis = token.length === 13 ? value : value * 1000;
  const date = new Date(millis);
  return isPlausibleYear(date.getFullYear()) ? date : null;
}

/** `20260826143012`, `20260826`, plus a following `143012` if present. */
function fromCompactDate(tokens: string[], index: number): TimeCandidate | null {
  const token = tokens[index];

  if (/^\d{14}$/.test(token)) {
    const date = makeDate(
      Number(token.slice(0, 4)), Number(token.slice(4, 6)), Number(token.slice(6, 8)),
      Number(token.slice(8, 10)), Number(token.slice(10, 12)), Number(token.slice(12, 14)),
    );
    return date ? { date, tokenIndex: index, span: 1 } : null;
  }

  if (/^\d{8}$/.test(token)) {
    const next = tokens[index + 1];
    const hasTime = next && /^\d{6}$/.test(next);
    const date = makeDate(
      Number(token.slice(0, 4)), Number(token.slice(4, 6)), Number(token.slice(6, 8)),
      hasTime ? Number(next.slice(0, 2)) : 0,
      hasTime ? Number(next.slice(2, 4)) : 0,
      hasTime ? Number(next.slice(4, 6)) : 0,
    );
    return date ? { date, tokenIndex: index, span: hasTime ? 2 : 1 } : null;
  }

  // Samsung's two-digit year: `250826_143012`. Only read as a date when a
  // six-digit time follows, or it is indistinguishable from a short number.
  if (/^\d{6}$/.test(token)) {
    const next = tokens[index + 1];
    if (!next || !/^\d{6}$/.test(next)) return null;
    const date = makeDate(
      2000 + Number(token.slice(0, 2)), Number(token.slice(2, 4)), Number(token.slice(4, 6)),
      Number(next.slice(0, 2)), Number(next.slice(2, 4)), Number(next.slice(4, 6)),
    );
    return date ? { date, tokenIndex: index, span: 2 } : null;
  }

  return null;
}

/** `2026-08-26 14:30:12` and `2026-08-26_14-30-12` survive tokenisation as parts. */
function fromDashedDate(raw: string): Date | null {
  const match = raw.match(
    /(20\d{2})[-.](\d{1,2})[-.](\d{1,2})(?:[ _T]+(\d{1,2})[-:.](\d{1,2})(?:[-:.](\d{1,2}))?)?/,
  );
  if (!match) return null;
  return makeDate(
    Number(match[1]), Number(match[2]), Number(match[3]),
    Number(match[4] ?? 0), Number(match[5] ?? 0), Number(match[6] ?? 0),
  );
}

/**
 * Whether a digit run reads as a phone number rather than a timestamp.
 *
 * Ten digits is the ambiguous case: an Indian mobile number and a Unix
 * timestamp in seconds are both ten digits. They are separable by their first
 * digit — epoch seconds for any plausible year begin `1`, and no national
 * mobile number does.
 */
function looksLikePhoneNumber(token: string, hadPlus: boolean): boolean {
  if (hadPlus) return /^\d{7,15}$/.test(token);
  if (!/^\d{7,15}$/.test(token)) return false;
  if (token.length === 10 && token.startsWith("1")) return false;
  if (token.length === 13 || token.length === 14) return false; // epoch millis / compact datetime
  if (token.length === 8) return false; // compact date
  return true;
}

const SEPARATORS = /[\s_\-@#()[\]]+/;

// ------------------------------------------------------------------- parser

export function parseRecordingFileName(fileName: string): ParsedRecording {
  const result: ParsedRecording = {
    fileName,
    customerNumber: null,
    contactName: null,
    recordedAt: null,
    direction: "unknown",
    confidence: "low",
    pattern: "unrecognised",
  };

  const extension = extensionOf(fileName);
  const stem = extension ? fileName.slice(0, -(extension.length + 1)) : fileName;
  if (!stem.trim()) return result;

  // A dashed date has to be read before tokenising, because splitting on "-"
  // would tear `2026-08-26` apart.
  const dashedDate = fromDashedDate(stem);
  let working = stem;
  if (dashedDate) {
    result.recordedAt = dashedDate;
    result.pattern = "iso-date";
    working = working.replace(
      /(20\d{2})[-.](\d{1,2})[-.](\d{1,2})(?:[ _T]+(\d{1,2})[-:.](\d{1,2})(?:[-:.](\d{1,2}))?)?/,
      " ",
    );
  }

  const rawTokens = working.split(SEPARATORS).filter(Boolean);
  const tokens = rawTokens.map((token) => token.replace(/^\+/, ""));
  const hadPlus = rawTokens.map((token) => token.startsWith("+"));

  const consumed = new Set<number>();

  // 1. Direction, wherever it appears.
  tokens.forEach((token, index) => {
    const mapped = DIRECTION_TOKENS[token.toLowerCase()];
    if (mapped && result.direction === "unknown") {
      result.direction = mapped;
      consumed.add(index);
    }
  });

  // 2. Timestamp. Compact date forms first — they are unambiguous — then epoch.
  if (!result.recordedAt) {
    for (let index = 0; index < tokens.length; index += 1) {
      const candidate = fromCompactDate(tokens, index);
      if (candidate) {
        result.recordedAt = candidate.date;
        result.pattern = "compact-date";
        for (let offset = 0; offset < candidate.span; offset += 1) {
          consumed.add(candidate.tokenIndex + offset);
        }
        break;
      }
    }
  }
  if (!result.recordedAt) {
    for (let index = 0; index < tokens.length; index += 1) {
      if (consumed.has(index)) continue;
      const date = fromEpoch(tokens[index]);
      if (date) {
        result.recordedAt = date;
        result.pattern = "epoch";
        consumed.add(index);
        break;
      }
    }
  }

  // 3. Phone number. A `+`-prefixed token wins outright; otherwise take the
  //    last plausible run, since recorders put the label first and the number
  //    after it ("Call recording 9876543210_…").
  let numberIndex = tokens.findIndex(
    (token, index) => !consumed.has(index) && hadPlus[index] && looksLikePhoneNumber(token, true),
  );
  if (numberIndex === -1) {
    for (let index = tokens.length - 1; index >= 0; index -= 1) {
      if (consumed.has(index)) continue;
      if (looksLikePhoneNumber(tokens[index], false)) {
        numberIndex = index;
        break;
      }
    }
  }
  if (numberIndex !== -1) {
    result.customerNumber = (hadPlus[numberIndex] ? "+" : "") + tokens[numberIndex];
    consumed.add(numberIndex);
  }

  // 4. Whatever alphabetic text is left is a contact name — several recorders
  //    write the saved name when the caller is in the address book, and then
  //    there is no number in the filename at all.
  const leftover = tokens
    .filter((token, index) => !consumed.has(index) && /[A-Za-z]/.test(token))
    .filter((token) => !isLabelWord(token));
  if (leftover.length > 0) {
    result.contactName = leftover.join(" ").trim() || null;
  }

  if (result.customerNumber && result.recordedAt) {
    result.confidence = "high";
  } else if (result.customerNumber || result.recordedAt) {
    result.confidence = "medium";
  } else {
    result.confidence = "low";
  }
  if (result.pattern === "unrecognised" && result.customerNumber) {
    result.pattern = "number-only";
  }

  return result;
}

/**
 * A stable, short identifier for "this file, imported by this handset".
 *
 * It becomes the call's `external_ref`, which the server caps at 80 characters
 * and uses for idempotency — and a UUID device id plus a Samsung filename
 * comfortably exceeds that, so the filename is folded into a hash rather than
 * carried whole. The full filename is still sent in the call metadata, where
 * there is no length limit and where support will look for it.
 *
 * FNV-1a rather than a cryptographic digest: this only needs to avoid
 * collisions among one handset's own recordings, and it stays synchronous and
 * dependency-free.
 */
export function importRefFor(deviceId: string, fileName: string): string {
  return `imp-${deviceId.replace(/-/g, "").slice(0, 8)}-${fnv1a64(fileName)}`;
}

function fnv1a64(value: string): string {
  // 64-bit FNV-1a run as two 32-bit halves, because JS bitwise ops are 32-bit.
  let high = 0x811c9dc5;
  let low = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    high ^= code;
    low ^= (code << 5) | (code >>> 3);
    high = Math.imul(high, 0x01000193) >>> 0;
    low = Math.imul(low, 0x01000193) >>> 0;
  }
  return high.toString(16).padStart(8, "0") + low.toString(16).padStart(8, "0");
}

/** Words the recorders themselves add, which are never a contact's name. */
const LABEL_WORDS = new Set([
  "call", "calls", "recording", "recordings", "record", "recorder", "rec",
  "voice", "audio", "phone", "phonerecord", "callrecording", "new",
  "truecaller", "cube", "acr", "auto", "mp3", "wav", "amr", "unknown",
]);

function isLabelWord(token: string): boolean {
  return LABEL_WORDS.has(token.toLowerCase().replace(/[^a-z]/g, ""));
}
