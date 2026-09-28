"""Intent mapping: natural language -> shell command.

Two layers, in order:
1. Built-in intents (regex patterns for common developer commands),
   first the hand-tuned core, then the large phrase table in intents.py.
2. User aliases from ~/.talksh.yaml, matched fuzzily.

Every match returns a confidence score between 0 and 1. The caller
decides what to do with low-confidence matches (ask, suggest, or refuse).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from talksh.intents import INTENTS


@dataclass
class Match:
    command: str
    confidence: float
    source: str  # "builtin" or "alias"


# Each builtin is (compiled pattern, command builder, base confidence).
# Builders receive the regex match object.
_BUILTINS: list[tuple[re.Pattern, object, float]] = []


def _builtin(pattern: str, confidence: float = 0.9):
    def deco(fn):
        _BUILTINS.append((re.compile(pattern, re.IGNORECASE), fn, confidence))
        return fn

    return deco


@_builtin(r"^run (?:the )?tests(?: for (?:the )?(.+?)(?: module)?)?$", 0.92)
def _run_tests(m: re.Match) -> str:
    target = (m.group(1) or "").strip()
    if not target:
        return "pytest"
    # "auth module" -> tests/test_auth.py ; leave dotted paths alone
    slug = target.replace(" ", "_").lower()
    path = slug if "/" in slug or slug.endswith(".py") else f"tests/test_{slug}.py"
    return f"pytest {path} -v"


@_builtin(r"^git status$", 0.98)
def _git_status(m: re.Match) -> str:
    return "git status"


@_builtin(r"^(?:commit|commit changes)(?: with message (.+))?$", 0.9)
def _git_commit(m: re.Match) -> str:
    msg = (m.group(1) or "").strip().strip("\"'")
    if msg:
        return f'git commit -m "{msg}"'
    return "git commit"


@_builtin(r"^(?:start|run)(?: the)? server$", 0.85)
def _run_server(m: re.Match) -> str:
    return "python -m http.server"


@_builtin(r"^docker compose up$", 0.95)
def _compose_up(m: re.Match) -> str:
    return "docker compose up -d"


@_builtin(r"^list files$", 0.95)
def _list_files(m: re.Match) -> str:
    return "ls -la"


def _fuzzy_score(a: str, b: str) -> float:
    """Token-aware similarity: 1.0 for exact, lower for partial overlap."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


_SLOT_TOKEN = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def compile_phrase(phrase: str) -> re.Pattern:
    """Compile a phrase template like "commit with message {message}" into a
    case-insensitive regex. {slot} captures free text; everything else is
    matched literally."""
    parts: list[str] = []
    last = 0
    for m in _SLOT_TOKEN.finditer(phrase):
        parts.append(re.escape(phrase[last : m.start()]))
        parts.append(f"(?P<{m.group(1)}>.+)")
        last = m.end()
    parts.append(re.escape(phrase[last:]))
    return re.compile("^" + "".join(parts) + "$", re.IGNORECASE)


def _fill_template(template: str, groups: dict[str, str]) -> str:
    """Fill {slot} placeholders in a command template from regex groups."""
    out = template
    for name, value in groups.items():
        out = out.replace("{" + name + "}", (value or "").strip())
    return out


def _literal_words(phrase: str) -> int:
    """Number of non-slot words in a phrase template. Used to try more
    specific phrases before generic ones ("restart deployment {name}"
    beats "restart {service}")."""
    return len(_SLOT_TOKEN.sub(" ", phrase).split())


def _register_table() -> None:
    """Append the phrase table to the builtin registry, after the core.

    Phrases are tried most-specific-first so a generic pattern like
    "process {name}" never shadows "process on port {port}". Ties keep
    file order."""
    pairs: list[tuple[int, int, str, str, float]] = []
    for order, (phrases, command_template, confidence) in enumerate(INTENTS):
        for phrase in phrases:
            pairs.append((order, phrase, command_template, confidence))
    pairs.sort(key=lambda p: (-_literal_words(p[1]), p[0]))
    for _, phrase, command_template, confidence in pairs:
        pattern = compile_phrase(phrase)

        def builder(m: re.Match, _template: str = command_template) -> str:
            return _fill_template(_template, m.groupdict())

        _BUILTINS.append((pattern, builder, confidence))


_register_table()


def map_intent(text: str, aliases: dict[str, str] | None = None) -> Match | None:
    """Map transcribed text to a shell command. Returns None when unsure."""
    text = " ".join(text.split())  # collapse whitespace
    if not text:
        return None

    # 1. Built-in intents first.
    for pattern, builder, confidence in _BUILTINS:
        m = pattern.match(text)
        if m:
            return Match(command=builder(m), confidence=confidence, source="builtin")

    # 2. User aliases, fuzzy matched. Threshold keeps wild guesses out.
    best: Match | None = None
    for phrase, command in (aliases or {}).items():
        score = _fuzzy_score(text, phrase)
        if score >= 0.6 and (best is None or score > best.confidence):
            # Alias confidence is capped below builtins so exact builtin
            # patterns always win ties.
            best = Match(command=command, confidence=min(score, 0.89), source="alias")
    return best
