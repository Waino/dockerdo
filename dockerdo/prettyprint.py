"""Functions to ensure a consistent look and feel for the output"""

import rich
import sys


def action(verb: str, text: str) -> None:
    rich.print(f"[bold green](+) {verb:>10}[/bold green] {text}", file=sys.stderr)


def warning(text: str) -> None:
    rich.print(f"[bold yellow](!)[/bold yellow] [bold]{text}[/bold]", file=sys.stderr)


def error(text: str) -> None:
    rich.print(f"[bold red](!)[/bold red] [bold]{text}[/bold]", file=sys.stderr)
