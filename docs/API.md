# API reference

Base URL `http://localhost:8000`. Interactive docs at `/docs`; the OpenAPI
schema is at `/openapi.json` and is the authority — this page is the map.

## Authentication

Two kinds of caller, both `Authorization: Bearer <token>`.

**Dashboard users** exchange email and password for a short-lived JWT:

```bash
curl -X POST localhost:8000/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@northwind.example.com","password":"northwind-admin-2026"}'
```

**Handsets** exchange a one-time pairing code for a long-lived opaque token.
It is not a JWT: a long-lived credential must be revocable immediately, which
means a database lookup. Only its SHA-256 hash is stored.

### Roles

| Role         | Reads everything | Changes configuration |
| ------------ | ---------------- | --------------------- |
| `owner`      | ✓                | ✓                     |
| `admin`      | ✓                | ✓                     |
| `supervisor` | ✓                | —                     |
| `agent`      | —                | —                     |

A device token reaches only `/v1/mobile/*`; a user JWT never reaches it.

## Errors

```json
{ "error": { "code": "not_found", "message": "Call not found" } }
```

| Status | Meaning                                            |
| ------ | -------------------------------------------------- |
| 400    | Malformed input — an unparseable number, bad audio type |
| 401    | Missing, expired or revoked credential             |
| 403    | Authenticated but the role is insufficient          |
| 404    | Absent, or belongs to another tenant                |
| 409    | Conflicts with existing state (duplicate number)    |
| 413    | Recording exceeds `MAX_RECORDING_MB`                |
| 422    | Schema validation failed                            |

A 404 rather than a 403 for another tenant's resource is deliberate: a 403
confirms the id exists.

---

## Dashboard endpoints

### Auth

| Method | Path | Notes |
| ------ | ---- | ----- |
| `POST` | `/v1/auth/login` | Returns user, organisation and a token pair |
| `POST` | `/v1/auth/refresh` | Refresh token → new access token |
| `GET`  | `/v1/auth/me` | Current user |
| `POST` | `/v1/auth/change-password` | |
| `GET` `POST` | `/v1/auth/users` | List / create. Create is admin-only |
| `POST` | `/v1/auth/agents/{id}/pairing-code` | Admin-only. Plaintext code returned **once** |
| `POST` | `/v1/auth/devices/pair` | **Unauthenticated** — the code is the credential |
| `POST` | `/v1/auth/devices/{id}/revoke` | Admin-only. Takes effect immediately |

### Agents

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET`  | `/v1/agents?days=7` | Roster with per-agent call and quality stats |
| `GET`  | `/v1/agents/presence` | Live counts by status |
| `POST` | `/v1/agents` | Admin-only. Optionally provisions a login too |
| `GET` `PATCH` `DELETE` | `/v1/agents/{id}` | `DELETE` deactivates — history is kept |

### Calls

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET`  | `/v1/calls` | Filter by `days` `agent_id` `team` `direction` `status` `sentiment` `satisfied` `has_recording` `search`; paginated |
| `GET`  | `/v1/calls/{id}` | Call with recording, transcript, analysis, tasks and jobs |
| `GET`  | `/v1/calls/{id}/transcript` | Transcript with segments |
| `GET`  | `/v1/calls/{id}/audio` | Streams the audio. Tenancy is checked on every request, so this needs the bearer token — a bare `<audio src>` will 401 |
| `POST` | `/v1/calls/{id}/reprocess?stage=transcribe\|analyze` | Admin-only. Re-runs one stage |

`search` matches the customer number in any dialling format, or the name.

