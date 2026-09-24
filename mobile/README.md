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
| `/`        | Status toggle, today's figures, import backlog, upload badge     |
| `/tracking`| **Primary on Android** — call-log sync + optional recordings     |
| `/call`    | Fallback — in-app recording: policy → consent → record → queue   |
| `/uploads` | The upload queue, with per-item retry                            |
| `/settings`| Folder, permissions, server, unpair                              |

## The Android flow

Two layers, and the second is optional.

**1. The call log** reports every call the phone made or took — number, exact
duration, direction, and missed calls. This works on **every Android phone**,
whether or not it can record anything.

**2. A recordings folder**, when the phone's dialler saves one, attaches audio
to those calls so they also get a transcript and analysis. The agent grants the
folder once through the system picker.

A phone that cannot record still reports its full call volume and talk time.
That is deliberate: a dashboard that only knows about recorded calls
under-reports the floor's work, and the gap is invisible.

Recordings are matched to call-log entries by number and time, so a call takes
its duration and direction from the log — which is exact — and only its audio
from the file.

[`docs/MOBILE_RECORDING.md`](../docs/MOBILE_RECORDING.md) has the filename
formats, the matching rules, the `READ_CALL_LOG` distribution caveat, and the
one folder Android puts out of reach.

## Tests

```bash
npm test        # filename parsing and recording matching
npm run typecheck
```

Both modules are free of React Native imports, so they run in plain Node — which
is how a handset nobody owns still gets its filename format tested, and how the
matching rules are checked without a device.

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
