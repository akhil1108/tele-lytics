# Architecture

## The shape of it

```
┌──────────────────┐         ┌──────────────────────────────────────┐
│  Mobile app      │         │  Admin dashboard                     │
│  (Expo / RN)     │         │  (Next.js)                           │
│                  │         │                                      │
│  device token    │         │  user JWT + WebSocket                │
└────────┬─────────┘         └──────────────────┬───────────────────┘
         │                                      │
         │  /v1/mobile/*                        │  /v1/*  ·  /ws/dashboard
         ▼                                      ▼
┌───────────────────────────────────────────────────────────────────┐
│  FastAPI                                                          │
│  auth · agents · calls · recordings · policy · analytics · tasks  │
└───────┬───────────────────────────────────┬───────────────────────┘
        │                                   │
        ▼                                   ▼
┌───────────────┐                  ┌──────────────────┐
│  Postgres     │◀─── job queue ───│  Pipeline worker │
│  + blob store │                  └────────┬─────────┘
└───────────────┘                           │
                            ┌───────────────┴────────────────┐
                            ▼                                ▼
                  ┌──────────────────┐            ┌────────────────────┐
                  │  Speech model    │            │  Insight model     │
                  │  text + tone     │            │  Claude, structured│
                  └──────────────────┘            └────────────────────┘
```

## The pipeline

Two stages, each behind a provider interface, each idempotent.

```
recording ─▶ transcribe ─▶ transcript + per-utterance tone
                              │
                              └─▶ analyze ─▶ sentiment · filler analysis
                                             tasks · actions · satisfaction
```

**Idempotent** means re-running a stage replaces its own output and leaves
everything else alone. That is what makes retries safe, and what lets an
operator re-run one call after swapping models — `POST /v1/calls/{id}/reprocess`.

### Stage 1 — speech

Input: the stored audio plus hints (language, both numbers, direction).
Output: a transcript, and for each utterance a speaker, timings and a tone
reading.

Providers live in `backend/app/llm/stt/`:

- `shared_model` — HTTP adapter for whatever speech model you run. The wire
  contract is `docs/STT_CONTRACT.md`, and the parser is deliberately tolerant
  because real speech APIs disagree on nearly every field name.
- `mock` — a synthetic two-speaker support call, seeded from the call id, so
  the whole system runs with no model attached.

### Stage 2 — insight

Input: the transcript, the call context, and **exact filler counts computed in
code**. Output: a `CallAnalysis`.

The counting is the important part. Filler and stop-word counts are computed
deterministically in `backend/app/llm/stopwords.py` and handed to the model as
fact. The model's job is to *judge* them — whether the filler speech actually
cost the call anything — not to recount them. A model asked to count produces
numbers that drift between runs, and a dashboard whose figures move when
nothing changed is a dashboard nobody trusts.

`backend/app/llm/analysis/claude.py` uses structured outputs, so the response
validates against the `CallAnalysis` schema on arrival. There is no JSON
parsing or repair step, and a malformed response is impossible rather than
merely unlikely. The system prompt is byte-stable and sits behind a cache
breakpoint, so the marginal cost of a call is essentially its transcript.

## Recording policy

Recording is governed per number, and the resolver in
`backend/app/services/policies.py` is the single place that decides:

1. An explicit policy on the **customer's** number that disables recording wins
   over everything. That row is how a do-not-record request is honoured, and it
   has to beat the agent's own settings or it is worthless.
2. Otherwise the **agent's** number decides, including its per-direction flags.
3. With no policy on the agent's number, the answer is **no**.

Point 3 is a deliberate choice about which way to fail. An unrecorded call is a
gap in a report; an unlawfully recorded one is a liability.

The handset calls `GET /v1/mobile/recording-policy` before every call and
honours the answer. The dashboard's `/numbers` page runs the *same* resolver
through `GET /v1/numbers/lookup`, so an operator can confirm what a number will
actually do rather than inferring it from checkboxes.

## Why the job queue is in Postgres

The queue is `processing_jobs`, not Celery or a broker.

- The volume is low — one or two jobs per call — and the jobs are long and
  I/O-bound on a model call. There is no throughput problem to solve.
- A call row and its pipeline work commit in the same transaction. With a
  separate broker, a call can be marked ready for processing while the enqueue
  fails, and that recording is then lost until someone notices.
- One fewer piece of infrastructure to run, monitor and lose.

Claiming is atomic and portable: the `UPDATE … WHERE status = 'queued'` is
itself the lock, so two workers racing for the same row cannot both win. Jobs
whose worker died are reclaimed after 30 minutes. Failures retry with backoff
(30s, 2m, 10m); a `ProviderError` marked non-retryable parks immediately,
because sending the same rejected bytes to the same model three more times only
wastes the model's time.

Run more workers by starting more processes.

## Multi-tenancy

Every tenant-scoped table carries `org_id` directly rather than reaching it
through a join, so every query filters the tenant boundary with one indexed
predicate. Both principal types resolve to an `org_id`:

- **Users** carry a short-lived JWT. The org claim is checked against the user
  row, so a token minted before a user moved between organisations cannot read
  the old tenant's data.
- **Devices** carry a long-lived opaque token — not a JWT, because a long-lived
  credential needs to be revocable immediately, which means a database lookup.
  Only the SHA-256 hash is stored.

A device is bound to exactly one agent and can only ever write that agent's
calls. `tests/test_analytics.py::test_one_tenant_cannot_see_another` and
`tests/test_pipeline.py::test_a_device_cannot_upload_to_another_agents_call`
hold both of these.

## Realtime

`/ws/dashboard` carries presence and call events. Browsers cannot set an
`Authorization` header on a WebSocket handshake, so the access token arrives as
a query parameter — the same short-lived JWT, validated identically.

A snapshot is sent on connect, so a client joining between broadcasts is never
blank, and a dropped broadcast cannot leave one permanently stale.

`PresenceHub` is in-process. Running several API replicas needs a shared bus
(Redis pub/sub) behind the same interface — `broadcast()` is the only method
that would change.

## Retention

Audio is the sensitive part of a call record; the transcript and analysis are
what the dashboard needs long-term. So recordings expire on a schedule while
their derived insight is kept.

Precedence is number override → organisation setting → global default, and `0`
means keep indefinitely. The purge marks the row `purged` rather than deleting
it, so the dashboard can explain why the player is empty instead of returning a
404 that looks like a bug.

## What is deliberately not here

- **Carrier-side recording.** Higher quality than a handset microphone where
  the deployment allows it. The upload API is the same, so it can run alongside
  — see `docs/MOBILE_RECORDING.md`.
- **Speaker identification across calls.** Diarisation labels agent vs customer
  within one call; it does not recognise a returning caller.
- **Live, mid-call analysis.** Everything here is post-call. Real-time
  supervisor assist is a different architecture, not a setting.
