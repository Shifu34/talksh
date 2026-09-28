"""Command-line entry point for talksh."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from talksh import __version__
from talksh.audio import audio_available, record
from talksh.config import Config
from talksh.executor import confirm_and_run, is_blocked
from talksh.llm import resolve_command
from talksh.stt import transcribe

console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="talksh",
        description="Local-first voice control for your terminal. Speak an intent, confirm the command, run it.",
    )
    p.add_argument("--version", action="version", version=f"talksh {__version__}")
    p.add_argument(
        "--demo",
        action="store_true",
        help="Simulated end-to-end run. No microphone or model needed.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the mapped command instead of executing it.",
    )
    p.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the LLM even when an API key is configured; use the local intent mapper.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=5.0,
        help="How long to record in one-shot mode (default: 5).",
    )
    p.add_argument(
        "--model",
        default=None,
        help="faster-whisper model size (default: from config, or 'base').",
    )
    p.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: ~/.talksh.yaml).",
    )
    return p


def run_demo(cfg: Config, dry_run: bool, no_llm: bool = False) -> int:
    """Scripted pipeline demo: fake transcript -> map -> confirm -> execute.

    Uses the real mapper and executor; only audio capture and STT are
    simulated. Needs no microphone, no model, no audio libraries.
    """
    transcript = "run the tests for the auth module"
    stt_confidence = 0.94

    console.print("[bold]talksh --demo[/bold] [dim](simulated, no mic or model used)[/dim]\n")
    console.print("[dim]1. push-to-talk ... recording ... done[/dim]")
    console.print(f'[dim]2. transcribe locally[/dim]  "{transcript}"  (confidence {stt_confidence:.2f})')

    match, via = resolve_command(transcript, cfg, no_llm=no_llm)
    via_note = {"llm": "via LLM", "local": "via local mapper", "none": ""}[via]
    if via == "llm":
        console.print("[dim]3. generate command (LLM)[/dim]")
    elif via == "local":
        console.print("[dim]3. map intent (no LLM key configured, using local mapper)[/dim]")
    if match is None:
        console.print("[red]No intent matched.[/red] Try rephrasing.")
        return 1
    console.print(
        f"[dim]   [/dim]  -> [cyan]{match.command}[/cyan] "
        f"(confidence {match.confidence:.2f}, {via_note or match.source})"
    )

    if is_blocked(match.command):
        console.print("[red]Refused:[/red] that command is on the safety blocklist.")
        return 1

    console.print("[dim]4. confirm[/dim]  Run it? [y/n] [bold]y[/bold] [dim](simulated answer)[/dim]")
    # Execute a harmless echo so the demo shows real execution output.
    return confirm_and_run(
        f'echo "talksh demo: executed after voice confirmation: {match.command}"',
        dry_run=dry_run,
        assume_yes=True,
    )


def run_once(cfg: Config, args: argparse.Namespace) -> int:
    """Record once from the mic, transcribe, map, confirm, execute."""
    if not audio_available():
        console.print(
            "[red]No microphone available.[/red] Install OS audio libraries "
            "(e.g. PortAudio) or try [bold]talksh --demo[/bold]."
        )
        return 1

    console.print(f"[dim]Recording for {args.seconds:g}s... speak now.[/dim]")
    try:
        audio = record(seconds=args.seconds)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    model = args.model or cfg.model
    console.print(f"[dim]Transcribing locally ({model})...[/dim]")
    try:
        transcript, stt_conf = transcribe(audio, model_name=model, language=cfg.language)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    console.print(f'Heard: "{transcript}"  (confidence {stt_conf:.2f})')
    if not transcript:
        console.print("[yellow]Heard nothing. Try again, a little louder.[/yellow]")
        return 1

    match, via = resolve_command(transcript, cfg, no_llm=args.no_llm)
    if match is None:
        console.print("[yellow]Could not map that to a command. Try rephrasing.[/yellow]")
        return 1
    via_note = {"llm": "via LLM", "local": "via local mapper"}.get(via, match.source)
    console.print(
        f"Mapped to [cyan]{match.command}[/cyan] "
        f"(confidence {match.confidence:.2f}, {via_note})"
    )
    return confirm_and_run(match.command, dry_run=args.dry_run)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load(args.config)
    if args.demo:
        return run_demo(cfg, args.dry_run, args.no_llm)
    return run_once(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
