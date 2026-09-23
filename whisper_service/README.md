# Whisper inference service

Speech-to-text for the dashboard's pipeline, implementing
[`docs/STT_CONTRACT.md`](../docs/STT_CONTRACT.md) so it plugs into
`STT_PROVIDER=shared_model` with zero changes to `backend/`.

Four models, one HTTP endpoint:

| Job | Model | Why |
| --- | --- | --- |
| Transcription | [`openai/whisper-large-v3-turbo`](https://huggingface.co/openai/whisper-large-v3-turbo) | 99-language coverage (matters for `en-IN` code-switching), ~8x faster decode than large-v3 for a small accuracy tradeoff |
| Speaker diarisation | [`pyannote/speaker-diarization-3.1`](https://huggingface.co/pyannote/speaker-diarization-3.1) | Whisper alone has no speaker concept; call recordings are mono, so this is what tells agent from customer |
| Tone | [`superb/wav2vec2-base-superb-er`](https://huggingface.co/superb/wav2vec2-base-superb-er) | Discrete label + confidence maps directly onto `tone.label` — the field the transcript view actually renders. (An earlier pick, `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition`, silently fails to load its classifier head via `AutoModelForAudioClassification` — the checkpoint's weight names don't match the standard head, so it scores on randomly-initialised weights. Watch the startup log for "weights ... newly initialized" if you swap emotion models — that warning means the same failure.) |
| Non-English → English translation | OpenAI's hosted Whisper (`whisper-1`, via `client.audio.translations.create`) | Runs whenever `metadata.language` isn't English, and *replaces* local transcription for that call rather than running after it. Deliberately not a local model: our local Whisper romanizes code-switched Indian-language speech (Latin script, e.g. "agi dhe" rather than ಆಗಿದೆ), and every local text-translation model tried expects native script as input — they silently no-op on romanized text instead of translating it. One call over the whole recording, not per segment: an earlier per-segment version lost cross-segment context, and short/ambiguous clips translated worse than local Whisper's own same-language read of them. `response_format="verbose_json"` gives back real per-segment timestamps *and* an `avg_logprob`-derived confidence in the same call — solving two problems (translation quality, missing ASR confidence) at once. Falls back to local transcription if the API is unreachable or `OPENAI_API_KEY` isn't set, so a call still gets *a* transcript either way. |

## Setup

1. **Accept both gated models' terms**, logged in, or startup fails with a
   `GatedRepoError` (diarisation pulls in a second gated model under the hood
   for segmentation):
   - <https://huggingface.co/pyannote/speaker-diarization-3.1>
   - <https://huggingface.co/pyannote/segmentation-3.0>
2. **Get an HF token** with read access at
   <https://huggingface.co/settings/tokens>, and — if you'll send calls with
   a non-English language hint — an OpenAI key at
   <https://platform.openai.com/api-keys>.
3. **Install `ffmpeg`** if running outside Docker (`brew install ffmpeg` /
   `apt-get install ffmpeg`) — it normalises whatever audio format arrives to
   16kHz mono WAV before either model sees it.
4. **Point at your fine-tuned checkpoint, if you have one.** `whisper_model`
   accepts a local path just as well as a Hub id — e.g. the folder you
   `hf-mount` a checkpoint into:
   ```
   WHISPER_MODEL=./local
   ```

## Running locally

```bash
cd whisper_service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export HF_TOKEN=hf_...          # for the gated diarisation model
uvicorn main:app --host 0.0.0.0 --port 8001
```

First request is slow — that's the ~3GB of model weights downloading and
loading onto the device. Subsequent requests reuse the cached, loaded models.

Then, in the main repo's `.env`:

```
STT_PROVIDER=shared_model
STT_ENDPOINT_URL=http://localhost:8001/transcribe
STT_MODEL=openai/whisper-large-v3-turbo
```

## Running in Docker

```bash
docker build -t whisper-service .
docker run -p 8001:8001 -e HF_TOKEN=hf_... -v hf-cache:/data/hf-cache whisper-service
```

The `hf-cache` volume keeps downloaded model weights across container
restarts — without it, every restart re-downloads ~3GB.

## Hardware

CPU works but is slow — expect large-v3-turbo to run noticeably slower than
real-time on CPU alone, before diarisation and tone scoring are even added.
For real call-centre volume, use:

- **A CUDA GPU** (8GB+ VRAM comfortable for all three models) — set
  `torch`/`torchaudio` to a CUDA build per the comment in
  `requirements.txt`.
- **Apple Silicon**, for local dev only — `DEVICE=mps` picks up the GPU via
  PyTorch's MPS backend. Noticeably faster than CPU here, though pyannote's
  MPS support is less mature than CUDA's; fall back to `DEVICE=cpu` for
  diarisation specifically if you hit odd errors there.

`DEVICE=auto` (the default) picks the best available automatically.

## Known limitations of this scaffold

- **No per-segment ASR confidence on the local (untranslated) path.**
  Getting a real token-level confidence out of `transformers`' `pipeline()`
  needs the lower-level `model.generate(output_scores=True,
  return_dict_in_generate=True)` call instead of the high-level pipeline.
  Confidence is optional in the contract, so local-Whisper segments are
  returned without it — the adapter's fallback handles this fine. Translated
  calls *do* get a real confidence, from OpenAI's `avg_logprob`.
- **Diarisation and tone run per-ASR-chunk**, not on a fully independent
  timeline — accurate enough for typical two-party calls, but if a chunk's
  boundaries drift on a long utterance, speaker attribution can drift with
  them. See the main answer this scaffold came out of for the WhisperX
  alternative (forced word-level alignment) if that matters for you.
- **Tone's valence/arousal are a fixed lookup from the discrete label**, not
  measured — see `_EMOTION_VALENCE_AROUSAL` in `models.py`. `tone.label` is
  the real signal here.
- **Translation makes one OpenAI API call per recording**, not per segment —
  an earlier per-segment version was tried and reverted (see git history):
  it lost cross-segment context, and short/ambiguous clips translated worse
  than local Whisper's own same-language read of them. One call over the
  whole recording keeps that context. Still real added latency (a network
  round trip plus OpenAI's own processing time) and real per-call cost on
  top of diarisation + tone already running locally. Tested end to end
  against a real ~85-second, 26-segment Kannada/English recording (19.7s
  total — 4x faster than realtime) — worth testing your own typical call
  length and volume before assuming this scales without a queue.
- **Any non-English hint triggers translation, with no confidence gate.**
  `needs_translation` just checks the language isn't `"en"` — it doesn't
  verify the audio is actually in that language. Forcing the wrong hint on
  genuinely English audio measurably degrades output (confirmed: forcing a
  Kannada hint on an English test clip produced a worse transcript than
  letting Whisper auto-detect). Set `metadata.language` to what's actually
  spoken, not a default guess.
- **No native-language transcript is kept once translation runs.** Earlier
  versions surfaced the pre-translation text as `original_text` for
  audit/QA; that's gone now that translation replaces local transcription
  outright rather than running after it. If you want both, that's one more
  API call — `client.audio.transcriptions.create(language=...)` alongside
  the translations call — not currently wired up.
