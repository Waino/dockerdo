"""dockerdo/dodo: Use your local dev tools for remote docker development"""

import click
import sys
import importlib.resources
from pathlib import Path

from dockerdo.shell import get_user_config_dir
from dockerdo.config import UserConfig


# ## for subcommands
@click.group()
def cli() -> None:
    pass


# @click.argument('vararg', type=str, nargs=-1)
# @click.option('--enum', type=click.Choice(choices))
@click.option("--no_bashrc", is_flag=True, help="Do not modify ~/.bashrc")
@cli.command()
def install(no_bashrc: bool) -> int:
    """Install dockerdo"""
    # Create the user config file
    user_config_dir = get_user_config_dir()
    user_config_dir.mkdir(parents=True, exist_ok=True)
    user_config_path = user_config_dir / "dockerdorc"
    bash_completion_path = user_config_dir / "dockerdo.bash-completion"
    if not user_config_path.exists():
        initial_config = UserConfig()
        with open(user_config_path, "w") as fout:
            fout.write(initial_config.model_dump_json(indent=4))
    if not no_bashrc:
        with Path("~/.bashrc").expanduser().open("a") as fout:
            # Add the dodo alias to ~/.bashrc)
            fout.write("\n# Added by dockerdo\nalias dodo='dockerdo run'\n")
            # Add the dockerdo shell completion to ~/.bashrc
            fout.write(
                "[[ -f {bash_completion_path} ]]" " && source {bash_completion_path}\n"
            )
        with bash_completion_path.open("w") as fout:
            bash_completion = importlib.resources.read_text(
                "dockerdo", "dockerdo.bash-completion"
            )
            fout.write(bash_completion)
    return 0


@cli.command()
def init() -> int:
    """Initialize a dockerdo session"""
    return 0


@cli.command()
def overlay() -> int:
    """Overlay a Dockerfile with the changes needed by dockerdo"""
    return 0


@cli.command()
def build() -> int:
    """Build a Docker image"""
    return 0


@cli.command()
def push() -> int:
    """Push a Docker image"""
    return 0


@cli.command()
def run() -> int:
    """Start the container"""
    return 0


@cli.command()
def export() -> int:
    """Add an environment variable to the env list"""
    return 0


@cli.command()
def exec() -> int:
    """Execute a command in the container"""
    return 0


@cli.command()
def stop() -> int:
    """Stop the container"""
    return 0


@cli.command()
def history() -> int:
    """Show the history of a container"""
    return 0


@cli.command()
def rm() -> int:
    """Remove a container"""
    return 0


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
