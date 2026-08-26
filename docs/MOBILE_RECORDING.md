# Call recording on mobile

## The short version

On Android, the workflow that works is:

1. The agent turns on call recording **in the phone's own dialler**.
2. The agent grants this app read access to the folder those recordings land
   in — once, via the system folder picker.
3. The app scans that folder, reads the customer number and the time out of
   each filename, and uploads new recordings to the pipeline.

The app also has an in-app microphone recorder, but that is the fallback. The
import path gives better audio, needs no special permission, and does not
require the agent to remember to press anything during a call.

## Why the phone's own recorder, and not this app

**No app can record the carrier voice call.** Android's `VOICE_CALL`,
`VOICE_DOWNLINK` and `VOICE_UPLINK` audio sources have required the privileged
`CAPTURE_AUDIO_OUTPUT` permission since Android 10 (API 29). It is
`signature|privileged` — granted only to apps signed with the platform key or
shipped in the system partition. The phone's built-in dialler *is* such an app.
This one is not, and Play policy separately forbids using the accessibility API
to work around it.

So the OEM recorder gets both sides of the call at full quality; a third-party
app pointed at the microphone gets the agent clearly and the customer faintly.
Reading the OEM's output is strictly better.

iOS has no equivalent. There is no call-recording API at any entitlement tier,
and one app cannot read another's files. On iOS, use the in-app recorder on
speakerphone, or record server-side (below).

## How folder access works

The app uses the **Storage Access Framework**: the agent picks the folder
through the system UI and the app receives a persistable read grant for that
tree. It survives restarts and reboots.

This is deliberate rather than convenient. The alternative,
`MANAGE_EXTERNAL_STORAGE` ("All files access"), grants the whole filesystem and
Google will not approve it for an app of this kind. SAF grants exactly one
folder.

**One folder is out of reach**: the Google Phone app on Pixel writes to
`Android/data/com.google.android.dialer/files/CallRecordings`, and Android 11+
blocks SAF from `Android/data` entirely. Pixel fleets need a different dialler,
a device-owner build, or server-side recording.

### Folders the app offers by default

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

## Reading the filename

Every recorder encodes the number and time differently. `mobile/src/lib/callRecordings.ts`
handles the formats below, and `npm test` in `mobile/` covers each one.

| Recorder | Filename | Read as |
| -------- | -------- | ------- |
| Samsung | `Call recording 9876543210_250826_143012.m4a` | number + time |
| Samsung (saved contact) | `Call recording Rohit Verma_250826_143012.m4a` | name + time, **number needed** |
| Xiaomi | `1756218612000_9876543210.mp3` | epoch + number |
| Oppo / OnePlus | `Call@9876543210_20260826143012.amr` | number + time |
| Vivo | `9876543210_20260826_143012.wav` | number + time |
| Google Phone | `+919876543210 2026-08-26 14:30:12.m4a` | E.164 + time |
| Cube ACR and similar | `20260826_143012_+919876543210_out.mp3` | time + number + **direction** |
| Truecaller | `Truecaller_9876543210_20260826_143012.m4a` | number + time |

Two details that matter:

**Ten digits is ambiguous.** An Indian mobile number and a Unix timestamp in
seconds are both ten digits. They are told apart by the first digit: epoch
seconds for any plausible year start with `1`, and no national mobile number
does.

**Nothing is guessed.** A file whose number cannot be read is listed separately
with a field to type it into. A recording filed against the wrong customer is
worse than one the agent had to label, so the app never picks a number it is
not sure of. Same for the date: an impossible one (`20260231`) or one from
before smartphones is rejected rather than rolled over.

## Direction

Most recorders do not record whether a call was incoming or outgoing. Rather
than defaulting to one and reporting a fabricated inbound/outbound split, calls
imported without that information are stored as **`unknown`**.

The dashboard shows them as "Direction unknown", counts them in the call total,
and leaves them out of the inbound/outbound figures — so those two deliberately
do not sum to the total. An agent who knows their line is inbound-only can set
a default in the import screen, and the call metadata records whether the
direction came from the filename or was assumed.

## Consent and policy

An already-recorded file still goes through the policy check before it is
uploaded — the question changes from "may I record this?" to "may I ingest
this?", and the answer still has to be yes.

- A customer who has opted out has their recording **refused at import** and
  never uploaded. The agent is told why, and the file stays on their phone.
- A number whose recording is switched off is refused the same way.
- The per-direction switches govern capture, so they do not block an import
  whose direction is unknown. Turning *both* off does.

Imported files are always marked `consent_captured: false`, because nothing in
the file records that an announcement was made. The dashboard says so in words
next to the recording, so it reads as a fact about the file's origin rather
than a compliance failure.

**This is a mechanism, not legal advice.** Two-party consent rules differ by
jurisdiction, and India's DPDP Act 2023 and TRAI rules impose their own
requirements. Configure the policy for the law you operate under.

## Not uploading the same call twice

Two independent guards:

- **On the handset**, a ledger of imported filenames. A re-scan skips them.
  Settings has a "offer every recording again" control for the case where a
  batch was filed against the wrong numbers.
- **On the server**, `external_ref` — a short hash of the device id and the
  filename. Re-sending it returns the existing call rather than creating a
  second one, which covers a crash between logging the call and uploading its
  audio.

The original file in the recordings folder is never modified or deleted. It is
the agent's file. The app copies it to its own cache to upload, and deletes
only that copy once the server has accepted it.

## Server-side recording

Best audio quality, no handset involvement, and the right answer for a fleet
with a recording-capable PBX or carrier (Twilio, Exotel, Knowlarity, Asterisk,
a SIP trunk with a recording fork).

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

Because the API is identical, handset import and server-side recording can run
side by side — a fleet where some agents are on managed devices and others are
not needs no special casing.
