"""Functions to ensure a consistent look and feel for the output"""

import rich
import sys
from rich.text import Text
from typing import Union
from rich.live import Live
from typing import Literal, Optional

Host = Literal["local", "remote", "container"]
ActionStatus = Literal["RUNNING", "OK", "WARN", "FAIL"]


def format_bullet(status: ActionStatus) -> Text:
    _bullet_map = {
        "RUNNING": Text.assemble(
            ("(", "bold white"),
            ("/", "bold blue"),
            (")", "bold white"),
        ),
        "OK": Text.assemble(
            ("(", "bold white"),
            ("+", "bold green"),
            (")", "bold white"),
        ),
        "WARN": Text.assemble(
            ("(", "bold white"),
            ("!", "bold yellow"),
            (")", "bold white"),
        ),
        "FAIL": Text.assemble(
            ("(", "bold white"),
            ("!", "bold red"),
            (")", "bold white"),
        ),
    }
    return _bullet_map.get(status, Text(""))


def format_action(host: Host, verb: str, text: Union[str, Text], status: ActionStatus = "OK") -> Text:
    if host == "local":
        host_color = "green"
    elif host == "remote":
        host_color = "blue"
    else:
        host_color = "magenta"
    pad_len = max(0, 9 - len(host))
    pad = " " * pad_len
    bullet = format_bullet(status)
    host_text = Text.assemble(
        ("[", "bold white"),
        (host, f"bold {host_color}"),
        ("]", "bold white"),
        (pad, ""),
    )
    message = Text.assemble(
        (f"{verb:>9}", "bold green"),
        (" ", ""),
        text,
    )
    return Text.assemble(bullet, " ", host_text, message)


def action(host: Host, verb: str, text: str) -> None:
    rich.print(format_action(host, verb, text), file=sys.stderr)


def info(text: str) -> None:
    rich.print(f"[bold blue](#)[/bold blue] [bold]{text}[/bold]", file=sys.stderr)


def warning(text: str) -> None:
    rich.print(f"[bold yellow](!)[/bold yellow] [bold]{text}[/bold]", file=sys.stderr)


def error(text: str) -> None:
    rich.print(f"[bold red](!)[/bold red] [bold]{text}[/bold]", file=sys.stderr)


def container_status(status: str) -> None:
    if status == "running":
        color = "green"
    elif status == "stopped":
        color = "yellow"
    else:
        color = "red"
    info(f"Container status: [bold {color}]{status}[/bold {color}]")


class LongAction:
    """A status tracker for long tasks that don't report intermediary results"""

    def __init__(
        self,
        host: Host,
        running_verb: str,
        done_verb: str,
        running_message: Union[str, Text],
        done_message: Optional[Union[str, Text]] = None,
    ):
        self.host = host
        self.running_verb = running_verb
        self.done_verb = done_verb
        self.running_message = Text.assemble(running_message)
        self.done_message = Text.assemble(done_message) if done_message else running_message
        self.bullet: Text = Text("")
        self.status: ActionStatus = "RUNNING"
        self._live = None

    def set_status(self, status: ActionStatus):
        self.status = status
        self.bullet = format_bullet(status)
        if self._live:
            self._live.update(self._render(), refresh=True)

    def _render(self):
        message = self.done_message if self.status == 'OK' else self.running_message
        verb = self.done_verb if self.status == 'OK' else self.running_verb
        if self.status in {"WARN", "FAIL"}:
            message = Text.assemble(message, " ", (self.status, "bold red"))
        return format_action(self.host, verb, message, self.status)

    def __enter__(self):
        self.set_status("RUNNING")
        self._live = Live(self._render(), auto_refresh=False).__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        if not self.status:
            # If you didn't set a status before exit, then it failed
            self.set_status("FAIL")
        else:
            # ensure that the correct status is shown
            self._live.update(self._render(), refresh=True)
        self._live.__exit__(*args, **kwargs)
        self._live = None
