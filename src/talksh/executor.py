"""Command execution with safety rails.

Rules:
- A blocklist of destructive patterns is refused outright, no override.
- Commands that delete or overwrite files need the user to type "yes".
- --dry-run prints the command instead of running it.
"""

from __future__ import annotations

import re
import shlex
import subprocess

from rich.console import Console
from rich.prompt import Prompt

console = Console()

# Patterns that are never executed, however they were produced.
BLOCKLIST = [
    r"\bmkfs\b",
    r"\bdd\b.*\bof=/dev/",
    r":\(\)\s*{\s*:\|\:&\s*}\s*;",  # fork bomb
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r">\s*/dev/sd",
]

# rm targeting the filesystem root, in any argument position.
_RM_ROOT = re.compile(r"\brm\b.*(?:^|\s)/(?:\s|$)")

# Patterns that need typed confirmation ("yes", not just enter).
DESTRUCTIVE = [
    r"\brm\s+-rf?\b",
    r"\brmdir\b",
    r"\bgit\s+push\b.*--force",
    r"\bgit\s+reset\s+--hard\b",
    r"\bdocker\s+system\s+prune\b",
    r">",  # shell redirection can clobber files
]


def is_blocked(command: str) -> bool:
    if _RM_ROOT.search(command):
        return True
    return any(re.search(p, command) for p in BLOCKLIST)


def is_destructive(command: str) -> bool:
    return any(re.search(p, command) for p in DESTRUCTIVE)


def confirm_and_run(command: str, dry_run: bool = False, assume_yes: bool = False) -> int:
    """Show the command, get confirmation, run it. Returns the exit code."""
    if is_blocked(command):
        console.print("[red]Refused:[/red] that command is on the safety blocklist and will not run.")
        return 1

    console.print(f"[bold]Command:[/bold] [cyan]{command}[/cyan]")

    if dry_run:
        console.print("[yellow]Dry run:[/yellow] not executing.")
        return 0

    destructive = is_destructive(command)
    if destructive and not assume_yes:
        console.print("[red]This looks destructive.[/red] Type [bold]yes[/bold] to run it, anything else aborts.")
        answer = Prompt.ask("Confirm", default="no")
        if answer.strip().lower() != "yes":
            console.print("Aborted.")
            return 2
    elif not assume_yes:
        answer = Prompt.ask("Run it?", choices=["y", "n", "e"], default="n", show_default=True)
        if answer == "e":
            edited = Prompt.ask("Edit command", default=command)
            return confirm_and_run(edited, dry_run=dry_run)
        if answer != "y":
            console.print("Aborted.")
            return 2

    console.print("[dim]Running...[/dim]")
    try:
        proc = subprocess.run(command, shell=True)  # noqa: S602 - user-confirmed command
        return proc.returncode
    except KeyboardInterrupt:
        console.print("\nInterrupted.")
        return 130


def split_command(command: str) -> list[str]:
    """Best-effort tokenization, useful for previews and logging."""
    try:
        return shlex.split(command)
    except ValueError:
        return [command]
