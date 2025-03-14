"""dockerdo/dodo: Use your local dev tools for remote docker development"""

import click
import sys


# ## for subcommands
@click.group()
def cli():
    pass


# @click.argument('vararg', type=str, nargs=-1)
# @click.option('--enum', type=click.Choice(choices))
@click.option('--no_bashrc', is_flag=True, help="Do not modify ~/.bashrc")
@cli.command()
def install(no_bashrc: bool):
    """Install dockerdo"""
    return 0


@cli.command()
def init():
    """Initialize dockerdo"""
    return 0


@cli.command()
def overlay():
    """Overlay a Dockerfile with the changes needed by dockerdo"""
    return 0


@cli.command()
def build():
    """Build a Docker image"""
    return 0


@cli.command()
def push():
    """Push a Docker image"""
    return 0


@cli.command()
def start():
    """Start the container"""
    return 0


@cli.command()
def export():
    """Add an environment variable to the env list"""
    return 0


@cli.command()
def run():
    """Run a command in the container"""
    return 0


@cli.command()
def stop():
    """Stop the container"""
    return 0


@cli.command()
def history():
    """Show the history of a container"""
    return 0


@cli.command()
def rm():
    """Remove a container"""
    return 0


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
