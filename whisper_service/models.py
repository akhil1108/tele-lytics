"""Model loading and inference: ASR (Whisper), diarization (pyannote), tone
(a speech-emotion regressor).

Every model is loaded once at process start and cached — reloading a 1-3GB
checkpoint per request would make this unusably slow. `warm_up()` is called
from `main.py`'s startup hook so the first real request isn't the one that
pays the load cost.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import torch
import torchaudio

from config import settings


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
    chunks = [
        AsrChunk(start_s=c["timestamp"][0] or 0.0, end_s=c["timestamp"][1] or 0.0, text=c["text"].strip())
        for c in result.get("chunks", [])
        if c["text"].strip()
    ]
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


def slice_waveform(waveform: torch.Tensor, sample_rate: int, start_s: float, end_s: float) -> torch.Tensor:
    start = max(0, int(start_s * sample_rate))
    end = min(waveform.shape[-1], int(end_s * sample_rate))
    if end <= start:
        return waveform[start : start + 1]
    return waveform[start:end]


def warm_up() -> None:
    """Load every model once at startup rather than on the first request."""
    _asr_pipeline()
    if settings.hf_token:
        _diarization_pipeline()
    _emotion_model()
    _translation_model()


# ------------------------------------------------------- Indic -> English


@lru_cache(maxsize=1)
def _translation_model():
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    from IndicTransToolkit.processor import IndicProcessor

    tokenizer = AutoTokenizer.from_pretrained(
        settings.indic_translation_model, trust_remote_code=True, token=settings.hf_token
    )
    model = AutoModelForSeq2SeqLM.from_pretrained(
        settings.indic_translation_model, trust_remote_code=True, token=settings.hf_token
    ).to(DEVICE).eval()
    processor = IndicProcessor(inference=True)
    return tokenizer, model, processor


# Whisper's language hint uses ISO 639-1-ish codes; IndicTrans2 wants
# FLORES-200 script-tagged codes. Only the languages Whisper actually
# recognises AND IndicTrans2's indic-en model was trained on are listed —
# a handful of IndicTrans2's low-resource languages (Bodo, Dogri, Konkani,
# Santali, ...) have no Whisper-recognised code to map from at all.
_WHISPER_TO_FLORES: dict[str, str] = {
    "as": "asm_Beng", "bn": "ben_Beng", "gu": "guj_Gujr", "hi": "hin_Deva",
    "kn": "kan_Knda", "ml": "mal_Mlym", "mr": "mar_Deva", "ne": "npi_Deva",
    "or": "ory_Orya", "pa": "pan_Guru", "sa": "san_Deva", "sd": "snd_Deva",
    "ta": "tam_Taml", "te": "tel_Telu", "ur": "urd_Arab",
}


def flores_code_for(whisper_language: str | None) -> str | None:
    """None means "don't translate" — English, or a language IndicTrans2's
    indic-en model doesn't cover."""
    if not whisper_language:
        return None
    return _WHISPER_TO_FLORES.get(whisper_language.split("-")[0].lower())


def translate_to_english(texts: list[str], src_lang: str) -> list[str]:
    """Batch-translates already-transcribed native-language text to English.

    Whole-call, not per-segment: the source language comes from the same
    hint Whisper transcribed with, so a call genuinely code-switching
    between, say, Kannada and English mid-call will have its English
    portions run back through translation too — usually a near no-op, but
    worth knowing rather than assuming this handles code-switching cleanly.
    """
    if not texts:
        return texts
    tokenizer, model, processor = _translation_model()
    batch = processor.preprocess_batch(texts, src_lang=src_lang, tgt_lang="eng_Latn")
    inputs = tokenizer(batch, padding="longest", truncation=True, max_length=256, return_tensors="pt")
    with torch.no_grad():
        generated = model.generate(**inputs.to(DEVICE), num_beams=5, max_length=256)
    decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
    return processor.postprocess_batch(decoded, lang="eng_Latn")
