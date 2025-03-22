"""Functions to ensure a consistent look and feel for the output"""

import rich
import sys
from enum import Enum
from rich.text import Text
from typing import Union
from rich.live import Live
from rich.table import Table
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
    if status == "running":
        color = "green"
    elif status == "stopped":
        color = "yellow"
    else:
        color = "red"
    info(f"Container status: [bold {color}]{status}[/bold {color}]")


class LongTaskStatus(Enum):
    RUNNING = 0
    OK = 1
    WARN = 2
    FAIL = 3


class LongTask:
    """A status tracker for long tasks that don't report intermediary results"""

    RUNNING = LongTaskStatus.RUNNING
    OK = LongTaskStatus.OK
    WARN = LongTaskStatus.WARN
    FAIL = LongTaskStatus.FAIL
    _status_map = {
        LongTaskStatus.RUNNING: Text(""),
        LongTaskStatus.OK: Text.assemble(
            ("[", "bold white"),
            ("OK", "green"),
            ("]", "bold white"),
        ),
        LongTaskStatus.WARN: Text.assemble(
            ("[", "bold white"),
            ("WARN", "bold yellow"),
            ("]", "bold white"),
        ),
        LongTaskStatus.FAIL: Text.assemble(
            ("[", "bold white"),
            ("FAIL", "black on red"),
            ("]", "bold white"),
        ),
    }
    _bullet_map = {
        LongTaskStatus.RUNNING: Text.assemble(
            ("(", "bold white"),
            ("/", "bold blue"),
            (")", "bold white"),
        ),
        LongTaskStatus.OK: Text.assemble(
            ("(", "bold white"),
            ("+", "bold green"),
            (")", "bold white"),
        ),
        LongTaskStatus.WARN: Text.assemble(
            ("(", "bold white"),
            ("!", "bold yellow"),
            (")", "bold white"),
        ),
        LongTaskStatus.FAIL: Text.assemble(
            ("(", "bold white"),
            ("!", "bold red"),
            (")", "bold white"),
        ),
    }

    def __init__(self, message: Union[str, Text]):
        self.message = message
        self.status: Union[str, Text] = ""
        self.bullet: Union[str, Text] = ""
        self._live = None

    def set_status(self, status: Union[str, Text, LongTaskStatus]):
        if isinstance(status, LongTaskStatus):
            self.status = self._status_map[status]
            self.bullet = self._bullet_map[status]
        else:
            self.status = status
            self.bullet = ""
        if self._live:
            self._live.update(self._render(), refresh=True)

    def _render(self):
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")
        grid.add_row(self._add_bullet(self.message), self.status)
        return grid

    def _add_bullet(self, message: Union[str, Text]):
        if self.bullet == "":
            return message
        return Text.assemble(self.bullet, " ", message)

    def __enter__(self):
        self.set_status(LongTaskStatus.RUNNING)
        self._live = Live(self._render(), auto_refresh=False).__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        if not self.status:
            # If you didn't set a status before exit, then it failed
            self.set_status(LongTaskStatus.FAIL)
        else:
            # ensure that the correct status is shown
            self._live.update(self._render(), refresh=True)
        self._live.__exit__(*args, **kwargs)
        self._live = None
