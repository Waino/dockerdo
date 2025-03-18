"""dockerdo/dodo: Use your local dev tools for remote docker development"""

import click
import importlib.resources
import os
import sys
from pathlib import Path
from typing import Optional, List

from dockerdo import prettyprint
from dockerdo.config import UserConfig, Session
from dockerdo.docker import DISTROS, format_dockerfile
from dockerdo.shell import (
    get_sshfs_remote_dir,
    get_user_config_dir,
    run_docker_save_pipe,
    run_local_command,
    run_remote_command,
)
from dockerdo.utils import make_image_tag


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
        prettyprint.error(
            "$DOCKERDO_SESSION_DIR is not set. Did you source the activate script?"
        )
        return None
    session = Session.load(Path(session_dir))
    return session


# ## for subcommands
@click.group(context_settings={"show_default": True})
def cli() -> None:
    pass


@click.option("--no-bashrc", is_flag=True, help="Do not modify ~/.bashrc")
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
        prettyprint.action("local", "Created", f"config file {user_config_path}")
    else:
        prettyprint.warning(f"Not overwriting existing config file {user_config_path}")
    with bash_completion_path.open("w") as fout:
        bash_completion = importlib.resources.read_text(
            "dockerdo", "dockerdo.bash-completion"
        )
        fout.write(bash_completion)
        prettyprint.action(
            "local", "Created", f"bash completion file {bash_completion_path}"
        )
    if not no_bashrc:
        with Path("~/.bashrc").expanduser().open("a") as fout:
            # Add the dodo alias to ~/.bashrc)
            fout.write("\n# Added by dockerdo\nalias dodo='dockerdo run'\n")
            # Add the dockerdo shell completion to ~/.bashrc
            fout.write(
                f"[[ -f {bash_completion_path} ]] && source {bash_completion_path}\n"
            )
            prettyprint.action("local", "Modified", "~/.bashrc")
    return 0


@cli.command()
@click.argument("session_name", type=str, required=False)
@click.option("--container", type=str, help="Container name [default: random]")
@click.option("--record", is_flag=True, help="Record filesystem events")
@click.option("--remote", "remote_host", type=str, help="Remote host")
@click.option("--local", is_flag=True, help="Remote host is the same as local host")
@click.option("--distro", type=click.Choice(DISTROS), default=None)
@click.option("--image", type=str, help="Docker image")
@click.option(
    "--user", "container_username", type=str, help="Container username", default="root"
)
@click.option("--registry", type=str, help="Docker registry", default=None)
@click.option(
    "--build_dir", type=Path, help="Remote host build directory", default=Path(".")
)
def init(
    record: bool,
    session_name: Optional[str],
    container: Optional[str],
    remote_host: Optional[str],
    local: bool,
    distro: Optional[str],
    image: Optional[str],
    container_username: str,
    registry: Optional[str],
    build_dir: Path,
) -> int:
    """
    Initialize a dockerdo session.

    SESSION_NAME is optional. If not given, an ephemeral session is created.
    """
    user_config = load_user_config()
    cwd = Path(os.getcwd())
    session = Session.from_opts(
        session_name=session_name,
        container_name=container,
        remote_host=remote_host,
        local=local,
        distro=distro,
        base_image=image,
        container_username=container_username,
        docker_registry=registry,
        record_inotify=record,
        remote_host_build_dir=build_dir,
        local_work_dir=cwd,
        user_config=user_config,
    )
    if session is None:
        return 1
    session.save()
    print(session.write_activate_script())
    return 0


def _overlay(distro: Optional[str], image: Optional[str]) -> int:
    """Overlay a Dockerfile with the changes needed by dockerdo"""
    user_config = load_user_config()
    session = load_session()
    if session is None:
        return 1

    if image is not None:
        session.base_image = image
    if distro is not None:
        session.distro = distro
    cwd = Path(os.getcwd())
    dockerfile = cwd / "Dockerfile.dockerdo"
    dockerfile_content = format_dockerfile(
        distro=session.distro,
        image=session.base_image,
        homedir=session.get_homedir(),
        ssh_key_path=user_config.ssh_key_path,
    )
    with open(dockerfile, "w") as f:
        f.write(dockerfile_content)
    prettyprint.action(
        "local", "Overlayed", f"image {session.base_image} into Dockerfile.dockerdo"
    )
    return 0


