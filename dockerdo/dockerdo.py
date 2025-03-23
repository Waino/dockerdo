"""dockerdo/dodo: Use your local dev tools for remote docker development"""

import click
import importlib.resources
import os
import rich
import sys
import time
from pathlib import Path
from typing import Optional, List

from dockerdo import prettyprint
from dockerdo.config import UserConfig, Session
from dockerdo.docker import DISTROS, format_dockerfile
from dockerdo.shell import (
    set_execution_mode,
    get_user_config_dir,
    run_docker_save_pipe,
    run_local_command,
    run_remote_command,
    run_container_command,
    verify_container_state,
    run_ssh_master_process,
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
    session_dir = os.environ.get("DOCKERDO_SESSION_DIR", None)
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
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
@cli.command()
def install(no_bashrc: bool, verbose: bool, dry_run: bool) -> int:
    """Install dockerdo"""
    set_execution_mode(verbose, dry_run)
    # Create the user config file
    user_config_dir = get_user_config_dir()
    user_config_dir.mkdir(parents=True, exist_ok=True)
    user_config_path = user_config_dir / "dockerdo.yaml"
    bash_completion_path = user_config_dir / "dockerdo.bash-completion"
    if not user_config_path.exists():
        initial_config = UserConfig()
        with prettyprint.LongAction(
            host="local",
            running_verb="Creating",
            done_verb="Created",
            running_message=f"user config file {user_config_path}",
        ) as task:
            with open(user_config_path, "w") as fout:
                fout.write(initial_config.model_dump_yaml())
            task.set_status("OK")
    else:
        prettyprint.warning(f"Not overwriting existing config file {user_config_path}")
    with prettyprint.LongAction(
        host="local",
        running_verb="Creating",
        done_verb="Created",
        running_message=f"bash completion file {bash_completion_path}",
    ) as task:
        with bash_completion_path.open("w") as fout:
            bash_completion = importlib.resources.read_text(
                "dockerdo", "dockerdo.bash-completion"
            )
            fout.write(bash_completion)
        task.set_status("OK")
    if not no_bashrc:
        with prettyprint.LongAction(
            host="local",
            running_verb="Modifying",
            done_verb="Modified",
            running_message="~/.bashrc",
        ) as task:
            with Path("~/.bashrc").expanduser().open("a") as fout:
                # Add the dodo alias to ~/.bashrc)
                fout.write("\n# Added by dockerdo\nalias dodo='dockerdo run'\n")
                # Add the dockerdo shell completion to ~/.bashrc
                fout.write(
                    f"[[ -f {bash_completion_path} ]] && source {bash_completion_path}\n"
                )
            task.set_status("OK")
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
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
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
    verbose: bool,
    dry_run: bool,
) -> int:
    """
    Initialize a dockerdo session.

    SESSION_NAME is optional. If not given, an ephemeral session is created.
    """
    set_execution_mode(verbose, dry_run)
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
    with prettyprint.LongAction(
        host="local",
        running_verb="Overlaying",
        done_verb="Overlayed",
        running_message=f"image {session.base_image} into Dockerfile.dockerdo",
    ) as task:
        with open(dockerfile, "w") as f:
            f.write(dockerfile_content)
        task.set_status(task.OK)
    return 0


@cli.command()
@click.option("--distro", type=click.Choice(DISTROS), default=None)
@click.option("--image", type=str, help="Docker image", default=None)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def overlay(distro: Optional[str], image: Optional[str], verbose: bool, dry_run: bool) -> int:
    """Overlay a Dockerfile with the changes needed by dockerdo"""
    set_execution_mode(verbose, dry_run)
    return _overlay(distro, image)


