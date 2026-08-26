# Call tracking and recording on Android

## The shape of it

Two layers, and the second is optional:

```
┌─────────────────────────────────────────────────────────────┐
│  1. CALL LOG — every Android phone                          │
│     number · exact duration · direction · missed calls      │
│     → volume, talk time, who was called                     │
└──────────────────────────┬──────────────────────────────────┘
                           │  matched by number + time
┌──────────────────────────┴──────────────────────────────────┐
│  2. RECORDINGS — only phones whose dialler records          │
│     the audio for those calls                               │
│     → transcript, tone, sentiment, tasks, satisfaction      │
└─────────────────────────────────────────────────────────────┘
```

**A phone that cannot record still reports every call it handled.** That is the
point of splitting it this way. A dashboard that only knows about recorded
calls under-reports the floor's work, and the gap is invisible — which is worse
than a gap you can see.

## Layer 1 — the call log

The app reads `CallLog.Calls` and reports what it finds. This works on every
Android phone regardless of whether it can record.

What each entry gives:

| Field | Used for |
| ----- | -------- |
| Number | Who was called |
| Date | When the call started |
| Duration | Exact talk time (zero for missed) |
| Type | Incoming, outgoing or missed — a real direction, not a guess |

Only those four are read. The call log also holds contact names, photo URIs,
geocoded locations and voicemail transcriptions; none of that is touched.

**Entries that are skipped:** voicemail, blocked and rejected calls, and calls
from withheld or private numbers. None of them is a call the agent handled, and
counting them would inflate the day's figures with calls nobody spoke on.

**Missed calls are reported** — with zero duration and a reason of
`call_not_answered`. They count towards call volume and are excluded from
average call length, so improving missed-call reporting cannot make the average
appear to fall.

### The permission caveat

`READ_CALL_LOG` is a **restricted permission**. Google Play's Permissions policy
limits it to a small set of approved uses — default dialler, caller ID, device
backup and a few others. A workforce app distributed through **MDM, a private
Play channel, or sideload** is unaffected. **Public Play distribution needs a
policy declaration** and may be refused.

If that is a blocker, the app still works without it: in-app recording and
folder import both function, you simply lose the accounting for calls that were
never recorded.

## Layer 2 — recordings

**No app can record the carrier voice call.** Android's `VOICE_CALL`,
`VOICE_DOWNLINK` and `VOICE_UPLINK` audio sources have required the privileged
`CAPTURE_AUDIO_OUTPUT` permission since Android 10 (API 29). It is
`signature|privileged` — granted only to apps signed with the platform key or
shipped in the system partition. The phone's built-in dialler *is* such an app.
This one is not, and Play policy separately forbids using the accessibility API
to work around it.

So the agent turns on call recording in their **own dialler**, and this app
reads the folder it writes to. That gives both sides of the call at full
quality. The in-app microphone recorder remains as a fallback; it captures the
agent clearly and the customer faintly, so use speakerphone if you rely on it.

Folder access uses the **Storage Access Framework**: the agent grants one folder
through the system picker and the app receives a persistable read grant for that
tree, surviving restarts. The alternative, `MANAGE_EXTERNAL_STORAGE`, grants the
entire filesystem and Play will not approve it for an app of this kind.

### Folders offered by default

| Manufacturer | Folder |
| ------------ | ------ |
| Samsung | `Recordings/Call` |
| Xiaomi / Redmi / POCO | `MIUI/sound_recorder/call_rec` |
| OnePlus / Oppo / Realme | `Recordings/Call Recordings` |
| Oppo (alternate) | `Music/Recordings/Call Recordings` |
| Vivo | `Record/Call` |
| Cube ACR | `CubeCallRecorder/All` |
| Truecaller | `Truecaller/Recordings` |

Anything else is reachable with **Browse for the folder**.

**One folder is out of reach.** The Google Phone app on Pixel writes to
`Android/data/com.google.android.dialer/files/CallRecordings`, and Android 11+
blocks SAF from `Android/data` entirely. On a Pixel, layer 1 still reports every
call; only the audio is unavailable.

## Matching recordings to calls

A recording is paired with a call-log entry when the numbers match and the times
are within **three minutes**.

Three minutes because recorders stamp filenames at different moments — some when
recording starts, some when the file is finalised at the end — so the gap can be
the length of the call plus clock skew. Matching is greedy nearest-in-time, one
recording per call: a recording that could fit two calls goes to the closer one,
and a call that already has audio is not offered a second file.

Numbers are compared on their last nine digits, which survives the difference
between `+919876543210`, `09876543210` and `9876543210`.

**Why match at all, rather than trusting the filename?** Because the call log is
better data. It has the exact connected duration and a real direction; a
filename has an approximate timestamp and usually no direction. Matching takes
the metadata from the log and only the audio from the file.

### Filename formats read

