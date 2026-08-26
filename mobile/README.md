# Agent mobile app

Expo / React Native app for agents. Records call audio, honours the recording
policy for each number, and uploads to the analytics pipeline.

## Running

```bash
npm install
cp .env.example .env          # EXPO_PUBLIC_API_BASE_URL must be reachable
npx expo start                # then scan the QR with Expo Go, or press a / i
```

On a physical handset the API URL must be a LAN or public address —
`localhost` there means the phone itself.

Microphone recording needs a development build rather than Expo Go on iOS:

```bash
npx expo run:android
npx expo run:ios
```

## Screens

| Route      | What it does                                                     |
| ---------- | ---------------------------------------------------------------- |
| `/pair`    | Exchange a one-time code for a device token                      |
| `/`        | Status toggle, today's figures, upload badge                     |
| `/call`    | Policy check → consent → record → queue                          |
| `/uploads` | The upload queue, with per-item retry                            |
| `/import`  | Bring in a recording the dialler already saved                   |
| `/settings`| Permissions, server, unpair                                      |

## Read this before planning around recording

**Neither Android nor iOS lets an app record the carrier voice call.** This app
records through the microphone, which works for speakerphone and in-app VoIP
calls, and it imports recordings the device already made. The full picture —
including the two higher-quality routes and how to wire them up — is in
[`docs/MOBILE_RECORDING.md`](../docs/MOBILE_RECORDING.md).

## How pairing works

An admin generates a one-time code in the dashboard; the agent types it in. The
exchange returns a long-lived opaque device token, stored in the platform
keystore via `expo-secure-store`.

The token binds this handset to exactly one agent. The app never says which
agent it is — the server decides from the token — so a compromised handset
cannot write into anyone else's call history. An admin can revoke it instantly
from `/agents`.

## The upload queue

Agents work in lifts, basements and moving vehicles, so an upload failing is
the normal case, not the exception.

`src/lib/uploadQueue.ts` persists to AsyncStorage on every change, so a
recording survives the app being killed, and drains when the handset regains a
connection (NetInfo, plus a 60-second sweep). Retries back off 30s → 2m → 10m →
30m.

Two rules matter:

- **The audio file is deleted only once the server has accepted it.** Not
  before.
- **A permanently failed upload stays on the list, visible and retryable by
  hand.** A recording is not something to drop quietly.

A 4xx or an auth failure is treated as permanent — the same bytes will be
rejected the same way every time.

## Consent

`/call` will not unlock the record control until the server's policy says this
call may be recorded, and — where consent is required — until the agent
confirms they read the announcement. That confirmation travels with the audio
as `consent_captured` and appears on the call in the dashboard.

Imported files are always `consent_captured: false`, because nothing in the
file records that an announcement was made.
