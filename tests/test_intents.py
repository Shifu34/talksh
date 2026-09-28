"""Tests for the expanded built-in intent table."""

from talksh.intents import INTENTS, mapping_count
from talksh.mapper import map_intent


def test_mapping_count_is_large():
    # The offline table is the product's offline selling point: it must
    # genuinely cover a developer's daily life, not just a handful of demos.
    assert mapping_count() >= 200


def test_no_duplicate_phrases():
    seen = set()
    for phrases, _, _ in INTENTS:
        for phrase in phrases:
            key = phrase.lower()
            assert key not in seen, f"duplicate phrase: {phrase!r}"
            seen.add(key)


def _cmd(text: str) -> str | None:
    m = map_intent(text)
    return m.command if m else None


# --- git ---
def test_git_branch_create():
    assert _cmd("create branch feature-x") == "git branch feature-x"


def test_git_commit_all_with_message():
    assert _cmd("commit all with message fix token refresh") == 'git commit -am "fix token refresh"'


def test_git_stash_pop():
    assert _cmd("stash pop") == "git stash pop"


def test_git_log_oneline():
    assert _cmd("compact git log") == "git log --oneline"


# --- docker ---
def test_docker_compose_logs_service():
    assert _cmd("compose logs api") == "docker compose logs api"


def test_docker_exec_shell():
    assert _cmd("shell into web") == "docker exec -it web sh"


# --- python ---
def test_pip_install():
    assert _cmd("install requests") == "pip install requests"


def test_pytest_coverage():
    assert _cmd("run tests with coverage") == "pytest --cov"


# --- npm ---
def test_npm_run_build():
    assert _cmd("npm build") == "npm run build"


# --- files ---
def test_find_file():
    assert _cmd("find file README") == 'find . -name "README"'


def test_grep_pattern():
    assert _cmd("search code for TODO") == 'grep -rn "TODO" .'


# --- network ---
def test_ping():
    assert _cmd("ping google.com") == "ping -c 4 google.com"


def test_ssh_with_user():
    assert _cmd("ssh alice at myhost") == "ssh alice@myhost"


# --- system ---
def test_process_on_port():
    assert _cmd("process on port 8080") == "lsof -i :8080"


def test_memory():
    assert _cmd("memory usage") == "free -h"


# --- kubernetes ---
def test_kubectl_get_pods():
    assert _cmd("list pods") == "kubectl get pods"


def test_kubectl_logs():
    assert _cmd("pod logs api-123") == "kubectl logs api-123"


# --- github ---
def test_gh_pr_list():
    assert _cmd("list pull requests") == "gh pr list"


def test_gh_issue_create():
    assert _cmd("create issue") == "gh issue create"


# --- slots are extracted, not just static ---
def test_slot_extraction_branch():
    assert _cmd("switch to branch hotfix-1") == "git checkout hotfix-1"


def test_slot_extraction_commit_message():
    assert _cmd("commit with message add retries") == 'git commit -m "add retries"'
