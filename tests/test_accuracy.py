"""Tests for transcription tolerance: normalization, suggestions, STT options."""

import numpy as np

from talksh import stt
from talksh.config import Config
from talksh.mapper import map_intent, suggest


def test_singular_test_still_maps():
    m = map_intent("run the test for the auth module")
    assert m is not None
    assert m.command == "pytest tests/test_auth.py -v"


def test_case_and_punctuation_ignored():
    m = map_intent("Run the TESTS for the Auth Module!!!")
    assert m is not None
    assert m.command == "pytest tests/test_auth.py -v"


def test_slot_keeps_original_case():
    m = map_intent("commit with message Fix Token Refresh")
    assert m is not None
    assert m.command == 'git commit -m "Fix Token Refresh"'


def test_singular_branch_maps():
    m = map_intent("switch to branches feature-x")
    assert m is not None
    assert m.command == "git checkout feature-x"


def test_plural_form_maps():
    m = map_intent("list branch")
    assert m is not None
    assert m.command == "git branch"


def test_suggest_offers_closest_phrase():
    hints = suggest("run the disk for the auth module")
    assert hints, "expected at least one suggestion"
    assert any("pytest" in h for h in hints)


def test_suggest_empty_for_gibberish():
    assert suggest("zzz qqq xxx") == []


def test_config_default_model_is_small():
    assert Config().model == "small"


def _fake_stt(monkeypatch):
    captured = {}

    class FakeSeg:
        text = " hello "
        avg_logprob = -0.1

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            captured.update(kwargs)
            return [FakeSeg()], None

    def fake_load(model_name="small"):
        captured["model_name"] = model_name
        return FakeModel()

    monkeypatch.setattr(stt, "_load_model", fake_load)
    return captured


def test_transcribe_enables_vad_filter(monkeypatch):
    captured = _fake_stt(monkeypatch)
    text, conf = stt.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "hello"
    assert 0.0 < conf <= 1.0
    assert captured["vad_filter"] is True
    assert captured["model_name"] == "small"


def test_transcribe_language_auto_passes_none(monkeypatch):
    captured = _fake_stt(monkeypatch)
    stt.transcribe(np.zeros(16000, dtype=np.float32), language="auto")
    assert captured["language"] is None


def test_transcribe_language_en_passed_through(monkeypatch):
    captured = _fake_stt(monkeypatch)
    stt.transcribe(np.zeros(16000, dtype=np.float32), language="en")
    assert captured["language"] == "en"
