"""Functions to ensure a consistent look and feel for the output"""

import rich
import sys
from typing import Literal

Host = Literal["local", "remote", "container"]


def action(host: Host, verb: str, text: str) -> None:
    if host == "local":
        host_color = "green"
    elif host == "remote":
        host_color = "blue"
    else:
        host_color = "magenta"
    pad_len = max(0, 9 - len(host))
    pad = " " * pad_len
    rich.print(
        "[bold green](+)[/bold green]"
        f" [[{host_color}]{host}[/{host_color}]]{pad}"
        f" [bold green]{verb:>9}[/bold green]"
        f" {text}",
        file=sys.stderr,
    )


def info(text: str) -> None:
    rich.print(f"[bold blue](#)[/bold blue] [bold]{text}[/bold]", file=sys.stderr)


def warning(text: str) -> None:
    rich.print(f"[bold yellow](!)[/bold yellow] [bold]{text}[/bold]", file=sys.stderr)


def error(text: str) -> None:
    rich.print(f"[bold red](!)[/bold red] [bold]{text}[/bold]", file=sys.stderr)


def container_status(status: str) -> None:
    if status == "created":
        color = "blue"
    if status == "running":
        color = "green"
    elif status == "stopped":
        color = "yellow"
    else:
        color = "red"
    info(f"Container status: [bold {color}]{status}[/bold {color}]")
