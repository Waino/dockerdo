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
    return 0


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
