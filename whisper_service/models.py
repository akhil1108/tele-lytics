"""Model loading and inference: ASR (Whisper), diarization (pyannote), tone
(a speech-emotion regressor).

Every model is loaded once at process start and cached — reloading a 1-3GB
checkpoint per request would make this unusably slow. `warm_up()` is called
from `main.py`'s startup hook so the first real request isn't the one that
pays the load cost.
"""

from __future__ import annotations

import logging
import math
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import torch
import torchaudio

from config import settings

log = logging.getLogger(__name__)


def _resolve_device() -> str:
    if settings.device != "auto":
        return settings.device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


DEVICE = _resolve_device()


# --------------------------------------------------------------- ASR (stage 1a)


@lru_cache(maxsize=1)
def _asr_pipeline():
    from transformers import pipeline

    return pipeline(
        "automatic-speech-recognition",
        model=settings.whisper_model,
        torch_dtype=torch.float16 if DEVICE != "cpu" else torch.float32,
        device=DEVICE,
        chunk_length_s=30,
        return_timestamps=True,
    )


@dataclass
class AsrChunk:
    start_s: float
    end_s: float
    text: str
    # None for local Whisper (the high-level pipeline() API doesn't expose
    # per-chunk confidence without dropping to a lower-level generate()
    # call); populated from OpenAI's avg_logprob when translation runs.
    confidence: float | None = None


def transcribe(wav_path: str, *, language: str | None, vocabulary: list[str]) -> tuple[str, list[AsrChunk]]:
    """Full text plus timestamped chunks. `language` is a hint, not a hard constraint —
    Whisper still auto-detects if it disagrees strongly with the audio."""
    generate_kwargs: dict = {"task": "transcribe"}
    if language:
        # Whisper wants a bare language name/code, not a locale like "en-IN".
        generate_kwargs["language"] = language.split("-")[0]

    asr = _asr_pipeline()
    if vocabulary:
        # Best-effort vocabulary boost via an initial prompt. Silently skipped
        # on transformers versions where get_prompt_ids isn't available —
        # domain vocabulary (product names, order-code formats) helps but
        # isn't required for the contract.
        try:
            prompt_ids = asr.tokenizer.get_prompt_ids(", ".join(vocabulary), return_tensors="pt")
            generate_kwargs["prompt_ids"] = prompt_ids
        except Exception:
            pass

    result = asr(wav_path, generate_kwargs=generate_kwargs)
    chunks = []
    for c in result.get("chunks", []):
        text = c["text"].strip()
        if not text:
            continue
        start_s = c["timestamp"][0] or 0.0
        # Whisper sometimes can't predict an ending timestamp — cut off mid-
        # word, or trailing into silence/noise it's hallucinating a
        # repetition loop over. Falling back to a hardcoded 0.0 here used to
        # produce end_s < start_s, an inverted range that broke diarization
        # overlap-matching and fed a near-empty audio slice to the tone
        # model. Falling back to start_s instead keeps it a valid
        # (zero-length) segment, which slice_waveform already pads safely.
        end_s = c["timestamp"][1]
        end_s = end_s if end_s is not None else start_s
        chunks.append(AsrChunk(start_s=start_s, end_s=end_s, text=text))
    return result.get("text", "").strip(), chunks


# ---------------------------------------------------------- diarization (1b)


@lru_cache(maxsize=1)
def _diarization_pipeline():
    from pyannote.audio import Pipeline

    if not settings.hf_token:
        raise RuntimeError(
            "HF_TOKEN is required to load pyannote/speaker-diarization-3.1 — "
            "accept its terms at huggingface.co/pyannote/speaker-diarization-3.1 first"
        )
    pipeline = Pipeline.from_pretrained(settings.diarization_model, use_auth_token=settings.hf_token)
    if DEVICE != "cpu":
        pipeline.to(torch.device(DEVICE))
    return pipeline


@dataclass
class Turn:
    start_s: float
    end_s: float
    speaker: str  # "SPEAKER_00", "SPEAKER_01", ... — the adapter maps these by number


