"""Configuration loading for talksh.

Reads ~/.talksh.yaml when present and merges it over sane defaults.
Everything here is optional; talksh works fine with no config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a hard dependency
    yaml = None

DEFAULT_CONFIG_PATH = Path.home() / ".talksh.yaml"


@dataclass
class LLMSettings:
    """Optional LLM command generation.

    api_key can also come from the TALKSH_API_KEY or OPENAI_API_KEY
    environment variables. Precedence: config file api_key first, then
    TALKSH_API_KEY, then OPENAI_API_KEY. With no key anywhere, talksh
    uses the local intent mapper only.
    """

    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"


@dataclass
class Config:
    hotkey: str = "ctrl+alt+v"
    # tiny, base, small, medium, large-v3 (faster-whisper). small is the
    # sweet spot: much better with accents than base, still fast on CPU.
    # Set language to "auto" for non-English or mixed speech.
    model: str = "small"
    language: str = "en"
    confirm_destructive: bool = True
    aliases: dict[str, str] = field(default_factory=dict)
    llm: LLMSettings = field(default_factory=LLMSettings)

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Config":
        """Load config from path (default ~/.talksh.yaml), merged over defaults."""
        cfg = cls()
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not cfg_path.exists() or yaml is None:
            return cfg
        try:
            raw = yaml.safe_load(cfg_path.read_text()) or {}
        except Exception:
            # A broken config should never break the tool; fall back to defaults.
            return cfg
        if not isinstance(raw, dict):
            return cfg
        for key in ("hotkey", "model", "language", "confirm_destructive"):
            if key in raw:
                setattr(cfg, key, raw[key])
        aliases = raw.get("aliases")
        if isinstance(aliases, dict):
            cfg.aliases = {str(k): str(v) for k, v in aliases.items()}
        llm_raw = raw.get("llm")
        if isinstance(llm_raw, dict):
            llm = LLMSettings()
            for key in ("api_key", "model", "base_url"):
                if llm_raw.get(key):
                    setattr(llm, key, str(llm_raw[key]))
            cfg.llm = llm
        return cfg
