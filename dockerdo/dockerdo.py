"""dockerdo/dodo: Use your local dev tools for remote docker development"""

import click
import importlib.resources
import os
import sys
from pathlib import Path
from typing import Optional

from dockerdo.shell import get_user_config_dir
from dockerdo.config import UserConfig, Session
from dockerdo import prettyprint


def load_user_config() -> UserConfig:
    """Load the user config"""
    user_config_path = get_user_config_dir() / "dockerdo.yaml"
    if not user_config_path.exists():
        return UserConfig()
    with open(user_config_path, "r") as fin:
        return UserConfig.from_yaml(fin.read())


def load_session() -> Optional[Session]:
    """Load a session"""
    session_dir = os.environ.get("DOCKERDO_SESSION_DIR")
    if session_dir is None:
        prettyprint.error("$DOCKERDO_SESSION_DIR is not set")
        return None
    session = Session.load(Path(session_dir))
    return session


# ## for subcommands
@click.group(context_settings={'show_default': True})
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
    user_config_path = user_config_dir / "dockerdo.yaml"
    bash_completion_path = user_config_dir / "dockerdo.bash-completion"
    if not user_config_path.exists():
        initial_config = UserConfig()
        with open(user_config_path, "w") as fout:
            fout.write(initial_config.model_dump_yaml())
    with bash_completion_path.open("w") as fout:
        bash_completion = importlib.resources.read_text(
            "dockerdo", "dockerdo.bash-completion"
        )
        fout.write(bash_completion)
    if not no_bashrc:
        with Path("~/.bashrc").expanduser().open("a") as fout:
            # Add the dodo alias to ~/.bashrc)
            fout.write("\n# Added by dockerdo\nalias dodo='dockerdo run'\n")
            # Add the dockerdo shell completion to ~/.bashrc
            fout.write(
                f"[[ -f {bash_completion_path} ]] && source {bash_completion_path}\n"
            )
    return 0


@cli.command()
@click.argument("session_name", type=str, required=False)
@click.option("--container", type=str, help="Container name [default: random]")
@click.option("--record", is_flag=True, help="Record filesystem events")
@click.option("--remote", "remote_host", type=str, help="Remote host")
@click.option("--local", is_flag=True, help="Remote host is the same as local host")
@click.option("--image", type=str, help="Docker image")
@click.option("--registry", type=str, help="Docker registry", default=None)
@click.option("--build_dir", type=Path, help="Remote host build directory", default=Path("."))
def init(
    record: bool,
    session_name: Optional[str],
    container: Optional[str],
    remote_host: Optional[str],
    local: bool,
    image: Optional[str],
    registry: Optional[str],
    build_dir: Path,
) -> int:
    """
    Initialize a dockerdo session.

    SESSION_NAME is optional. If not given, an ephemeral session is created.
    """
    user_config = load_user_config()
    session = Session.from_opts(
        session_name=session_name,
        container_name=container,
        remote_host=remote_host,
        local=local,
        base_image=image,
        docker_registry=registry,
        record_inotify=record,
        remote_host_build_dir=build_dir,
        user_config=user_config,
    )
    session.save()
    print(session.write_activate_script())
    return 0


@cli.command()
@click.option("--distro", type=click.Choice(["ubuntu", "alpine"]))
def overlay() -> int:
    """Overlay a Dockerfile with the changes needed by dockerdo"""
    user_config = load_user_config()
    session = load_session()
    if session is None:
        return 1
    prettyprint.action(f"Overlaying image {session.base_image} into Dockerfile.dockerdo")
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
