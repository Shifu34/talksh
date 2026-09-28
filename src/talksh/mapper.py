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


@_builtin(r"^\W*run (?:the )?tests?(?: for (?:the )?(.+?)(?: modules?)?)?\W*$", 0.92)
def _run_tests(m: re.Match) -> str:
    target = re.sub(r"[^\w\s./-]", "", (m.group(1) or "")).strip()
    if not target:
        return "pytest"
    # "auth module" -> tests/test_auth.py ; leave dotted paths alone
    slug = target.replace(" ", "_").lower()
    path = slug if "/" in slug or slug.endswith(".py") else f"tests/test_{slug}.py"
    return f"pytest {path} -v"


@_builtin(r"^\\W*git status\\W*$", 0.98)
def _git_status(m: re.Match) -> str:
    return "git status"


@_builtin(r"^\\W*(?:commit|commit changes?)(?: with message (.+?))?\\W*$", 0.9)
def _git_commit(m: re.Match) -> str:
    msg = (m.group(1) or "").strip().strip("\"'")
    if msg:
        return f'git commit -m "{msg}"'
    return "git commit"


@_builtin(r"^\\W*(?:start|run)(?: the)? servers?\\W*$", 0.85)
def _run_server(m: re.Match) -> str:
    return "python -m http.server"


@_builtin(r"^\\W*docker compose up\\W*$", 0.95)
def _compose_up(m: re.Match) -> str:
    return "docker compose up -d"


@_builtin(r"^\\W*list files?\\W*$", 0.95)
def _list_files(m: re.Match) -> str:
    return "ls -la"


def _fuzzy_score(a: str, b: str) -> float:
    """Token-aware similarity: 1.0 for exact, lower for partial overlap."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


_SLOT_TOKEN = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_PUNCT = re.compile(r"[^a-zA-Z0-9\s]")


def _singular(word: str) -> str:
    """Crude de-pluralization. Only needs to be consistent, not perfect
    English; case is preserved."""
    low = word.lower()
    if len(low) <= 3:
        return word
    if low.endswith("ies"):
        return word[:-3] + "y"
    if low.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if low.endswith("us"):  # status, plus, ...
        return word
    if low.endswith("s") and not low.endswith("ss"):
        return word[:-1]
    return word


def _normalize(text: str) -> str:
    """Normalize text for loose comparison (suggestions only, never for
    slot extraction): strip punctuation, collapse whitespace, singularize."""
    text = _PUNCT.sub(" ", text)
    return " ".join(_singular(w) for w in text.split())


def _plural(word: str) -> str:
    """Crude pluralization: test->tests, branch->branches, city->cities."""
    low = word.lower()
    if len(low) <= 3 or low.endswith("s"):
        return word
    if low.endswith("y") and low[-2] not in "aeiou":
        return word[:-1] + "ies"
    if low.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def _word_variants(word: str) -> list[str]:
    """Singular/plural variants of a literal word, longest first, so
    'test' and 'tests' match the same intent."""
    variants = {word, _singular(word), _plural(word), _plural(_singular(word))}
    return sorted(variants, key=len, reverse=True)


def _compile_literal(text: str) -> str:
    """Compile literal phrase words into a regex tolerating singular/plural
    differences. Slots are untouched, so captured values (filenames,
    hostnames, messages) keep their original text."""
    words = text.split()
    if not words:
        return ""
    return r"\s+".join(
        "(?:" + "|".join(re.escape(v) for v in _word_variants(w)) + ")"
        for w in words
    )


def compile_phrase(phrase: str) -> re.Pattern:
    """Compile a phrase template like "commit with message {message}" into a
    case-insensitive regex. {slot} captures free text; literal words match
    singular or plural, and leading/trailing punctuation is ignored."""
    parts: list[str] = []
    last = 0
    for m in _SLOT_TOKEN.finditer(phrase):
        parts.append(_compile_literal(phrase[last : m.start()]))
        parts.append(f"(?P<{m.group(1)}>.+)")
        last = m.end()
    parts.append(_compile_literal(phrase[last:]))
    return re.compile(r"^\W*(?:" + "".join(parts) + r")\W*$", re.IGNORECASE)


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


# Human-readable phrase table, kept for "did you mean" suggestions.
# Each entry is (phrase template, command template).
PHRASE_TABLE: list[tuple[str, str]] = []


def _register_table() -> None:
    """Append the phrase table to the builtin registry, after the core.

    Phrases are tried most-specific-first so a generic pattern like
    "process {name}" never shadows "process on port {port}". Ties keep
    file order."""
    pairs: list[tuple[int, int, str, str, float]] = []
    for order, (phrases, command_template, confidence) in enumerate(INTENTS):
        for phrase in phrases:
            pairs.append((order, phrase, command_template, confidence))
            PHRASE_TABLE.append((phrase, command_template))
    pairs.sort(key=lambda p: (-_literal_words(p[1]), p[0]))
    for _, phrase, command_template, confidence in pairs:
        pattern = compile_phrase(phrase)

        def builder(m: re.Match, _template: str = command_template) -> str:
            return _fill_template(_template, m.groupdict())

        _BUILTINS.append((pattern, builder, confidence))


_register_table()


def map_intent(text: str, aliases: dict[str, str] | None = None) -> Match | None:
    """Map transcribed text to a shell command. Returns None when unsure.

    Matching tolerates singular/plural differences ("test" vs "tests")
    and letter case; captured slots keep their original text.
    """
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


# Representative phrases for the hand-tuned core builtins (which have no
# phrase-table entries), so suggestions cover them too.
_CORE_PHRASES: list[tuple[str, str]] = [
    ("run the tests for the {module} module", "pytest tests/test_{module}.py -v"),
    ("run the tests", "pytest"),
    ("git status", "git status"),
    ("commit with message {message}", 'git commit -m "{message}"'),
    ("start the server", "python -m http.server"),
    ("docker compose up", "docker compose up -d"),
    ("list files", "ls -la"),
]


def _token_overlap(a: str, b: str) -> float:
    """Token-set overlap between two normalized strings, 0..1."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def suggest(text: str, aliases: dict[str, str] | None = None, n: int = 3) -> list[str]:
    """Closest known phrases to the given text, for 'did you mean' hints.

    Returns strings like '"run the tests" -> pytest'. Empty when nothing
    is even close.
    """
    norm = _normalize(text)
    scored: list[tuple[float, str]] = []
    for phrase, command in _CORE_PHRASES + PHRASE_TABLE:
        shown = _SLOT_TOKEN.sub(lambda m: m.group(1), phrase)
        score = _token_overlap(norm, _normalize(shown))
        scored.append((score, f'"{phrase}" -> {command}'))
    for phrase, command in (aliases or {}).items():
        score = _token_overlap(norm, _normalize(phrase))
        scored.append((score, f'"{phrase}" -> {command}'))
    scored.sort(key=lambda p: -p[0])
    return [hint for score, hint in scored[:n] if score > 0.2]
