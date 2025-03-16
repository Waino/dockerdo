"""Functions to ensure a consistent look and feel for the output"""
import rich
import sys


def action(text: str) -> None:
    rich.print(f"[bold green](+)[/bold green] {text}", file=sys.stderr)


def warning(text: str) -> None:
    rich.print(f"[bold yellow](!)[/bold yellow] [bold]{text}[/bold]", file=sys.stderr)


def error(text: str) -> None:
    rich.print(f"[bold red](!)[/bold red] [bold]{text}[/bold]", file=sys.stderr)