| Recorder | Filename |
| -------- | -------- |
| Samsung | `Call recording 9876543210_250826_143012.m4a` |
| Samsung (saved contact) | `Call recording Rohit Verma_250826_143012.m4a` |
| Xiaomi | `1756218612000_9876543210.mp3` |
| Oppo / OnePlus | `Call@9876543210_20260826143012.amr` |
| Vivo | `9876543210_20260826_143012.wav` |
| Google Phone | `+919876543210 2026-08-26 14:30:12.m4a` |
| Cube ACR and similar | `20260826_143012_+919876543210_out.mp3` |
| Truecaller | `Truecaller_9876543210_20260826_143012.m4a` |

Two details worth knowing:

**Ten digits is ambiguous.** An Indian mobile number and a Unix timestamp in
seconds are both ten digits. They separate on the first digit: epoch seconds for
any plausible year start with `1`, and no national mobile number does.

**Nothing is guessed.** A recording whose number cannot be read is not attached
to a call — it is offered to the agent to label. An impossible date (`20260231`)
or one from before smartphones is rejected rather than rolled over. Attaching
audio to the wrong call would put one customer's words under another customer's
name.

## Consent and policy

The policy check applies to **audio**, not to the fact a call happened.

- A **call** is always reportable. Hiding the day's work would not protect
  anyone, and a missing call is a hole in a report nobody can see.
- **Audio** is only uploaded when policy allows it. A customer who has opted out,
  or a number whose recording is switched off, has the recording refused — the
  file stays on the agent's phone, and the call is still reported with a reason
  the dashboard can show.
- Per-direction switches govern capture, so they do not block an import whose
  direction is unknown. Turning *both* off does.

Dialler recordings are always marked `consent_captured: false`, because nothing
in the file records that an announcement was made. The dashboard says so in
words next to the recording, so it reads as a fact about the file's origin
rather than a compliance failure.

**This is a mechanism, not legal advice.** Two-party consent rules differ by
jurisdiction, and India's DPDP Act 2023 and TRAI rules impose their own
requirements. Configure the policy for the law you operate under.

## Not reporting the same call twice

Three independent guards:

- **A call-log ledger** of provider row ids already reported.
- **A sync cursor**, so each scan only reads entries newer than the last one.
  It advances only past what was actually read, so an interrupted sync resumes
  rather than skipping the remainder.
- **`external_ref` on the server** — `log-<device>-<row id>` for a call-log
  entry, or a hash of device id and filename for a folder import. Re-sending one
  returns the existing call rather than creating a second.

The original file in the recordings folder is never modified or deleted. It is
the agent's file. The app copies it to its own cache to upload and deletes only
that copy, once the server has accepted it.

## iOS

iOS gives an app no access to the call log and no access to another app's files,
and it has no call-recording API at any entitlement tier. On iOS the options are
the in-app recorder on speakerphone, or server-side recording.

## Server-side recording

Best audio quality, no handset involvement, and the right answer for a fleet
with a recording-capable PBX or carrier (Twilio, Exotel, Knowlarity, Asterisk, a
SIP trunk with a recording fork).

A connector needs two calls. It authenticates as a device, so provision one
pairing code per agent line and store the tokens.

```bash
# 1. Log the call
CALL_ID=$(curl -sX POST "$API/v1/mobile/calls" \
  -H "Authorization: Bearer $DEVICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "external_ref": "pbx-6d41f2",
        "direction": "inbound",
        "customer_number": "+919000000001",
        "started_at": "2026-08-26T09:14:00Z",
        "ended_at":   "2026-08-26T09:18:32Z",
        "recording_expected": true
      }' | jq -r .id)

# 2. Upload the audio — this starts the pipeline
curl -X POST "$API/v1/mobile/calls/$CALL_ID/recording" \
  -H "Authorization: Bearer $DEVICE_TOKEN" \
  -F 'file=@call.wav;type=audio/wav' \
  -F 'duration_seconds=272' \
  -F 'consent_captured=true'
```

`external_ref` makes step 1 idempotent, so a connector retrying after a network
drop does not create duplicate calls.

Because the API is identical, handset tracking and server-side recording can run
side by side — a fleet where some agents are on managed devices and others are
not needs no special casing.

## Reading the code

| File | What it does |
| ---- | ------------ |
| `mobile/modules/call-log/` | Native module reading `CallLog.Calls` |
| `mobile/src/lib/callLogSync.ts` | Filtering, direction mapping, recording matching — pure and tested |
| `mobile/src/lib/callLogService.ts` | Sync orchestration, ledger, cursor |
| `mobile/src/lib/callRecordings.ts` | Filename parsing — pure and tested |
| `mobile/src/lib/importer.ts` | SAF folder access and scanning |
| `mobile/app/tracking.tsx` | The two-step setup screen |

`npm test` in `mobile/` covers the parsing and matching rules. They run in plain
Node, which is how a handset nobody owns still gets its filename format tested.
