"""Tests for natural phrasing: fillers, lead-ins, buried intents, negation."""

from talksh.mapper import _strip_fillers, map_intent


def test_i_want_to_lead_in():
    m = map_intent("I want to run the test for the auth module")
    assert m is not None
    assert m.command == "pytest tests/test_auth.py -v"


def test_can_you_please_lead_in():
    m = map_intent("can you please run the tests")
    assert m is not None
    assert m.command == "pytest"


def test_trailing_please():
    m = map_intent("run the tests for the auth module please")
    assert m is not None
    assert m.command == "pytest tests/test_auth.py -v"


def test_um_and_hey_fillers():
    assert map_intent("um run the tests").command == "pytest"
    assert map_intent("hey, git status").command == "git status"


def test_truncated_sentence_maps_bare():
    # "I want to run the test for..." got cut off by the recording window.
    m = map_intent("I want to run the test for...")
    assert m is not None
    assert m.command == "pytest"


def test_buried_intent_found():
    m = map_intent("could you show me git status")
    assert m is not None
    assert m.command == "git status"


def test_buried_commit_with_message():
    m = map_intent("I would like to commit with message fix login bug")
    assert m is not None
    assert m.command == 'git commit -m "fix login bug"'


def test_negation_never_maps():
    assert map_intent("don't run the tests") is None
    assert map_intent("never commit this") is None
    assert map_intent("do not push to main") is None


def test_strip_fillers_idempotent():
    assert _strip_fillers("so please um run the tests please") == "run the tests"
    assert _strip_fillers("git status") == "git status"
    assert _strip_fillers("please") == ""


def test_filler_word_inside_slot_kept():
    # "now" is a filler at the edges, but part of a message it stays.
    m = map_intent("commit with message ship it now")
    assert m is not None
    assert m.command == 'git commit -m "ship it now"'