@cli.command()
@click.option("--distro", type=click.Choice(DISTROS), default=None)
@click.option("--image", type=str, help="Docker image", default=None)
def overlay(distro: Optional[str], image: Optional[str]) -> int:
    """Overlay a Dockerfile with the changes needed by dockerdo"""
    return _overlay(distro, image)


@cli.command()
@click.option("--remote", is_flag=True, help="Build on remote host")
def build(remote) -> int:
    """Build a Docker image"""
    session = load_session()
    if session is None:
        return 1
    user_config = load_user_config()

    cwd = Path(os.getcwd())
    dockerfile = cwd / "Dockerfile.dockerdo"
    if not dockerfile.exists():
        _overlay(session.distro, session.base_image)
    session.image_tag = make_image_tag(
        session.docker_registry,
        session.base_image,
        session.name,
    )

    # Read SSH key content
    # This approach avoids the limitation of Docker build context
    # while still securely injecting the SSH key into the image during build time
    with open(user_config.ssh_key_path, "r") as f:
        ssh_key = f.read().strip()

    build_cmd = f"docker build -t {session.image_tag} --build-arg SSH_KEY='{ssh_key}'-f {dockerfile} ."
    if remote:
        run_remote_command(
            build_cmd,
            session,
        )
        prettyprint.action(
            "remote", "Built", f"image {session.image_tag} on {session.remote_host}"
        )
    else:
        run_local_command(
            build_cmd,
            cwd=cwd,
        )
        prettyprint.action("local", "Built", f"image {session.image_tag}")
    return 0


@cli.command()
def push() -> int:
    """Push a Docker image"""
    session = load_session()
    if session is None:
        return 1
    if session.image_tag is None:
        prettyprint.error("Must 'dockerdo build' first")
        return 1

    if session.docker_registry is not None:
        run_local_command(
            f"docker push {session.image_tag}", cwd=session.local_work_dir
        )
    elif session.remote_host is not None:
        sshfs_remote_dir = get_sshfs_remote_dir(session)
        assert sshfs_remote_dir is not None
        run_docker_save_pipe(
            session.image_tag,
            local_work_dir=session.local_work_dir,
            sshfs_remote_dir=sshfs_remote_dir,
        )
        remote_path = session.remote_host_build_dir / f"{session.name}.tar.gz"
        run_remote_command(f"pigz -d {remote_path} | docker load", session)
    else:
        prettyprint.warning(
            "No docker registry or remote host configured. Not pushing image."
        )
        return 1
    return 0


@cli.command()
@click.argument("docker_run_args", type=str, nargs=-1)
@click.option(
    "--no-default-args",
    is_flag=True,
    help="Do not add default arguments from user config",
)
def run(docker_run_args: List[str]) -> int:
    """Start the container"""
    session = load_session()
    if session is None:
        return 1
    if session.image_tag is None:
        prettyprint.error("Must 'dockerdo build' first")
        return 1
    if session.docker_run_args is not None:
        docker_run_args = session.docker_run_args.split() + docker_run_args
    docker_run_args_str = " ".join(docker_run_args)

    if session.remote_host is None:
        run_local_command(
            f"docker run -d {docker_run_args_str} --name {session.container_name} {session.image_tag}",
            cwd=session.local_work_dir,
        )
    else:
        run_remote_command(
            f"docker run -d {docker_run_args_str} --name {session.container_name} {session.image_tag}",
            session,
        )
    return 0


@cli.command()
def export() -> int:
    """Add an environment variable to the env list"""
    session = load_session()
    if session is None:
        return 1
    return 0


@cli.command()
def exec() -> int:
    """Execute a command in the container"""
    session = load_session()
    if session is None:
        return 1
    return 0


@cli.command()
def stop() -> int:
    """Stop the container"""
    session = load_session()
    if session is None:
        return 1
    return 0


@cli.command()
def history() -> int:
    """Show the history of a container"""
    session = load_session()
    if session is None:
        return 1
    return 0


@cli.command()
def rm() -> int:
    """Remove a container"""
    session = load_session()
    if session is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
