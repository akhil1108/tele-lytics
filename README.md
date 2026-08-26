# Call Analytics

Call recording insight for contact centres. Agents carry a mobile app that
records their calls; supervisors get a dashboard showing who is on a call right
now, what was said, how the customer felt about it, and what somebody promised
to do.

Two applications over one API:

| Application         | Who uses it   | What it does                                                        |
| ------------------- | ------------- | ------------------------------------------------------------------- |
| **Admin dashboard** | Supervisors   | Live floor status, call volume, transcripts, insight, recording policy |
| **Agent app**       | Agents        | Reports every call from the phone's log, uploads recordings where they exist |

## What happens to a call

```
phone call log ──▶ every call reported (number · duration · direction)
                            │
                            └── has a dialler recording? ──▶ policy check ──▶ upload
                                                                 │
                                        ┌────────────────────────┴─────┐
                                        ▼                            ▼
                              stage 1: speech model        stage 2: insight model
                              transcript + tone            sentiment · filler words
                                                           tasks · actions · CSAT
                                        └─────────────┬──────────────┘
                                                      ▼
                                              admin dashboard
```

Both stages sit behind a provider interface, so the models are swapped by
environment variable. Ship with `STT_PROVIDER=mock` and `ANALYSIS_PROVIDER=mock`
and the entire system runs with no credentials at all — which is how the tests
run and how the demo seeds.

## Running it

```bash
git clone <this repo> && cd call-analytics
cp .env.example .env
docker compose up --build

# demo organisation with transcripts, insight and tasks
docker compose exec api python -m scripts.seed --calls 60
```

- Dashboard → <http://localhost:3000> · `admin@northwind.example.com` / `northwind-admin-2026`
- API docs → <http://localhost:8000/docs>

The mobile app runs separately:

```bash
cd mobile && npm install && npx expo start
```

Pair a handset: **Agents → Pair** in the dashboard produces a one-time code;
type it into the app.

Without Docker, see [`backend/README.md`](backend/README.md),
[`web/README.md`](web/README.md) and [`mobile/README.md`](mobile/README.md).

## What the dashboard shows

- **Live floor** — agents on call right now, over a WebSocket, not a poll.
- **Volume and coverage** — calls handled, and of the calls policy said to
  record, how many actually produced audio. Calls policy *excluded* are not
  counted as failures.
- **Sentiment** — per call and over time, with the moments it turned. Clicking
  a turning point seeks the audio player to it.
- **Satisfaction** — a verdict per call, with the evidence quoted. A call that
  gives no usable signal is reported as *unclear* rather than guessed, and
  abstentions are excluded from the rate.
- **Filler words** — counted exactly, per speaker, as a rate per 100 words so
  it compares across calls of any length.
- **Tasks and actions** — what someone committed to on the call, separate from
  what the model recommends doing next. Both quote the line they came from.
- **Recording policy** — per number, with a checker that runs the same resolver
  the handset does.

## Design decisions worth knowing

**Recording is off unless a number says otherwise, and a customer opt-out beats
the agent's own settings.** An unrecorded call is a gap in a report; an
unlawfully recorded one is a liability. `docs/ARCHITECTURE.md` §Recording policy.

**A phone that cannot record still reports every call.** The Android app reads
the call log for number, exact duration and direction, and reports all of it.
Where the phone's dialler also saves recordings, those are matched to the log
entries and add a transcript on top. Splitting it this way means a dashboard
that only knows about recorded calls cannot silently under-report the floor's
work.

**The phone's own dialler does the recording; the app never taps the call.** No
third-party app can — the Android permission is reserved for system apps and iOS
has no API at all. [`docs/MOBILE_RECORDING.md`](docs/MOBILE_RECORDING.md) has
the filename formats, the matching rules, the `READ_CALL_LOG` distribution
caveat, and how to wire up carrier-side recording instead.

**Average call length excludes missed calls.** They have zero duration, so
folding them in would make the average fall as missed-call reporting gets more
complete — exactly backwards.

**Filler counts are computed in code; the model only judges them.** A model
asked to count produces numbers that drift between runs, and a dashboard whose
figures move when nothing changed is one nobody trusts.

**The job queue is a Postgres table, not a broker.** A call row and its pipeline
work commit together — with a separate broker a call can be marked ready while
the enqueue fails, and that recording is lost until somebody notices.

**Audio expires; insight is kept.** Recordings are purged on a retention
schedule while their transcript and analysis stay. The purged row remains so the
dashboard can explain the empty player rather than 404.

## Repository

```
backend/    FastAPI API + pipeline worker (Python 3.11)
web/        Admin dashboard (Next.js 14)
mobile/     Agent app (Expo / React Native)
docs/       Architecture, speech-model contract, mobile recording constraints
```

## Documentation

| Document | What it covers |
| -------- | -------------- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How the pieces fit, and why the awkward choices were made |
| [`docs/STT_CONTRACT.md`](docs/STT_CONTRACT.md) | Wire contract for plugging in your own speech model |
| [`docs/MOBILE_RECORDING.md`](docs/MOBILE_RECORDING.md) | What call recording on mobile can and cannot do |
| [`docs/API.md`](docs/API.md) | Endpoint reference |

## Status

Working end to end and tested — 84 backend tests covering tenant isolation, the
full pipeline, retries, policy resolution and every dashboard aggregate, plus 49
mobile tests over the recording-filename parser and the call-recording matcher.

Not yet built, and deliberately so: carrier-side recording connectors,
cross-call speaker identification, and live mid-call analysis (a different
architecture, not a setting).
