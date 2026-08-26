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
| `/import`  | **Primary on Android** — scan the dialler's folder and import    |
| `/call`    | Fallback — in-app recording: policy → consent → record → queue   |
| `/uploads` | The upload queue, with per-item retry                            |
| `/settings`| Folder, permissions, server, unpair                              |

## The Android flow

The agent turns on call recording **in their phone's own dialler**, then points
this app at the folder it writes to. From then on, a scan finds every new call,
reads the customer number and time out of the filename, and imports it.

This is better than recording in-app: the OEM dialler holds the privileged
permission that captures both sides of a carrier call at full quality, which no
third-party app can obtain. In-app recording captures the microphone, so the
customer comes through faintly.

Folder access uses the Storage Access Framework — the agent grants one folder,
once, and the grant persists. That is deliberate: the alternative
(`MANAGE_EXTERNAL_STORAGE`) grants the whole filesystem and Play will not
approve it here.

Filename formats for Samsung, Xiaomi, Oppo/OnePlus, Vivo, Google Phone,
Truecaller and Cube ACR are all handled — see
[`docs/MOBILE_RECORDING.md`](../docs/MOBILE_RECORDING.md) for the table and the
constraints, including the one folder Android puts out of reach.

A file whose number cannot be read is listed for the agent to label rather than
being guessed at. Nothing is filed against a number the app is not sure of.

## Tests

```bash
npm test        # filename parsing — the part a handset nobody has still needs right
npm run typecheck
```

The parser has no React Native imports, so it runs in plain Node.

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
