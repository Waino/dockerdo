"""dockerdo/dodo: Use your local dev tools for remote docker development"""

import click
import importlib.resources
import os
import rich
import sys
import time
from contextlib import nullcontext, AbstractContextManager
from pathlib import Path
from subprocess import Popen
from typing import Optional, List, Literal

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
    detect_background,
    detect_ssh_agent,
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
    if not dry_run:
        user_config_dir.mkdir(parents=True, exist_ok=True)
    user_config_path = user_config_dir / "dockerdo.yaml"
    bash_completion_path = user_config_dir / "dockerdo.bash-completion"
    if not user_config_path.exists():
        initial_config = UserConfig()
        with prettyprint.LongAction(
            host="local",
            running_verb="Creating",
            done_verb="Created" if not dry_run else "Would create",
            running_message=f"user config file {user_config_path}",
        ) as task:
            if not dry_run:
                with open(user_config_path, "w") as fout:
                    fout.write(initial_config.model_dump_yaml())
            task.set_status("OK")
    else:
        prettyprint.warning(f"Not overwriting existing config file {user_config_path}")
    with prettyprint.LongAction(
        host="local",
        running_verb="Creating",
        done_verb="Created" if not dry_run else "Would create",
        running_message=f"bash completion file {bash_completion_path}",
    ) as task:
        if not dry_run:
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
            done_verb="Modified" if not dry_run else "Would modify",
            running_message="~/.bashrc",
        ) as task:
            if not dry_run:
                with Path("~/.bashrc").expanduser().open("a") as fout:
                    # Add the dodo alias to ~/.bashrc)
                    fout.write("\n# Added by dockerdo\nalias dodo='dockerdo exec'\n")
                    # Add the dockerdo shell completion to ~/.bashrc
                    fout.write(
                        f"[[ -f {bash_completion_path} ]] && source {bash_completion_path}\n"
                    )
            task.set_status("OK")
        prettyprint.info("Remember to restart bash or source ~/.bashrc")
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
    "--build-dir", type=Path, help="Remote host build directory", default=Path(".")
)
@click.option(
    "--remote-delay",
    type=float,
    default=None,
    help="Delay to add to all remote commands, to allow slow sshfs to catch up",
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
    remote_delay: Optional[float],
    verbose: bool,
    dry_run: bool,
) -> int:
    """
    Initialize a dockerdo session.

    You should source the output of this command to activate the session:  source $(dockerdo init)

    SESSION_NAME is optional. If not given, an ephemeral session is created.
    """
    set_execution_mode(verbose, dry_run)
    in_background = detect_background()
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
        remote_delay=remote_delay,
        user_config=user_config,
        dry_run=dry_run,
    )
    if session is None:
        return 1
    if not dry_run:
        session.save()
        if not in_background:
            prettyprint.info("Remember to source the activate script:")
        print(session.write_activate_script())
    return 0


def _overlay(distro: Optional[str], image: Optional[str], dry_run: bool) -> int:
    """Overlay a Dockerfile with the changes needed by dockerdo"""
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
    )
    with prettyprint.LongAction(
        host="local",
        running_verb="Overlaying",
        done_verb="Overlayed" if not dry_run else "Would overlay",
        running_message=f"image {session.base_image} into Dockerfile.dockerdo",
    ) as task:
        with open(dockerfile, "w") as f:
            f.write(dockerfile_content)
        task.set_status("OK")
    if not dry_run:
        session.save()
    return 0


@cli.command()
@click.option("--distro", type=click.Choice(DISTROS), default=None)
@click.option("--image", type=str, help="Base docker image", default=None)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def overlay(
    distro: Optional[str],
    image: Optional[str],
    verbose: bool,
    dry_run: bool
) -> int:
    """Overlay a Dockerfile with the changes needed by dockerdo"""
    set_execution_mode(verbose, dry_run)
    return _overlay(distro, image, dry_run)


