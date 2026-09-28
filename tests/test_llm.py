"""Tests for the optional LLM command generation (mocked HTTP, no network)."""

import io
import json
import urllib.error

import pytest

from talksh.config import Config
from talksh.llm import (
    DEFAULT_BASE_URL,
    generate_command,
    LLMConfig,
    resolve_command,
    resolve_llm_config,
)


class FakeResponse:
    """Minimal stand-in for the urllib response context manager."""

    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _completion(content: str) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"content": content}}]}
    ).encode("utf-8")


def _llm(api_key="sk-test-key"):
    return LLMConfig(api_key=api_key)


# --- resolve_llm_config ----------------------------------------------------


def test_no_key_anywhere_gives_none(monkeypatch):
    monkeypatch.delenv("TALKSH_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert resolve_llm_config(Config()) is None


def test_env_var_key_is_used(monkeypatch):
    monkeypatch.setenv("TALKSH_API_KEY", "sk-from-env")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm = resolve_llm_config(Config())
    assert llm is not None
    assert llm.model == "gpt-4o-mini"
    assert llm.base_url == DEFAULT_BASE_URL


def test_openai_env_fallback(monkeypatch):
    monkeypatch.delenv("TALKSH_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fallback")
    llm = resolve_llm_config(Config())
    assert llm is not None


def test_config_file_key_beats_env(monkeypatch):
    monkeypatch.setenv("TALKSH_API_KEY", "sk-from-env")
    cfg = Config()
    cfg.llm.api_key = "sk-from-config"
    llm = resolve_llm_config(cfg)
    assert llm is not None
    # config value wins; env is only a fallback
    assert llm.api_key == "sk-from-config"


def test_talksh_env_beats_openai_env(monkeypatch):
    monkeypatch.setenv("TALKSH_API_KEY", "sk-talksh")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    llm = resolve_llm_config(Config())
    assert llm is not None
    assert llm.api_key == "sk-talksh"


# --- generate_command -------------------------------------------------------


def test_generate_command_success(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(_completion("git status --short"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cmd = generate_command("show me what changed", _llm())
    assert cmd == "git status --short"
    assert seen["url"] == DEFAULT_BASE_URL + "/chat/completions"
    assert seen["auth"] == "Bearer sk-test-key"
    assert seen["body"]["model"] == "gpt-4o-mini"
    assert seen["body"]["messages"][1]["content"] == "show me what changed"


def test_generate_command_strips_formatting(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(_completion('```bash\ngit status\n```'))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert generate_command("status", _llm()) == "git status"


def test_generate_command_network_failure_returns_none(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert generate_command("status", _llm()) is None


def test_generate_command_bad_json_returns_none(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(b"not json at all")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert generate_command("status", _llm()) is None


def test_generate_command_empty_content_returns_none(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(_completion("   "))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert generate_command("status", _llm()) is None


def test_api_key_never_printed(monkeypatch, capsys):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(_completion("git status"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    generate_command("status", _llm(api_key="sk-super-secret-xyz"))
    out, err = capsys.readouterr()
    assert "sk-super-secret-xyz" not in out
    assert "sk-super-secret-xyz" not in err


# --- resolve_command (LLM first, local fallback) ------------------------------


def _no_env(monkeypatch):
    monkeypatch.delenv("TALKSH_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_no_key_uses_local_mapper(monkeypatch):
    _no_env(monkeypatch)
    match, via = resolve_command("git status", Config())
    assert via == "local"
    assert match is not None
    assert match.command == "git status"
    assert match.source == "builtin"


def test_llm_success_beats_mapper(monkeypatch):
    monkeypatch.setenv("TALKSH_API_KEY", "sk-test")

    def fake_urlopen(request, timeout=None):
        return FakeResponse(_completion("kubectl get pods -A"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    match, via = resolve_command("show me all pods everywhere", Config())
    assert via == "llm"
    assert match is not None
    assert match.command == "kubectl get pods -A"
    assert match.source == "llm"


def test_llm_failure_falls_back_to_mapper(monkeypatch):
    monkeypatch.setenv("TALKSH_API_KEY", "sk-test")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    match, via = resolve_command("git status", Config())
    assert via == "local"
    assert match is not None
    assert match.command == "git status"


def test_no_llm_flag_forces_local_even_with_key(monkeypatch):
    monkeypatch.setenv("TALKSH_API_KEY", "sk-test")

    def fake_urlopen(request, timeout=None):
        raise AssertionError("LLM should not be called with --no-llm")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    match, via = resolve_command("git status", Config(), no_llm=True)
    assert via == "local"
    assert match is not None
    assert match.command == "git status"


def test_llm_command_still_blocked_by_executor():
    # The safety path is shared: an LLM answer of "rm -rf /" must be refused.
    from talksh.executor import is_blocked

    assert is_blocked("rm -rf /")
