# talksh

Talk to your terminal. Say what you want, like "run the tests for the auth module", and talksh turns it into a real shell command, shows it to you, and runs it only after you say so.

By default everything runs on your machine. The speech model runs locally, your words never leave your laptop, and nothing is sent to any cloud. If you want, you can add an LLM API key and talksh will use it to generate any command from plain speech, falling back to the local mapper whenever the key is missing or the call fails.

## How it works

1. Hold the push-to-talk hotkey and speak your intent.
2. Your microphone records a few seconds of audio.
3. A local speech model (faster-whisper) transcribes it to text.
4. The text becomes a shell command, two ways:
   - **Local mapper (default).** 600+ built-in phrase mappings plus your own aliases, all offline.
   - **LLM (optional).** With an API key configured, the transcript goes to an OpenAI-compatible chat API which returns one command.
5. The command is shown with a confidence score. You confirm, edit, or cancel.
6. The command runs, and you see the output like normal.

```
You say:  "run the tests for the auth module"
Heard:    "run the tests for the auth module"  (confidence 0.94)
Command:  pytest tests/test_auth.py -v
Run it? [y/N/e(dit)]
```

## Safety rules

Voice control is powerful, so talksh is careful by default:

- **Nothing destructive runs on voice alone.** Commands matching the blocklist (like `rm -rf /`, `mkfs`, `dd`, or `shutdown`) are refused outright. Commands that delete or overwrite files require you to type the word `yes`, not just press enter.
- **LLM output gets the same treatment.** A command from the LLM goes through the identical safety path: blocklist refusal, typed-yes for destructive commands, and `--dry-run` support. The model never gets a free pass.
- **You always see the command first.** Nothing executes without an explicit confirmation.
- **`--dry-run` prints the command instead of running it.** Handy for scripting or just checking what was understood.
- **Local by default.** With no API key configured, no audio or transcripts are uploaded anywhere. There is no account, no telemetry, and no network call in the core flow. The LLM path is strictly opt-in.

## Install

```bash
pip install -e .
```

Audio capture needs a working microphone and your OS audio libraries. The `--demo` mode below needs neither. The LLM path needs no extra packages, it uses the standard library.

## Quick start

```bash
# One-shot: hold nothing, just speak once (uses default mic)
talksh

# See what would run, without running it
talksh --dry-run

# Force the local mapper even when an API key is configured
talksh --no-llm

# Simulated demo, no mic or model needed
talksh --demo
```

## LLM command generation (optional)

Add an API key and talksh can turn any spoken request into a command, even ones the local mapper has never seen. It talks to any OpenAI-compatible chat completions endpoint, so local servers work too.

```yaml
# ~/.talksh.yaml
llm:
  api_key: "sk-..."                     # or use an env var (see below)
  model: "gpt-4o-mini"                 # default
  base_url: "https://api.openai.com/v1"  # default; point at a local server if you like
```

Or skip the config file and export a variable:

```bash
export TALKSH_API_KEY="sk-..."
# OPENAI_API_KEY works as a fallback too
```

Key precedence: `api_key` in the config file wins, then `TALKSH_API_KEY`, then `OPENAI_API_KEY`. The key is only ever sent as a bearer token to your configured endpoint; it is never logged or printed.

Behavior notes:

- With a key configured, the transcript goes to the LLM, which must return exactly one shell command. Markdown fences and quotes are stripped automatically.
- If the call fails for any reason (no network, bad key, timeout after 15 seconds), talksh quietly falls back to the local mapper instead of erroring out.
- `talksh --no-llm` skips the LLM entirely.

## Custom aliases

talksh reads `~/.talksh.yaml`. Add your own phrases:

```yaml
# ~/.talksh.yaml
hotkey: "ctrl+alt+v"
model: "base"          # tiny, base, small, medium, large-v3
language: "en"
confirm_destructive: true

llm:
  api_key: ""          # empty means local mapper only

aliases:
  "deploy the staging app": "kubectl rollout restart deployment/api -n staging"
  "tail the api logs": "docker compose logs -f api"
  "open the pr dashboard": "open https://github.com/pulls"
```

Aliases match fuzzily, so "tail api logs" still finds "tail the api logs". Built-in intents always run first, your aliases second.

## Built-in intents

The offline table holds 600+ phrase mappings across the tools developers actually use. A few examples:

| You say | It runs |
|---|---|
| "run the tests for the auth module" | `pytest tests/test_auth.py -v` |
| "commit all with message fix token refresh" | `git commit -am "fix token refresh"` |
| "create and switch to branch feature-x" | `git checkout -b feature-x` |
| "stash pop" | `git stash pop` |
| "compose logs api" | `docker compose logs api` |
| "shell into web" | `docker exec -it web sh` |
| "install requests" | `pip install requests` |
| "npm build" | `npm run build` |
| "process on port 8080" | `lsof -i :8080` |
| "pod logs api-123" | `kubectl logs api-123` |
| "restart deployment api" | `kubectl rollout restart deployment/api` |
| "list pull requests" | `gh pr list` |

Categories covered: git (status, add, commit, push, pull, branches, merge, rebase, stash, log, diff, tags, remotes), docker and compose, python/pytest/pip/venv, npm/node/yarn/pnpm, files (find, grep, ripgrep, tar, zip, permissions), system (processes, ports, disk, memory), network (ping, curl, ssh, scp, dns), kubernetes (pods, logs, exec, apply, port-forward, contexts), and the GitHub CLI (prs, issues, releases, workflows).

Phrases support slots: "commit with message {message}", "switch to branch {name}", "kill process {pid}", "copy {file} to {host}". More specific phrases win over generic ones, so "process on port 8080" finds the port and "process nginx" finds the process.

## Roadmap

- Push-to-talk global hotkey (currently one-shot recording).
- Per-project intent overrides.
- Confidence tuning and "did you mean" suggestions when the transcript is unclear.
- Shell completions and a `talksh init` wizard.

## License

MIT. Early days, contributions welcome.
