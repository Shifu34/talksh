"""Speech-to-text via faster-whisper, loaded lazily.

The model is heavy (tens to hundreds of MB), so nothing is imported or
downloaded until the first transcription. `transcribe()` is the only
entry point the CLI needs.
"""

from __future__ import annotations

import numpy as np

_model = None
_model_name: str | None = None


def _load_model(model_name: str = "base"):
    global _model, _model_name
    if _model is not None and _model_name == model_name:
        return _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install it with `pip install faster-whisper`."
        ) from exc
    # TODO: expose compute_type ("int8" for CPU) and device via config.
    _model = WhisperModel(model_name, device="cpu", compute_type="int8")
    _model_name = model_name
    return _model


def transcribe(
    audio: np.ndarray,
    model_name: str = "small",
    language: str | None = "en",
) -> tuple[str, float]:
    """Transcribe float32 mono audio at 16kHz.

    Returns (text, confidence). Confidence is the average logprob-based
    score mapped to 0..1; treat it as relative, not absolute.

    language="auto" (or None) lets the model detect the language instead
    of assuming English.
    """
    model = _load_model(model_name)
    segments, info = model.transcribe(
        audio,
        language=None if language in (None, "auto") else language,
        beam_size=5,
        # Skip silence: avoids hallucinating words like "you" over pauses
        # and keeps the model focused on actual speech.
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    texts: list[str] = []
    probs: list[float] = []
    for seg in segments:
        texts.append(seg.text.strip())
        # avg_logprob is negative; map roughly to 0..1
        probs.append(max(0.0, min(1.0, 1.0 + seg.avg_logprob)))
    text = " ".join(texts).strip()
    confidence = sum(probs) / len(probs) if probs else 0.0
    return text, confidence
