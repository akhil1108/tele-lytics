# Admin dashboard

Next.js 14 (App Router) supervisor dashboard for the Tele-lytics platform.

## Running

```bash
npm install
cp .env.example .env.local     # point NEXT_PUBLIC_API_BASE_URL at the API
npm run dev                    # http://localhost:3000
```

The API's `CORS_ORIGINS` must include this app's origin, exactly — `localhost`
and `127.0.0.1` are different origins to a browser.

## Pages

| Route        | What it is                                                        |
| ------------ | ----------------------------------------------------------------- |
| `/`          | Live floor status, call volume, sentiment, filler words, coverage  |
| `/calls`     | Filterable call list with processing state                        |
| `/calls/:id` | Player, transcript with tone, and every insight panel             |
| `/agents`    | Roster, live presence, per-agent quality, handset pairing codes   |
| `/numbers`   | Per-number recording policy, plus a live policy checker           |
| `/tasks`     | Tasks committed on calls and actions the model recommends         |

## Notes on the charts

Chart colours come from CSS custom properties in `src/styles/globals.css`, so
light and dark swap in one place. The palettes were checked with a
contrast/CVD validator rather than chosen by eye:

- **two-series** (blue, orange) — passes every gate in both modes
- **three-series** (blue, orange, aqua) — passes all-pairs; aqua falls below
  3:1 on the light surface, so those charts always carry a legend, direct
  labels and a table view
- **sentiment** — a diverging blue↔red pair with a neutral grey midpoint,
  because sentiment is polarity rather than identity

Sentiment charts show three buckets, not five: two distinct steps per arm
cannot fit the lightness band the palette holds every series to. The five-level
detail lives in the table view and the per-utterance labels, where words carry
it instead of colour.

Every chart has a table view behind the "Table" toggle — that is the
accessibility fallback for the sub-3:1 colours, and it is also just the fastest
way to read an exact figure.

## Realtime

`src/lib/realtime.ts` opens a WebSocket to `/ws/dashboard` and reconnects with
capped exponential backoff. Presence counts render from it live; a snapshot is
sent on connect so a client that joins between broadcasts is never blank.
