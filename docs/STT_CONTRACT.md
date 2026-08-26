# Speech model contract

Stage 1 of the pipeline sends a call recording to a speech model and expects a
transcript with per-utterance tone back. This document is the wire contract, so
that whichever model you plug in, nothing else in the platform changes.

Set `STT_PROVIDER=shared_model` and point `STT_ENDPOINT_URL` at your endpoint.

## Request

`POST <STT_ENDPOINT_URL>` as `multipart/form-data`:

| Part       | Type     | Notes                                                    |
| ---------- | -------- | -------------------------------------------------------- |
| `audio`    | file     | The recording. `m4a`, `mp3`, `wav`, `ogg`, `opus`, `amr`. |
| `metadata` | JSON string | The object below.                                     |

```json
{
  "language": "en-IN",
  "diarize": true,
  "return_tone": true,
  "speakers": 2,
  "model": "whatever STT_MODEL is set to",
  "call_id": "0b4f…",
  "direction": "inbound",
  "agent_number": "+919876543210",
  "customer_number": "+919000000001",
  "vocabulary": ["Northwind", "NW-4481"]
}
```

`Authorization: Bearer <STT_API_KEY>` is sent when `STT_API_KEY` is set.

The `agent_number` and `customer_number` are supplied because a model doing
channel- or number-aware diarisation can label the speakers correctly instead of
inferring them from voice alone. Ignore them if yours cannot.

## Response

`200 OK` with JSON:

```json
{
  "language": "en-IN",
  "model": "your-model-v2",
  "text": "full transcript, optional if segments are present",
  "confidence": 0.93,
  "duration_seconds": 184.2,
  "tone_overall": "calm",
  "segments": [
    {
      "speaker": "agent",
      "start_ms": 0,
      "end_ms": 3400,
      "text": "Good morning, thank you for calling.",
      "confidence": 0.95,
      "tone": {
        "label": "warm",
        "confidence": 0.81,
        "valence": 0.6,
        "arousal": 0.4
      }
    }
  ]
}
```

Only `segments[].text` is genuinely required — everything else improves the
output but has a sensible fallback.

### Fields

| Field                  | Meaning                                                       |
| ---------------------- | ------------------------------------------------------------- |
| `speaker`              | Who is talking. See the mapping table below.                  |
| `start_ms` / `end_ms`  | Offsets into the call. Milliseconds or fractional seconds.    |
| `text`                 | What was said, verbatim. Do not tidy it.                       |
| `confidence`           | `0`–`1`. Values outside the range are clamped.                |
| `tone.label`           | Free text: `calm`, `frustrated`, `apologetic`, `rushed`, …     |
| `tone.valence`         | `-1` (unpleasant) to `+1` (pleasant).                          |
| `tone.arousal`         | `0` (flat) to `1` (highly activated).                          |

## What the adapter tolerates

Real speech APIs disagree on nearly every field name, so the adapter maps a
range of shapes rather than demanding one. You will usually not need to change
your model's output at all.

| We look for       | Also accepted                                                    |
| ----------------- | ---------------------------------------------------------------- |
| `segments`        | `results`, `chunks`, `utterances`, `turns`                        |
| `text`            | `transcript`, `content`, `value`                                  |
| `start_ms`        | `start`, `begin`, `from`, `offset`                                |
| `end_ms`          | `end`, `stop`, `to`                                               |
| `confidence`      | `score`, `probability`                                            |
| `tone`            | `emotion`, `affect`, `prosody`, `sentiment`                       |
| `speaker`         | `speaker_label`, `channel`, `speaker_id`                          |
| `model`           | `model_name`, `engine`                                            |

Also handled:

- **Seconds or milliseconds.** A float is read as seconds; an integer below
  1000 is read as seconds too, because no real segment starts 30 ms into a call
  on a whole number, while "starts at second 12" is everywhere.
- **A wrapper object.** A payload nested under `result`, `data`, `response` or
  `output` is unwrapped.
- **Emotion as a ranked list.** `[{"label": "calm", "score": 0.6}, …]` takes the
  highest-scoring entry.
- **Segments as bare strings.** `{"chunks": ["one", "two"]}` works, without
  timings.
- **Out-of-range scores.** Clamped rather than rejected.

### Speaker mapping

| Your value                                          | Mapped to  |
| --------------------------------------------------- | ---------- |
| `agent`, `rep`, `representative`, `operator`, `local`| `agent`    |
| `customer`, `client`, `caller`, `callee`, `remote`   | `customer` |
| `0`, `SPEAKER_00`, `channel 0`                       | `agent`    |
| any other number                                     | `customer` |
| anything else                                        | `unknown`  |

Channel 0 maps to the agent by convention: the handset holder is the near end.

## Errors

| Status  | Treated as                                                        |
| ------- | ----------------------------------------------------------------- |
| `2xx` with no usable text | Permanent failure — the job is not retried.     |
| `4xx`   | Permanent failure. Retrying sends the same bytes to the same model. |
| `5xx`   | Transient. Retried with backoff (30s, 2m, 10m).                    |
| timeout | Transient. `STT_TIMEOUT_SECONDS` defaults to 900.                  |

Anything the adapter did not recognise is preserved in `transcripts.raw`, so no
information from your model is lost even when it is not mapped.

## Testing your endpoint

The parser is exercised directly, without a server, in
`backend/tests/test_units.py` (`test_parses_whisper_style_seconds_and_speaker_labels`
and the tests around it). Add a case with your model's real response shape and
you will know it maps correctly before wiring anything up.
