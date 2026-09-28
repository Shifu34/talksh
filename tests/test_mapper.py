"""Tests for the intent mapper."""

from talksh.executor import is_blocked, is_destructive
from talksh.mapper import map_intent


def test_run_tests_bare():
    m = map_intent("run the tests")
    assert m is not None
    assert m.command == "pytest"
    assert m.source == "builtin"


def test_run_tests_for_module():
    m = map_intent("run the tests for the auth module")
    assert m is not None
    assert m.command == "pytest tests/test_auth.py -v"


def test_git_status():
    m = map_intent("git status")
    assert m is not None
    assert m.command == "git status"


def test_git_commit_with_message():
    m = map_intent("commit with message fix login bug")
    assert m is not None
    assert m.command == 'git commit -m "fix login bug"'


def test_docker_compose_up():
    m = map_intent("docker compose up")
    assert m is not None
    assert m.command == "docker compose up -d"


def test_custom_alias_fuzzy():
    aliases = {"tail the api logs": "docker compose logs -f api"}
    m = map_intent("tail api logs", aliases)
    assert m is not None
    assert m.command == "docker compose logs -f api"
    assert m.source == "alias"


def test_builtin_beats_alias_on_tie():
    aliases = {"git status": "echo wrong"}
    m = map_intent("git status", aliases)
    assert m is not None
    assert m.source == "builtin"
    assert m.command == "git status"


def test_unknown_intent_returns_none():
    assert map_intent("bake a chocolate cake") is None
    assert map_intent("") is None


def test_blocklist_refuses_rm_rf_root():
    assert is_blocked("rm -rf /")
    assert is_blocked("rm -rf / --no-preserve-root")
    assert not is_blocked("pytest tests/")


def test_destructive_detection():
    assert is_destructive("rm -rf build/")
    assert is_destructive("git push --force origin main")
    assert not is_destructive("git status")