def diarize(wav_path: str, *, num_speakers: int | None) -> list[Turn]:
    pipeline = _diarization_pipeline()
    annotation = pipeline(wav_path, num_speakers=num_speakers)
    return [
        Turn(start_s=segment.start, end_s=segment.end, speaker=label)
        for segment, _, label in annotation.itertracks(yield_label=True)
    ]


def roles_for(turns: list[Turn]) -> dict[str, str]:
    """Maps pyannote's arbitrary `SPEAKER_NN` labels to agent/customer.

    pyannote assigns numbers by internal clustering order, not by channel —
    on mono audio there is no "channel 0 is the agent" signal to read, unlike
    the numeric-speaker convention `shared_model.py`'s generic adapter falls
    back to. What we *do* know about a contact-centre call: the agent speaks
    the opening greeting, inbound or outbound. So whichever diarized speaker
    talks first is labelled "agent" here, at the source, rather than leaving
    it to the adapter's channel-oriented guess downstream.
    """
    if not turns:
        return {}
    first_speaker = min(turns, key=lambda t: t.start_s).speaker
    return {
        turn.speaker: "agent" if turn.speaker == first_speaker else "customer"
        for turn in turns
    }


def speaker_for(turns: list[Turn], roles: dict[str, str], start_s: float, end_s: float) -> str:
    """Whichever diarized turn overlaps this ASR chunk the most, as a role."""
    best_speaker, best_overlap = None, 0.0
    for turn in turns:
        overlap = min(end_s, turn.end_s) - max(start_s, turn.start_s)
        if overlap > best_overlap:
            best_overlap, best_speaker = overlap, turn.speaker
    return roles.get(best_speaker, "unknown")


# ----------------------------------------------------------------- tone (1c)


@lru_cache(maxsize=1)
def _emotion_model():
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

    extractor = AutoFeatureExtractor.from_pretrained(settings.emotion_model)
    model = AutoModelForAudioClassification.from_pretrained(settings.emotion_model).to(DEVICE).eval()
    return extractor, model


@dataclass
class Tone:
    label: str
    confidence: float
    valence: float  # -1 (unpleasant) .. +1 (pleasant) — matches STT_CONTRACT.md
    arousal: float  # 0 (flat) .. 1 (highly activated)


# This checkpoint classifies discrete emotions (trained on IEMOCAP: neutral/
# happy/angry/sad) rather than regressing valence/arousal directly, so the
# contract's two numeric fields are a fixed lookup from the label —
# approximate psychological circumplex-model placements, not a measurement.
# `tone.label` is what the dashboard actually displays; these numbers are the
# "nice to have" extra. Swap this table (and EMOTION_MODEL) together if you
# change checkpoints — it's keyed to this model's exact label set.
_EMOTION_VALENCE_AROUSAL: dict[str, tuple[float, float]] = {
    "neu": (0.0, 0.3),
    "hap": (0.8, 0.7),
    "ang": (-0.8, 0.85),
    "sad": (-0.6, 0.25),
}
# The contract's `tone.label` is free text meant to read like "calm" or
# "frustrated" — this checkpoint's raw 3-letter IEMOCAP codes aren't that.
_EMOTION_LABEL_WORDS = {"neu": "neutral", "hap": "happy", "ang": "angry", "sad": "sad"}


def score_tone(waveform: torch.Tensor, sample_rate: int) -> Tone:
    """Runs the emotion classifier over one already-sliced segment of audio."""
    extractor, model = _emotion_model()
    inputs = extractor(waveform.numpy(), sampling_rate=sample_rate, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values.to(DEVICE)).logits
        probs = torch.softmax(logits, dim=-1)[0]

    top_idx = int(probs.argmax())
    raw_label = model.config.id2label[top_idx].lower()
    confidence = float(probs[top_idx])
    valence, arousal = _EMOTION_VALENCE_AROUSAL.get(raw_label, (0.0, 0.3))
    label = _EMOTION_LABEL_WORDS.get(raw_label, raw_label)
    return Tone(label=label, confidence=confidence, valence=valence, arousal=arousal)


# -------------------------------------------------------------- audio decode


