"""dockerdo/dodo: Use your local dev tools for remote docker development"""

import click
import sys


# ## for subcommands
@click.group()
def cli() -> None:
    pass


# @click.argument('vararg', type=str, nargs=-1)
# @click.option('--enum', type=click.Choice(choices))
@click.option('--no_bashrc', is_flag=True, help="Do not modify ~/.bashrc")
@cli.command()
def install(no_bashrc: bool) -> int:
    """Install dockerdo"""
    return 0


@cli.command()
def init() -> int:
    """Initialize dockerdo"""
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
def start() -> int:
    """Start the container"""
    return 0


@cli.command()
def export() -> int:
    """Add an environment variable to the env list"""
    return 0


@cli.command()
def run() -> int:
    """Run a command in the container"""
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