@cli.command()
@click.option("--remote", is_flag=True, help="Build on remote host")
@click.option("-t", "--overlay-tag", type=str, help="Override image tag for the overlayed image", default=None)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def build(remote: bool, overlay_tag: Optional[str], verbose: bool, dry_run: bool) -> int:
    """Build a Docker image"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1
    user_config = load_user_config()

    cwd = Path(os.getcwd())
    dockerfile = cwd / "Dockerfile.dockerdo"
    if not dockerfile.exists():
        _overlay(session.distro, session.base_image, dry_run)
    session.image_tag = overlay_tag if overlay_tag is not None else make_image_tag(
        docker_registry=session.docker_registry,
        base_image=session.base_image,
        session_name=session.name,
        image_name_template=user_config.default_image_name_template
    )

    # Read SSH key content
    # This approach avoids the limitation of Docker build context
    # while still securely injecting the SSH key into the image during build time
    if not user_config.ssh_key_path.exists():
        prettyprint.error(f"SSH key not found at {user_config.ssh_key_path}")
        return 1
    with open(user_config.ssh_key_path, "r") as f:
        ssh_key = f.read().strip()

    if remote:
        build_cmd = f"docker build -t {session.image_tag} --build-arg SSH_PUB_KEY='{ssh_key}' -f {dockerfile.name} ."
        assert session.sshfs_remote_mount_point is not None
        destination = session.sshfs_remote_mount_point / dockerfile.name
        with prettyprint.LongAction(
            host="remote",
            running_verb="Copying",
            done_verb="Copied" if not dry_run else "Would copy",
            running_message=f"Dockerfile {dockerfile} to {destination}",
        ) as task:
            # copy the Dockerfile to the remote host
            if not dry_run:
                if not session.sshfs_remote_mount_point.is_mount():
                    task.set_status("FAIL")
                    prettyprint.error(f"Remote host build directory not mounted at {session.sshfs_remote_mount_point}")
                    return 1
                with open(dockerfile, "r") as fin:
                    with open(destination, "w") as fout:
                        fout.write(fin.read())
                # sleep to allow sshfs to catch up
                time.sleep(max(1.0, session.remote_delay))
            task.set_status("OK")
        with prettyprint.LongAction(
            host="remote",
            running_verb="Building",
            done_verb="Built" if not dry_run else "Would build",
            running_message=f"image {session.image_tag} on {session.remote_host}",
        ) as task:
            # build the image on the remote host
            retval = run_remote_command(
                build_cmd,
                session,
            )
            if retval == 0:
                task.set_status("OK")
            else:
                return retval
    else:
        build_cmd = f"docker build -t {session.image_tag} --build-arg SSH_PUB_KEY='{ssh_key}' -f {dockerfile} ."
        with prettyprint.LongAction(
            host="local",
            running_verb="Building",
            done_verb="Built" if not dry_run else "Would build",
            running_message=f"image {session.image_tag}",
        ) as task:
            retval = run_local_command(
                build_cmd,
                cwd=cwd,
            )
            if retval == 0:
                task.set_status("OK")
            else:
                return retval
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
        with prettyprint.LongAction(
            host="remote",
            running_verb="Pushing",
            done_verb="Pushed" if not dry_run else "Would push",
            running_message=f"image {session.image_tag}",
        ) as task:
            retval = run_local_command(
                f"docker push {session.image_tag}", cwd=session.local_work_dir
            )
            if retval != 0:
                return retval
            task.set_status("OK")
    elif session.remote_host is not None:
        sshfs_remote_mount_point = session.sshfs_remote_mount_point
        assert sshfs_remote_mount_point is not None
        with prettyprint.LongAction(
            host="remote",
            running_verb="Saving",
            done_verb="Saved" if not dry_run else "Would save",
            running_message=f"image {session.image_tag}",
        ) as task:
            retval = run_docker_save_pipe(
                session.image_tag,
                local_work_dir=session.local_work_dir,
                sshfs_remote_mount_point=sshfs_remote_mount_point,
            )
            if retval != 0:
                return retval
            remote_path = session.remote_host_build_dir / f"{session.name}.tar.gz"
            retval = run_remote_command(f"pigz -d {remote_path} | docker load", session)
            if retval != 0:
                return retval
            task.set_status("OK")
    else:
        prettyprint.warning(
            "No docker registry or remote host configured. Not pushing image."
        )
        return 1
    return 0


def run_or_start(
    docker_command: Literal["run", "start"],
    docker_args: List[str],
    record: bool,
    remote_delay: Optional[float],
    verbose: bool,
    dry_run: bool,
    session: Session,
) -> int:
    """
    Either run (create and start) or start the container

    Always run this command backgrounded, by adding an ampersand (&) at the end.
    """
    in_background = detect_background()
    set_execution_mode(verbose, dry_run)
    if session is None:
        return 1
    if session.image_tag is None:
        prettyprint.error("Must 'dockerdo build' first")
        return 1
    if not detect_ssh_agent():
        prettyprint.error("Dockerdo requires an ssh agent. Please start one and add your keys.")
        return 1
    verify_container_state(session)
    if session.container_state == "running":
        prettyprint.error(f"Container {session.container_name} is already running!")
        return 1
    docker_args_str = " ".join(docker_args)
    if remote_delay is not None:
        session.remote_delay = remote_delay
    ssh_port_on_remote_host = session.ssh_port_on_remote_host if session.ssh_port_on_remote_host is not None else 2222

    if docker_command == "run":
        command = (
            f"docker run -d {docker_args_str}"
            f" -p {ssh_port_on_remote_host}:22 "
            f" --name {session.container_name} {session.image_tag}"
        )
    else:  # start
        command = f"docker start {docker_args_str} {session.container_name}"

    ctx_mgr: AbstractContextManager
    if in_background:
        ctx_mgr = nullcontext()
    else:
        ctx_mgr = prettyprint.LongAction(
            host="container",
            running_verb="Starting" if not dry_run else "Would start",
            done_verb="Started" if not dry_run else "Would start",
            running_message=f"container {session.container_name}",
        )
    with ctx_mgr as task:
        if session.remote_host is None:
            retval = run_local_command(command, cwd=session.local_work_dir, silent=in_background)
        else:
            retval = run_remote_command(command, session)
        if retval != 0:
            return retval
        if task:
            task.set_status("OK")

    remote_host = (
        session.remote_host if session.remote_host is not None else "localhost"
    )
    ssh_master_process: Optional[Popen] = None
    if not in_background:
        ctx_mgr = prettyprint.LongAction(
            host="local",
            running_verb="Creating" if not dry_run else "Would create",
            done_verb="Created" if not dry_run else "Would create",
            running_message="SSH socket",
        )
    with ctx_mgr as task:
        # sleep to wait for the container to start
        if not dry_run:
            time.sleep(2)
        ssh_master_process = run_ssh_master_process(
            session=session,
            remote_host=remote_host,
            ssh_port_on_remote_host=ssh_port_on_remote_host
        )
        # sleep to wait for the ssh master process to start
        time.sleep(2)
        if task and os.path.exists(session.session_dir / "ssh-socket-container"):
            task.set_status("OK")
        if dry_run:
            task.set_status("OK")

    if not in_background:
        ctx_mgr = prettyprint.LongAction(
            host="local",
            running_verb="Mounting" if not dry_run else "Would mount",
            done_verb="Mounted" if not dry_run else "Would mount",
            running_message="container filesystem",
        )
    with ctx_mgr as task:
        if not dry_run:
            os.makedirs(session.sshfs_container_mount_point, exist_ok=True)
        retval = run_local_command(
            f"sshfs -p {ssh_port_on_remote_host}"
            f" {session.container_username}@{remote_host}:/"
            f" {session.sshfs_container_mount_point}",
            cwd=session.local_work_dir,
            silent=in_background,
        )
        if retval != 0:
            return retval
        if task and session.sshfs_container_mount_point.is_mount():
            task.set_status("OK")
        if dry_run:
            task.set_status("OK")

    session.record_inotify = session.record_inotify or record
    if not dry_run:
        session.container_state = "running"
        session.save()

    if session.record_inotify:
        if not dry_run:
            import dockerdo.inotify

            inotify_listener = dockerdo.inotify.InotifyListener(session)
            inotify_listener.register_listeners()
            if not in_background:
                prettyprint.info("Recording filesystem events. Runs indefinitely: remember to background this process.")
            try:
                inotify_listener.listen(verbose=verbose)
            except OSError as e:
                prettyprint.error(f"No longer listening to filesystem events due to error: {e}")
        else:
            prettyprint.info("Would record filesystem events")

    if ssh_master_process is None:
        return 1
    else:
        if not in_background:
            prettyprint.info(
                "Waiting for ssh master connection to close. Runs indefinitely: remember to background this process."
            )
        ssh_master_process.wait()
    return 0


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("docker_run_args", nargs=-1, type=click.UNPROCESSED)
@click.option(
    "--no-default-args",
    is_flag=True,
    help="Do not add default arguments from user config",
)
@click.option(
    "--ssh-port-on-remote-host", type=int, help="container SSH port on remote host"
)
@click.option("--record", is_flag=True, help="Record filesystem events")
@click.option(
    "--remote-delay",
    type=float,
    default=None,
    help="Delay to add to all remote commands, to allow slow sshfs to catch up",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Print commands."
    " Note that you can not shorten this to -v due to common usage of docker run -v for volume mounts."
)
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def run(
    docker_run_args: List[str],
    no_default_args: bool,
    ssh_port_on_remote_host: Optional[int],
    record: bool,
    remote_delay: Optional[float],
    verbose: bool,
    dry_run: bool,
) -> int:
    """
    Run (create and start) the container

    Accepts the arguments for `docker run`.

    Always run this command backgrounded, by adding an ampersand (&) at the end.
    """
    session = load_session()
    if session is None:
        return 1
    if session.docker_run_args is not None and not no_default_args:
        docker_run_args = session.docker_run_args.split() + docker_run_args
    if ssh_port_on_remote_host is None:
        # TODO: detect a free port
        ssh_port_on_remote_host = 2222
    session.ssh_port_on_remote_host = ssh_port_on_remote_host
    return run_or_start(
        docker_command="run",
        docker_args=docker_run_args,
        record=record,
        remote_delay=remote_delay,
        verbose=verbose,
        dry_run=dry_run,
        session=session,
    )


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("docker_start_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--record", is_flag=True, help="Record filesystem events")
@click.option(
    "--remote-delay",
    type=float,
    default=None,
    help="Delay to add to all remote commands, to allow slow sshfs to catch up",
)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def start(
    docker_start_args: List[str],
    record: bool,
    remote_delay: Optional[float],
    verbose: bool,
    dry_run: bool,
) -> int:
    """
    Start a previously stopped container

    Accepts the arguments for `docker start`.

    Always run this command backgrounded, by adding an ampersand (&) at the end.
    """
    session = load_session()
    if session is None:
        return 1
    if session.container_state != "stopped":
        prettyprint.error(f"Expecting a stopped container {session.container_name}")
        return 1

    return run_or_start(
        docker_command="start",
        docker_args=docker_start_args,
        record=record,
        remote_delay=remote_delay,
        verbose=verbose,
        dry_run=dry_run,
        session=session,
    )


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
    if len(value.strip()) == 0:
        prettyprint.action("container", "Unexported" if not dry_run else "Would unexport", key)
    else:
        prettyprint.action("container", "Exported" if not dry_run else "Would export", f"{key}={value}")
    return 0


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("-i", "--interactive", is_flag=True, help="Connect stdin for interactive commands")
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def exec(args: List[str], interactive: bool, verbose: bool, dry_run: bool) -> int:
    """Execute a command in the container"""
    set_execution_mode(verbose, dry_run)
    user_config = load_user_config()
    session = load_session()
    if session is None:
        return 1
    command = " ".join(args)
    session.write_container_env_file(verbose=verbose)
    if session.remote_delay > 0.0:
        time.sleep(session.remote_delay)
    interactive = interactive or user_config.always_interactive
    retval, container_work_dir = run_container_command(command=command, session=session, interactive=interactive)
    if retval != 0:
        return retval
    session.record_command(command, container_work_dir)
    session.save()
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
        if sshfs_remote_mount_point.is_mount():
            prettyprint.info(
                f"Remote host build directory mounted at {sshfs_remote_mount_point}"
            )
        else:
            prettyprint.warning(
                f"Remote host build directory not mounted at {sshfs_remote_mount_point}"
            )
    sshfs_container_mount_point = session.sshfs_container_mount_point
    if session.container_state == "running":
        if sshfs_container_mount_point.is_mount():
            prettyprint.info(
                f"Container filesystem mounted at {sshfs_container_mount_point}"
            )
        else:
            prettyprint.warning(
                f"Container filesystem not mounted at {sshfs_container_mount_point}"
            )

    # Check status of SSH sockets
    if session.remote_host is not None:
        if os.path.exists(session.session_dir / "ssh-socket-remote"):
            prettyprint.info(f"SSH socket to remote host found at {session.session_dir}/ssh-socket-remote")
        else:
            prettyprint.warning(
                f"SSH socket to remote host not found at {session.session_dir}/ssh-socket-remote"
            )
    if session.container_state == "running":
        if os.path.exists(session.session_dir / "ssh-socket-container"):
            prettyprint.info(f"SSH socket to container found at {session.session_dir}/ssh-socket-container")
        else:
            prettyprint.warning(
                f"SSH socket to container not found at {session.session_dir}/ssh-socket-container"
            )

    prettyprint.container_status(session.container_state)
    prettyprint.info("Session status:")
    rich.print(
        session.model_dump_yaml(exclude={"container_state"}),
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

    # unmount container filesystem
    if session.sshfs_container_mount_point.is_mount():
        with prettyprint.LongAction(
            host="local",
            running_verb="Unmounting",
            done_verb="Unmounted" if not dry_run else "Would unmount",
            running_message="container filesystem",
        ) as task:
            run_local_command(
                f"fusermount -u {session.sshfs_container_mount_point}",
                cwd=session.local_work_dir,
            )
            task.set_status("OK")

    command = f"docker stop {session.container_name}"
    with prettyprint.LongAction(
        host="container",
        running_verb="Stopping",
        done_verb="Stopped" if not dry_run else "Would stop",
        running_message=f"container {session.container_name}",
    ) as task:
        if session.remote_host is None:
            retval = run_local_command(command, cwd=session.local_work_dir)
        else:
            retval = run_remote_command(command, session)
        if retval != 0:
            return retval
        session.container_state = "stopped"
        session.save()
        task.set_status("OK")
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

    if len(session.env) > 0:
        prettyprint.info("Environment variables:")
        for key, value in session.env.items():
            print(f"{key}={value}")
    if session.record_inotify:
        prettyprint.info("Modified files:")
        for file in session.get_modified_files():
            print(file)
    else:
        prettyprint.info("Recording of modified files is disabled")
    prettyprint.info("Command history:")
    prettyprint.command_history(session.get_command_history())
    return 0


@cli.command()
@click.option("-f", "--force", is_flag=True, help="Force removal of container")
@click.option("--delete", is_flag=True, help="Delete session directory")
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def rm(force: bool, delete: bool, verbose: bool, dry_run: bool) -> int:
    """Remove a container"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1
    verify_container_state(session)

    if session.remote_host is not None:
        # Unmount remote host build directory
        sshfs_remote_mount_point = session.sshfs_remote_mount_point
        assert sshfs_remote_mount_point is not None
        if sshfs_remote_mount_point.is_mount():
            with prettyprint.LongAction(
                host="local",
                running_verb="Unmounting",
                done_verb="Unmounted" if not dry_run else "Would unmount",
                running_message="remote host build directory",
            ) as task:
                run_local_command(
                    f"fusermount -u {sshfs_remote_mount_point}",
                    cwd=session.local_work_dir,
                )
                task.set_status("OK")

    if session.container_state != "nothing":
        force_flag = "-f" if force else ""
        command = f"docker rm {force_flag} {session.container_name}"
        with prettyprint.LongAction(
            host="container",
            running_verb="Removing",
            done_verb="Removed" if not dry_run else "Would remove",
            running_message=f"container {session.container_name}",
        ) as task:
            if session.remote_host is None:
                retval = run_local_command(command, cwd=session.local_work_dir, silent=True)
            else:
                retval = run_remote_command(command, session)
            if retval != 0:
                return retval
            session.container_state = "nothing"
            session.save()
            task.set_status("OK")

    if delete:
        # Delete the image
        if session.image_tag is not None:
            host: Literal["local", "remote"] = "local" if session.remote_host is None else "remote"
            with prettyprint.LongAction(
                host=host,
                running_verb="Deleting",
                done_verb="Deleted" if not dry_run else "Would delete",
                running_message=f"image {session.image_tag}",
            ) as task:
                if session.remote_host is not None:
                    retval = run_remote_command(
                        f"docker rmi {session.image_tag}", session
                    )
                else:
                    retval = run_local_command(
                        f"docker rmi {session.image_tag}", cwd=session.local_work_dir, silent=True
                    )
                if retval != 0:
                    return retval
                task.set_status("OK")

        # Delete session directory
        with prettyprint.LongAction(
            host="local",
            running_verb="Deleting",
            done_verb="Deleted" if not dry_run else "Would delete",
            running_message=f"session directory {session.session_dir}",
        ) as task:
            if not dry_run:
                # delete the expected directory contents first
                for file_name in [
                    "activate",
                    "command_history.jsonl",
                    "env.list",
                    "modified_files",
                    "session.yaml",
                    "ssh-socket-container",
                    "ssh-socket-remote",
                ]:
                    file_path = session.session_dir / file_name
                    if file_path.exists():
                        file_path.unlink()
                # Now the directory should be empty, so we can delete it
                try:
                    session.session_dir.rmdir()
                    task.set_status("OK")
                except OSError:
                    prettyprint.error(f"There are extraneous files in {session.session_dir}")
                    for file in session.session_dir.iterdir():
                        print(file)
                    task.set_status("FAIL")
                    return 1
            else:
                task.set_status("OK")

    if session.remote_host is not None:
        prettyprint.info("Remember to foreground and close the ssh master process")
    prettyprint.info("Remember to call deactivate_dockerdo")
    return 0


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
