# Call recording on mobile: what actually works

This is the constraint most call-analytics projects discover late, so it is
stated plainly up front.

## Neither platform lets an app record the carrier call

**Android.** The `VOICE_CALL`, `VOICE_DOWNLINK` and `VOICE_UPLINK` audio
sources have required the privileged `CAPTURE_AUDIO_OUTPUT` permission since
Android 10 (API 29). It is `signature|privileged` — granted only to apps signed
with the platform key or installed in the privileged system partition. A
sideloaded or Play-distributed app cannot obtain it. Google Play policy also
prohibits using the accessibility API to work around this, and enforces it.

**iOS.** There is no public API for recording a phone call, at any entitlement
tier. CallKit gives you call *events*, never call *audio*.

Any product claiming otherwise is doing one of the four things below.

## The four routes that do work

### 1. Microphone capture — what this app ships

Records through the handset microphone while the call runs. Ships today, works
on both platforms, needs no special provisioning.

- **Quality:** good for the agent, quieter for the customer. Speakerphone
  improves the far side considerably.
- **Consequence:** the transcript carries per-segment confidence, and
  diarisation is a little less certain than a two-channel tap.
- **Caveat:** iOS suspends microphone capture for a third-party app during an
  active cellular call. In practice this means iOS agents must use speakerphone
  with the app in the foreground, or route through route 2 or 4.

Implemented in `mobile/src/lib/recorder.ts`.

### 2. VoIP calls placed inside the app

If calls go through a softphone your organisation controls, the app owns the
audio session and can capture both legs at full quality. Adding a SIP or WebRTC
stack to this app is the natural extension: the recorder interface stays the
same, only the audio source changes.

### 3. Importing recordings the device already made

Many enterprise diallers, Android OEM phone apps, and MDM-managed device-owner
builds already write call recordings to storage — that last case *does* hold
`CAPTURE_AUDIO_OUTPUT`. The app's **Import** screen picks those files up and
feeds them into the same pipeline.

This is the highest-quality route that requires no change to this codebase, and
it is the one to reach for in a managed fleet.

Implemented in `mobile/app/import.tsx`.

### 4. Carrier or PBX-side recording

The best audio quality, and no handset involvement at all. Your telephony
provider (Twilio, Exotel, Knowlarity, Asterisk, a SIP trunk with a recording
fork) writes the recording, and a small server-side connector posts it to the
same upload endpoint the handset uses.

Because the API is identical, routes 1, 3 and 4 can run side by side — a fleet
where some agents are on managed devices and others are not works without any
special casing.

## What the app does about consent

Recording never begins on a guess.

1. Before every call, the app calls `GET /v1/mobile/recording-policy` with the
   other party's number and the direction.
2. The server answers with a decision and a reason. Recording is refused unless
   an administrator explicitly enabled the agent's number, and an explicit
   customer opt-out overrides that.
3. When the policy says consent is required, the app shows the announcement to
   read out and will not unlock the record control until the agent confirms
   they read it.
4. That confirmation is uploaded with the audio as `consent_captured` and shown
   on the call in the dashboard.

Imported files are always marked `consent_captured: false` — nothing in the
file records that an announcement was made, and claiming otherwise would put a
false statement into a compliance record.

**This is a mechanism, not legal advice.** Two-party consent rules differ by
jurisdiction, and in India the DPDP Act 2023 and TRAI rules impose their own
requirements. Configure the policy for the law you operate under.

## Wiring up route 4

A connector needs three calls. It authenticates as a device, so provision one
pairing code per agent line and store the resulting tokens.

```bash
# 1. Log the call
curl -X POST "$API/v1/mobile/calls" \
  -H "Authorization: Bearer $DEVICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "external_ref": "pbx-6d41f2",
        "direction": "inbound",
        "customer_number": "+919000000001",
        "started_at": "2026-08-26T09:14:00Z",
        "ended_at":   "2026-08-26T09:18:32Z",
        "recording_expected": true
      }'

# 2. Upload the audio — this starts the pipeline
curl -X POST "$API/v1/mobile/calls/$CALL_ID/recording" \
  -H "Authorization: Bearer $DEVICE_TOKEN" \
  -F 'file=@call.wav;type=audio/wav' \
  -F 'duration_seconds=272' \
  -F 'consent_captured=true'

# 3. Nothing. The transcript and analysis appear in the dashboard on their own.
```

`external_ref` makes step 1 idempotent, so a connector that retries after a
network drop does not create duplicate calls.
