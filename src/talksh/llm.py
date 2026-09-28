"""Optional LLM command generation for talksh.

When an API key is configured (config file or environment variable), the
transcribed text is sent to an OpenAI-compatible chat completions endpoint
which returns a single shell command. When no key is configured, or the
LLM call fails for any reason, the caller falls back to the local intent
mapper instead of crashing.

The HTTP call uses only the standard library (urllib), so this adds no
new dependency. The API key is never logged or printed anywhere.

LLM-produced commands go through the exact same executor safety path as
mapped ones: blocklist refusal, typed-yes for destructive commands, and
--dry-run support.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from talksh.config import Config
from talksh.mapper import Match, map_intent

SYSTEM_PROMPT = (
    "You translate a developer's spoken request into a single shell command. "
    "Output ONLY the raw shell command: no quotes around it, no code fences, "
    "no markdown, no explanation, no trailing commentary. If the request is "
    "ambiguous, output the single most likely command."
)

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass
class LLMConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL


def resolve_llm_config(cfg: Config) -> LLMConfig | None:
    """Find the LLM settings, or None when no API key is available.

    Precedence: api_key in the config file wins, then the TALKSH_API_KEY
    environment variable, then OPENAI_API_KEY.
    """
    key = (
        cfg.llm.api_key
        or os.environ.get("TALKSH_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not key:
        return None
    return LLMConfig(api_key=key, model=cfg.llm.model, base_url=cfg.llm.base_url)


def _clean_command(text: str) -> str:
    """Strip markdown fences (and language tags like ```bash), quotes, and
    stray whitespace so only the raw command remains."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # opening fence, possibly with a language tag
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # closing fence
        text = "\n".join(lines)
    return text.strip("`\"' \t\n")


def generate_command(transcript: str, llm: LLMConfig, timeout: float = 15.0) -> str | None:
    """Ask the LLM to turn the transcript into one shell command.

    Returns the command string, or None on any failure (network error,
    bad key, timeout, unexpected response). The caller falls back to the
    local mapper when this returns None.
    """
    body = json.dumps(
        {
            "model": llm.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            "temperature": 0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        llm.base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["choices"][0]["message"]["content"].strip()
    except Exception:
        # Any failure (DNS, timeout, 401, bad JSON, ...) means fall back
        # to the local mapper. Never crash on the LLM path.
        return None
    return _clean_command(text) or None


def resolve_command(
    transcript: str, cfg: Config, no_llm: bool = False
) -> tuple[Match | None, str]:
    """Turn a transcript into a command.

    Tries the LLM first when a key is configured (unless no_llm is set),
    otherwise uses the local intent mapper. Returns (match, source) where
    source is "llm", "local", or "none".
    """
    if not no_llm:
        llm = resolve_llm_config(cfg)
        if llm is not None:
            command = generate_command(transcript, llm)
            if command:
                return Match(command=command, confidence=0.85, source="llm"), "llm"
    match = map_intent(transcript, cfg.aliases)
    return match, ("local" if match else "none")
