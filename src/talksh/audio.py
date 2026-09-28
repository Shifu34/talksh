"""Microphone capture.

Uses sounddevice when available. On machines without audio hardware (CI,
servers, containers) the import fails gracefully and recording raises a
clear error instead of crashing at import time.
"""

from __future__ import annotations

import numpy as np

try:
    import sounddevice as sd

    _AUDIO_AVAILABLE = True
    _AUDIO_ERROR: str | None = None
except Exception as exc:  # sounddevice needs PortAudio system libs
    sd = None  # type: ignore
    _AUDIO_AVAILABLE = False
    _AUDIO_ERROR = str(exc)

SAMPLE_RATE = 16_000  # Whisper-native sample rate


def audio_available() -> bool:
    return _AUDIO_AVAILABLE


def record(seconds: float = 5.0, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Record `seconds` of mono audio from the default mic.

    Returns float32 samples in [-1, 1].
    Raises RuntimeError when audio capture is unavailable.
    """
    if not _AUDIO_AVAILABLE:
        raise RuntimeError(
            "Audio capture is unavailable"
            + (f": {_AUDIO_ERROR}" if _AUDIO_ERROR else "")
            + ". On Linux install PortAudio (e.g. `apt install libportaudio2`), "
            "or use `talksh --demo` for a simulated run."
        )
    frames = int(seconds * sample_rate)
    # TODO: support device selection via --device and config `input_device`.
    recording = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    return recording.reshape(-1)


def list_devices() -> list[str]:
    """Human-readable list of input devices, empty when unavailable."""
    if not _AUDIO_AVAILABLE:
        return []
    # TODO: surface this via `talksh --list-devices`.
    return [str(d["name"]) for d in sd.query_devices() if d["max_input_channels"] > 0]