### Recording policy

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET`  | `/v1/numbers` | Filter by `search` `recording_enabled` `kind` |
| `POST` | `/v1/numbers` | Admin-only. Numbers are normalised to E.164 on the way in |
| `GET`  | `/v1/numbers/lookup?number=…&direction=…` | Runs the same resolver the handset does |
| `GET` `PATCH` `DELETE` | `/v1/numbers/{id}` | Changes are written to the audit log |

`lookup` exists so an operator can confirm what a number will actually do,
rather than inferring it from checkboxes.

### Analytics

| Method | Path | Returns |
| ------ | ---- | ------- |
| `GET` | `/v1/analytics/overview?days=7` | Every headline figure in one call |
| `GET` | `/v1/analytics/timeseries?days=7&bucket=hour\|day\|week` | Gap-filled, so charts have no holes |
| `GET` | `/v1/analytics/sentiment?days=7` | Breakdown in fixed label order |
| `GET` | `/v1/analytics/agents?days=7` | Leaderboard |
| `GET` | `/v1/analytics/fillers?days=7&speaker=agent` | Most-used filler words |
| `GET` | `/v1/analytics/risks?days=7` | Risk flags by kind |
| `GET` | `/v1/analytics/recording-coverage?days=7` | Per number: configured vs actual |

Two figures are computed more carefully than they look:

- **`satisfaction_rate`** is over calls that produced a verdict. A call the
  model could not judge is reported separately as
  `unknown_satisfaction_count`, never folded in as dissatisfied.
- **`recording_coverage`** is recorded ÷ *expected*, not ÷ total. It measures
  whether the pipeline worked, so calls policy excluded do not drag it down.

### Tasks

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET`   | `/v1/tasks` | Filter by `status` `kind` `priority` `assignee_agent_id` `overdue_only`. Defaults to open work |
| `PATCH` | `/v1/tasks/{id}` | Status, priority, assignee, due date |

`kind` separates a **task** (someone committed to it on the call) from an
**action** (the model recommends it; nobody promised it).

### Realtime

`GET /ws/dashboard?token=<access token>` — WebSocket.

The token is a query parameter because browsers cannot set headers on a
WebSocket handshake; it is the same JWT, validated identically.

Events: `presence`, `agent.status`, `call.logged`, `recording.uploaded`,
`heartbeat`. A `presence` snapshot is sent on connect, so a client joining
between broadcasts is never blank. Send `refresh` for a fresh snapshot,
`ping` for a `pong`.

---

## Handset endpoints

All require a device token and act on the one agent it is bound to.

| Method | Path | Notes |
| ------ | ---- | ----- |
| `GET`  | `/v1/mobile/me` | The paired agent |
| `POST` | `/v1/mobile/status` | Presence heartbeat; drives the live counter |
| `GET`  | `/v1/mobile/recording-policy?customer_number=…&direction=…` | **Called before every call.** The enforcement point for consent and opt-out |
| `POST` | `/v1/mobile/calls` | Log a call. Idempotent on `external_ref` |
| `POST` | `/v1/mobile/calls/{id}/recording` | `multipart/form-data`. Starts the pipeline |
| `GET`  | `/v1/mobile/calls` | This agent's recent calls |
| `GET`  | `/v1/mobile/summary` | Today's and the last 7 days' figures for the home screen — calls, incoming, outgoing, missed, talk time, recorded, average call, sentiment. `?tz_offset_minutes=330` makes "today" the handset's day |
| `POST` | `/v1/mobile/unpair` | Agent-initiated revoke (lost or swapped phone) |

### Upload

```bash
curl -X POST localhost:8000/v1/mobile/calls/$CALL_ID/recording \
  -H "Authorization: Bearer $DEVICE_TOKEN" \
  -F 'file=@call.m4a;type=audio/mp4' \
  -F 'duration_seconds=272' \
  -F 'consent_captured=true'
```

Accepted: `m4a` `mp3` `wav` `ogg` `opus` `webm` `aac` `amr` `3gp` `flac`.
Re-uploading the same call replaces the audio and re-runs processing, which is
what a handset retrying a failed upload needs.

### Policy decision

```json
{
  "number": "+919876543210",
  "should_record": true,
  "reason": "policy_enabled",
  "consent_required": true,
  "consent_prompt": "This call may be recorded for quality and training purposes.",
  "policy_id": "…",
  "retention_days": 30
}
```

| `reason` | Meaning |
| -------- | ------- |
| `policy_enabled` | Recording is on for this number |
| `no_policy_configured` | No policy exists — **not** recorded |
| `recording_disabled_for_number` | Explicitly switched off |
| `customer_opted_out` | The customer's own policy forbids it; beats the agent's settings |
| `inbound_calls_not_recorded` / `outbound_calls_not_recorded` | This direction is excluded |

---

## Meta

`GET /health` — liveness plus a real database round-trip, and which providers
are configured. A process that cannot reach its database reports `degraded`,
however happily it is running.