@cli.command()
@click.option("--remote", is_flag=True, help="Build on remote host")
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def build(remote: bool, verbose: bool, dry_run: bool) -> int:
    """Build a Docker image"""
    set_execution_mode(verbose, dry_run)
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

    build_cmd = f"docker build -t {session.image_tag} --build-arg SSH_PUB_KEY='{ssh_key}' -f {dockerfile} ."
    if remote:
        with prettyprint.LongAction(
            host="remote",
            running_verb="Building",
            done_verb="Built",
            running_message=f"image {session.image_tag} on {session.remote_host}",
        ) as task:
            run_remote_command(
                build_cmd,
                session,
            )
            task.set_status(task.OK)
    else:
        with prettyprint.LongAction(
            host="local",
            running_verb="Building",
            done_verb="Built",
            running_message=f"image {session.image_tag}",
        ) as task:
            run_local_command(
                build_cmd,
                cwd=cwd,
            )
            task.set_status(task.OK)
    session.save()
    return 0


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def push(verbose: bool, dry_run: bool) -> int:
    """Push a Docker image"""
    set_execution_mode(verbose, dry_run)
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
        sshfs_remote_mount_point = session.sshfs_remote_mount_point
        assert sshfs_remote_mount_point is not None
        run_docker_save_pipe(
            session.image_tag,
            local_work_dir=session.local_work_dir,
            sshfs_remote_mount_point=sshfs_remote_mount_point,
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
@click.option(
    "--ssh_port_on_remote_host", type=int, help="container SSH port on remote host"
)
@click.option("--record", is_flag=True, help="Record filesystem events")
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def run(
    docker_run_args: List[str],
    no_default_args: bool,
    ssh_port_on_remote_host: Optional[int],
    record: bool,
    verbose: bool,
    dry_run: bool,
) -> int:
    """Start the container"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1
    if session.image_tag is None:
        prettyprint.error("Must 'dockerdo build' first")
        return 1
    if session.container_state == "running":
        prettyprint.error("Container is expected to be already running")
        return 1
    if session.docker_run_args is not None and not no_default_args:
        docker_run_args = session.docker_run_args.split() + docker_run_args
    docker_run_args_str = " ".join(docker_run_args)
    if ssh_port_on_remote_host is None:
        # TODO: detect a free port
        ssh_port_on_remote_host = 2222
    session.ssh_port_on_remote_host = ssh_port_on_remote_host

    command = (
        f"docker run -d {docker_run_args_str}"
        f" -p {ssh_port_on_remote_host}:22 "
        f" --name {session.container_name} {session.image_tag}"
    )
    with prettyprint.LongAction(
        host="container",
        running_verb="Starting",
        done_verb="Started",
        running_message=f"container {session.container_name}",
    ) as task:
        if session.remote_host is None:
            run_local_command(command, cwd=session.local_work_dir)
        else:
            run_remote_command(command, session)
        session.container_state = "running"
        session.save()
        task.set_status(task.OK)

    remote_host = (
        session.remote_host if session.remote_host is not None else "localhost"
    )
    with prettyprint.LongAction(
        host="local",
        running_verb="Creating",
        done_verb="Created",
        running_message="SSH socket",
    ) as task:
        # sleep to wait for the container to start
        time.sleep(2)
        ssh_master_process = run_ssh_master_process(
            session=session,
            remote_host=remote_host,
            ssh_port_on_remote_host=ssh_port_on_remote_host
        )
        if os.path.exists(session.session_dir / "ssh-socket"):
            task.set_status(task.OK)
    with prettyprint.LongAction(
        host="local",
        running_verb="Mounting",
        done_verb="Mounted",
        running_message="container filesystem",
    ) as task:
        os.makedirs(session.sshfs_container_mount_point, exist_ok=True)
        run_local_command(
            f"sshfs -p {ssh_port_on_remote_host}"
            f" {session.container_username}@{remote_host}:/"
            f" {session.sshfs_container_mount_point}",
            cwd=session.local_work_dir,
        )
        if os.path.ismount(session.sshfs_container_mount_point):
            task.set_status(task.OK)

    session.record_inotify = session.record_inotify or record
    session.save()

    if session.record_inotify:
        import dockerdo.inotify

        inotify_listener = dockerdo.inotify.InotifyListener(session)
        inotify_listener.register_listeners()
        prettyprint.info("Recording filesystem events. Runs indefinitely: remember to background this process.")
        inotify_listener.listen()

    if ssh_master_process is None:
        return 1
    else:
        ssh_master_process.wait()
    return 0


@cli.command()
@click.argument("key_value", type=str, metavar="KEY=VALUE")
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def export(key_value: str, verbose: bool, dry_run: bool) -> int:
    """Add an environment variable to the env list"""
    set_execution_mode(verbose, dry_run)
    try:
        key, value = key_value.split("=")
    except ValueError:
        prettyprint.error("Invalid key=value format")
        return 1
    session = load_session()
    if session is None:
        return 1
    session.export(key, value)
    session.save()
    prettyprint.action("container", "Exported", f"{key}={value}")
    return 0


@cli.command()
@click.argument("args", type=str, nargs=-1)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def exec(args, verbose: bool, dry_run: bool) -> int:
    """Execute a command in the container"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1
    command = " ".join(args)
    run_container_command(command=command, session=session)
    session.record_command(command)
    return 0


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def status(verbose: bool, dry_run: bool) -> int:
    """Print the status of a session"""
    set_execution_mode(verbose, dry_run)
    user_config_path = get_user_config_dir() / "dockerdo.yaml"
    if not user_config_path.exists():
        prettyprint.warning(f"No user config found in {user_config_path}")
    session_dir = os.environ.get("DOCKERDO_SESSION_DIR", None)
    if session_dir is None:
        prettyprint.info("No active session")
        return 0
    session = load_session()
    assert session is not None

    # Check existence of Dockerfile
    dockerfile = session.local_work_dir / "Dockerfile.dockerdo"
    if dockerfile.exists():
        prettyprint.info(f"Dockerfile found in {dockerfile}")
    else:
        prettyprint.warning(f"No Dockerfile found in {dockerfile}")

    # Check existence of image
    if session.image_tag is not None:
        prettyprint.info(f"Docker images with tag: {session.image_tag}")
        command = f"docker images {session.image_tag}"
        if session.remote_host is None:
            run_local_command(command, cwd=session.local_work_dir)
        else:
            run_remote_command(command, session)

    # Check status of container
    verify_container_state(session)
    if session.container_state == "running":
        prettyprint.info(f"Containers named {session.container_name}")
        command = f"docker ps -a --filter name={session.container_name}"
        if session.remote_host is None:
            run_local_command(command, cwd=session.local_work_dir)
        else:
            run_remote_command(command, session)

    # Check status of mounts
    sshfs_remote_mount_point = session.sshfs_remote_mount_point
    if sshfs_remote_mount_point is not None:
        if os.path.ismount(sshfs_remote_mount_point):
            prettyprint.info(
                f"Remote host build directory mounted at {sshfs_remote_mount_point}"
            )
        else:
            prettyprint.warning(
                f"Remote host build directory not mounted at {sshfs_remote_mount_point}"
            )
    sshfs_container_mount_point = session.sshfs_container_mount_point
    if session.container_state == "running":
        if os.path.ismount(sshfs_container_mount_point):
            prettyprint.info(
                f"Container filesystem mounted at {sshfs_container_mount_point}"
            )
        else:
            prettyprint.warning(
                f"Container filesystem not mounted at {sshfs_container_mount_point}"
            )

    # Check status of SSH socket
    if session.container_state == "running":
        if os.path.exists(session.session_dir / "ssh-socket"):
            prettyprint.info(f"SSH socket found at {session.session_dir}/ssh-socket")
        else:
            prettyprint.warning(
                f"SSH socket not found at {session.session_dir}/ssh-socket"
            )

    prettyprint.container_status(session.container_state)
    prettyprint.info("Session status:")
    rich.print(
        session.model_dump_yaml(exclude={"modified_files", "container_state"}),
        file=sys.stderr,
    )
    session.save()
    return 0


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def stop(verbose: bool, dry_run: bool) -> int:
    """Stop the container"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1

    command = f"docker stop {session.container_name}"
    with prettyprint.LongAction(
        host="container",
        running_verb="Stopping",
        done_verb="Stopped",
        running_message=f"container {session.container_name}",
    ) as task:
        if session.remote_host is None:
            run_local_command(command, cwd=session.local_work_dir)
        else:
            run_remote_command(command, session)
        session.container_state = "stopped"
        session.save()
        task.set_status(task.OK)
    return 0


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def history(verbose: bool, dry_run: bool) -> int:
    """Show the history of a container"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1

    if session.record_inotify:
        prettyprint.info("Modified files:")
        for file in session.modified_files:
            print(file)
    else:
        prettyprint.info("Recording of modified files is disabled")
    prettyprint.info("Command history:")
    print(session.get_command_history())
    return 0


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def rm(verbose: bool, dry_run: bool) -> int:
    """Remove a container"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1

    command = f"docker rm {session.container_name}"
    with prettyprint.LongAction(
        host="container",
        running_verb="Removing",
        done_verb="Removed",
        running_message=f"container {session.container_name}",
    ) as task:
        if session.remote_host is None:
            run_local_command(command, cwd=session.local_work_dir)
        else:
            run_remote_command(command, session)
        session.container_state = "nothing"
        session.save()
        task.set_status(task.OK)
    return 0


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