def decode_to_wav(raw_bytes: bytes, suffix: str) -> str:
    """Normalises whatever format arrived (m4a/mp3/ogg/opus/amr/wav) to 16kHz
    mono WAV — what both Whisper and pyannote expect. Requires `ffmpeg` on PATH.
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(raw_bytes)
        src_path = src.name

    wav_path = str(Path(tempfile.mkdtemp()) / "audio.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", wav_path],
            check=True, capture_output=True, timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed to decode audio: {exc.stderr.decode()[:400]}") from exc
    finally:
        Path(src_path).unlink(missing_ok=True)
    return wav_path


def load_waveform(wav_path: str) -> tuple[torch.Tensor, int]:
    waveform, sample_rate = torchaudio.load(wav_path)
    return waveform.mean(dim=0), sample_rate  # mono


# wav2vec2-style conv stacks need a few hundred samples of real signal before
# their kernels fit at all; 1600 (100ms at 16kHz) is comfortable headroom.
# A very short ASR chunk — or the degenerate start==end case below — would
# otherwise crash the tone model with a "kernel size > input size" error.
_MIN_TONE_SAMPLES = 1600


def slice_waveform(waveform: torch.Tensor, sample_rate: int, start_s: float, end_s: float) -> torch.Tensor:
    start = max(0, int(start_s * sample_rate))
    end = min(waveform.shape[-1], int(end_s * sample_rate))
    if end <= start:
        end = start + 1
    segment = waveform[start:end]
    if segment.shape[-1] < _MIN_TONE_SAMPLES:
        segment = torch.nn.functional.pad(segment, (0, _MIN_TONE_SAMPLES - segment.shape[-1]))
    return segment


def warm_up() -> None:
    """Load every model once at startup rather than on the first request."""
    _asr_pipeline()
    if settings.hf_token:
        _diarization_pipeline()
    _emotion_model()


# ------------------------------------------------------- Indic -> English


def needs_translation(whisper_language: str | None) -> bool:
    """Any non-English language hint warrants a translation pass.

    No fixed language allowlist: unlike the local text-translation model
    this replaced, OpenAI's translation endpoint isn't limited to a specific
    set of Indic languages, so there's nothing narrower to check against.
    """
    if not whisper_language:
        return False
    return whisper_language.split("-")[0].lower() != "en"


@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured; set it or omit a non-English "
            "language hint to skip translation"
        )
    return OpenAI(api_key=settings.openai_api_key)


def translate_full_call(wav_path: str) -> tuple[str, list[AsrChunk]] | None:
    """Translates the whole recording to English in one call, replacing
    local Whisper's transcription step entirely when this runs.

    Whole-call, not per-segment, deliberately: an earlier per-segment
    version sent each ASR chunk's audio to OpenAI in isolation, and short,
    ambiguous clips (under ~1s) translated worse than local Whisper's own
    same-language read of them, because the model had no surrounding
    conversation to disambiguate against. One call over the full audio
    keeps that context, and `response_format="verbose_json"` gives back
    real per-segment timestamps *and* an avg_logprob-derived confidence in
    the same response — solving two problems at once.

    Returns None on any failure (missing key, API error) so the caller can
    fall back to local (untranslated) transcription rather than losing the
    call entirely.
    """
    try:
        client = _openai_client()
    except RuntimeError as exc:
        log.warning("translation skipped: %s", exc)
        return None

    try:
        with open(wav_path, "rb") as f:
            response = client.audio.translations.create(
                model=settings.openai_translation_model,
                file=f,
                response_format="verbose_json",
            )
    except Exception:
        log.exception("OpenAI translation call failed")
        return None

    chunks = [
        AsrChunk(
            start_s=seg.start,
            end_s=seg.end,
            text=seg.text.strip(),
            # avg_logprob is a per-token log-probability, not itself a 0..1
            # confidence — exponentiating gives a reasonable proxy, clamped
            # to guard against float edge cases at the extremes.
            confidence=max(0.0, min(1.0, math.exp(seg.avg_logprob))),
        )
        for seg in response.segments
        if seg.text.strip()
    ]
    return response.text.strip(), chunks
