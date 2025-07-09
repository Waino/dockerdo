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
from typing import Optional, List, Literal, Tuple

from dockerdo import prettyprint, __version__
from dockerdo.config import Preset, Session, MountSpecs, PortForwardSpecs
from dockerdo.docker import DISTROS, format_dockerfile
from dockerdo.shell import (
    confirm_tool_installed,
    detect_ssh_agent,
    ensure_mounts,
    ensure_port_forwards,
    find_free_port,
    get_all_docker_mount_args,
    get_container_work_dir,
    get_mutagen_forward_status,
    get_mutagen_status,
    get_user_config_dir,
    remove_forwards,
    remove_mounts,
    resolve_remote_host_build_dir,
    run_container_command,
    run_docker_save_pipe,
    run_local_command,
    run_remote_command,
    run_ssh_master_process,
    set_execution_mode,
    stop_forwards,
    stop_mounts,
    verify_container_state,
    write_container_env_file,
)
from dockerdo.ssh import (
    ensure_known_host_key,
    ensure_session_in_ssh_config,
    remove_known_host_key,
    remove_session_from_ssh_config,
    SSH_INCLUDE_BLOCK,
)
from dockerdo.utils import make_image_reference, retry


def load_preset(preset: str = '_default') -> Preset:
    """Load the user config"""
    user_config_path = get_user_config_dir() / "dockerdo.yaml"
    if not user_config_path.exists():
        return Preset()
    with open(user_config_path, "r") as fin:
        presets = Preset.load_presets(fin.read())
        if preset not in presets:
            raise Exception(f'No preset {preset}')
        return presets[preset]


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
@click.version_option(prog_name="dockerdo", package_name="dockerdo", version=__version__)
def cli() -> None:
    pass


@click.option("--no-bashrc", is_flag=True, help="Do not modify ~/.bashrc")
@click.option("--no-ssh-config", is_flag=True, help="Do not modify ~/.ssh/config")
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
@cli.command()
def install(no_bashrc: bool, no_ssh_config: bool, verbose: bool, dry_run: bool) -> int:
    """Install dockerdo"""
    set_execution_mode(verbose, dry_run)

    # Check requirements
    for tool in ["docker", "mutagen", "ssh", "sshfs", "ssh-keyscan", "scp"]:
        with prettyprint.LongAction(
            host="local",
            running_verb="Checking",
            done_verb="Checked" if not dry_run else "Would check",
            running_message=f"for required tool {tool}",
        ) as task:
            if confirm_tool_installed(tool):
                task.set_status("OK")
            else:
                task.set_status("FAIL")
                return 1

    # Create the user config file
    user_config_dir = get_user_config_dir()
    if not dry_run:
        user_config_dir.mkdir(parents=True, exist_ok=True)
    user_config_path = user_config_dir / "dockerdo.yaml"
    bash_completion_path = user_config_dir / "dockerdo.bash-completion"
    if not user_config_path.exists():
        initial_config = Preset.initial_config()
        with prettyprint.LongAction(
            host="local",
            running_verb="Creating",
            done_verb="Created" if not dry_run else "Would create",
            running_message=f"user config file {user_config_path}",
        ) as task:
            if not dry_run:
                with open(user_config_path, "w") as fout:
                    # Exclude the default values from the example preset
                    exclude = {
                        'default': {'description'},
                        'presets': {
                            '__all__': {
                                field for field in Preset.model_fields.keys()
                                if field not in ("description", "record_inotify", "mounts")
                            }
                        }
                    }
                    fout.write(initial_config.model_dump_yaml(exclude=exclude))
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

    # Add the command to include the dockerdo dynamic host blocks to the end of the main ssh config
    include_str = "Include ~/.ssh/config.dockerdo"
    main_ssh_config_path = Path("~/.ssh/config").expanduser()
    # Check if the include statement is already in the main ssh config
    already_included = False
    if main_ssh_config_path.exists():
        with main_ssh_config_path.open("r") as fin:
            if include_str in fin.read():
                prettyprint.info("SSH config already includes dockerdo dynamic hosts")
                already_included = True
    if not already_included:
        if no_ssh_config:
            prettyprint.warning(
                "Not modifying ~/.ssh/config. "
                "Please manually add the following line to ~/.ssh/config.dockerdo:"
            )
            print(include_str)
        else:
            with prettyprint.LongAction(
                host="local",
                running_verb="Modifying",
                done_verb="Modified" if not dry_run else "Would modify",
                running_message="~/.ssh/config",
            ) as task:
                if not dry_run:
                    with Path("~/.ssh/config").expanduser().open("a") as fout:
                        fout.write(f"\n{SSH_INCLUDE_BLOCK}\n")
                task.set_status("OK")
    return 0


@cli.command()
@click.argument("session_name", type=str, required=False)
@click.option("--preset", "preset_name", type=str, default="_default", help="Use preset from user config")
@click.option("--always-interactive", is_flag=True, help="Always assume interactive commands")
@click.option("--container", type=str, help="Container name [default: random]")
@click.option("--distro", type=click.Choice(DISTROS), default=None)
@click.option("--image", "base_image", type=str, help="Docker image")
@click.option("--local", is_flag=True, help="Remote host is the same as local host")
@click.option("--record", is_flag=True, help="Record filesystem events")
@click.option("--registry", type=str, help="Docker registry host", default=None)
@click.option("--registry-port", type=int, help="Docker registry port", default=None)
@click.option("--namespace", type=str, help="Docker registry namespace", default=None)
@click.option("--remote", "remote_host", type=str, help="Remote host")
@click.option(
    "--user", "container_username", type=str, help="Container username", default=None,
)
@click.option(
    "--build-dir", type=Path, help="Remote host build directory", default=None,
)
@click.option(
    "--ssh-key", 'ssh_key_path', type=Path, help="Path to ssh public key", default=None,
)
@click.option(
    "--startup-retries",
    type=int,
    help="Number of times to retry starting the ssh master process and mounts",
    default=None,
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
    preset_name: str,
    always_interactive: bool,
    base_image: Optional[str],
    build_dir: Optional[Path],
    container: Optional[str],
    container_username: Optional[str],
    distro: Optional[str],
    local: bool,
    record: bool,
    registry: Optional[str],
    registry_port: Optional[int],
    namespace: Optional[str],
    startup_retries: Optional[int],
    remote_delay: Optional[float],
    remote_host: Optional[str],
    session_name: Optional[str],
    ssh_key_path: Optional[Path],
    verbose: bool,
    dry_run: bool,
) -> int:
    """
    Initialize a dockerdo session.

    You should source the output of this command to activate the session:  source $(dockerdo init)

    SESSION_NAME is optional. If not given, an ephemeral session is created.
    """
    in_background = set_execution_mode(verbose, dry_run)
    preset = load_preset(preset=preset_name)
    cwd = Path(os.getcwd())
    session = Session.from_opts(
        always_interactive=always_interactive,
        base_image=base_image,
        container_name=container,
        container_username=container_username,
        distro=distro,
        docker_registry_host=registry,
        docker_registry_port=registry_port,
        docker_namespace=namespace,
        local=local,
        local_work_dir=cwd,
        preset=preset,
        record_inotify=record,
        startup_retries=startup_retries,
        remote_delay=remote_delay,
        remote_host=remote_host,
        remote_host_build_dir=build_dir,
        session_name=session_name,
        ssh_key_path=ssh_key_path,
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
@click.option("-t", "--overlay-tag", type=str, help="Override image referece for the overlayed image", default=None)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def build(remote: bool, overlay_tag: Optional[str], verbose: bool, dry_run: bool) -> int:
    """Build a Docker image"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1

    cwd = Path(os.getcwd())
    dockerfile = cwd / "Dockerfile.dockerdo"
    if not dockerfile.exists():
        _overlay(session.distro, session.base_image, dry_run)
    session.image_reference = overlay_tag if overlay_tag is not None else make_image_reference(
        docker_registry_host=session.docker_registry_host,
        docker_registry_port=session.docker_registry_port,
        docker_namespace=session.docker_namespace,
        base_image=session.base_image,
        session_name=session.name,
        image_name_template=session.image_name_template
    )

    # Read SSH key content
    # This approach avoids the limitation of Docker build context
    # while still securely injecting the SSH key into the image during build time
    if not session.ssh_key_path.exists():
        prettyprint.error(f"SSH key not found at {session.ssh_key_path}")
        return 1
    with open(session.ssh_key_path, "r") as f:
        ssh_key = f.read().strip()

    if remote:
        build_cmd = (
            f"docker build -t {session.image_reference}"
            f" --build-arg SSH_PUB_KEY='{ssh_key}' -f {dockerfile.name} ."
        )
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
            running_message=f"image {session.image_reference} on {session.remote_host}",
        ) as task:
            # build the image on the remote host
            retval = run_remote_command(
                build_cmd,
                session,
                use_tty=True,
            )
            if retval == 0:
                task.set_status("OK")
            else:
                return retval
    else:
        build_cmd = f"docker build -t {session.image_reference} --build-arg SSH_PUB_KEY='{ssh_key}' -f {dockerfile} ."
        with prettyprint.LongAction(
            host="local",
            running_verb="Building",
            done_verb="Built" if not dry_run else "Would build",
            running_message=f"image {session.image_reference}",
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
    if session.image_reference is None:
        prettyprint.error("Must 'dockerdo build' first")
        return 1

    if session.docker_registry_host is not None:
        with prettyprint.LongAction(
            host="remote",
            running_verb="Pushing",
            done_verb="Pushed" if not dry_run else "Would push",
            running_message=f"image {session.image_reference} to {session.docker_registry_host}",
        ) as task:
            retval = run_local_command(
                f"docker push {session.image_reference}", cwd=session.local_work_dir
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
            running_message=f"image {session.image_reference}",
        ) as task:
            retval = run_docker_save_pipe(
                image_reference=session.image_reference,
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
    in_background = set_execution_mode(verbose, dry_run)
    if session is None:
        return 1
    if session.image_reference is None:
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
    session.ssh_port_on_remote_host = (
        session.ssh_port_on_remote_host if session.ssh_port_on_remote_host is not None else 2222
    )

    if docker_command == "run":
        command = (
            f"docker run -d {docker_args_str}"
            f" -p {session.ssh_port_on_remote_host}:22 "
            f" --name {session.container_name} {session.image_reference}"
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

    if in_background:
        ctx_mgr = nullcontext()
    else:
        ctx_mgr = prettyprint.LongAction(
            host="container",
            running_verb="Scanning" if not dry_run else "Would scan",
            done_verb="Scanned" if not dry_run else "Would scan",
            running_message=f"container {session.container_name} ssh key",
        )
    with ctx_mgr as task:
        ensure_known_host_key(session)
        if task:
            task.set_status("OK")

    if in_background:
        ctx_mgr = nullcontext()
    else:
        ctx_mgr = prettyprint.LongAction(
            host="local",
            running_verb="Adding" if not dry_run else "Would add",
            done_verb="Added" if not dry_run else "Would add",
            running_message=f"container alias '{session.container_host_alias}' to ssh config",
        )
    with ctx_mgr as task:
        if not dry_run:
            ensure_session_in_ssh_config(session)
        if task:
            task.set_status("OK")

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
        ssh_master_process = run_ssh_master_process(session=session, retries=session.startup_retries)
        # sleep to wait for the ssh master process to start
        for _ in range(session.startup_retries):
            if not dry_run:
                time.sleep(2)
            if task and os.path.exists(session.session_dir / "ssh-socket-container"):
                task.set_status("OK")
                break
        if dry_run:
            task.set_status("OK")

    # mounts
    def _attempt_mounts():
        ensure_mounts(session)

    def _on_error_mounts(e: Exception):
        prettyprint.error(f"Error mounting: {e}")

    retry(_attempt_mounts, _on_error_mounts, retries=session.startup_retries)

    # port forwards
    def _attempt_forwards():
        ensure_port_forwards(session)

    def _on_error_forwards(e: Exception):
        prettyprint.error(f"Error forwarding ports: {e}")

    retry(_attempt_forwards, _on_error_forwards, retries=session.startup_retries)

    session.record_inotify = session.record_inotify or record
    if not dry_run:
        session.container_state = "running"
        session.save()

    if session.record_inotify:
        if not in_background:
            ctx_mgr = prettyprint.LongAction(
                host="local",
                running_verb="Recording" if not dry_run else "Would record",
                done_verb="Recording" if not dry_run else "Would record",
                running_message="filesystem events. Runs indefinitely: remember to background this process.",
            )
        with ctx_mgr as task:
            if not dry_run:
                import dockerdo.inotify

                inotify_listener = dockerdo.inotify.InotifyListener(session, verbose=verbose)
                inotify_listener.register_all_listeners()
                try:
                    inotify_listener.listen()
                except Exception as e:
                    prettyprint.error(f"No longer listening to filesystem events due to error: {e}")
            if task:
                task.set_status("OK")

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
    docker_run_args: Tuple[str],
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
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1
    docker_run_args_list = list(docker_run_args)
    if session.docker_run_args is not None and not no_default_args:
        docker_run_args_list = session.docker_run_args.split() + list(docker_run_args_list)
    if session.remote_host is not None and not session.remote_host_build_dir.is_absolute():
        abs_path = resolve_remote_host_build_dir(session)
        session.remote_host_build_dir = abs_path if abs_path is not None else session.remote_host_build_dir
    if ssh_port_on_remote_host is None:
        ssh_port_on_remote_host = session.ssh_port_on_remote_host
    if ssh_port_on_remote_host is None:
        ssh_port_on_remote_host = find_free_port(session=session)
    session.ssh_port_on_remote_host = ssh_port_on_remote_host
    session.format_mount_paths()
    docker_run_args_list.extend(get_all_docker_mount_args(session))
    return run_or_start(
        docker_command="run",
        docker_args=docker_run_args_list,
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
    set_execution_mode(verbose, dry_run)
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


def _ensure_callback(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    session = load_session()
    if session is None:
        prettyprint.error("No active session")
        ctx.exit()
    if session.container_state == "running":
        ensure_mounts(session)
        ensure_port_forwards(session)
    else:
        prettyprint.warning("Container is not running. Not mounting anything.")
    ctx.exit()


@cli.command()
@click.argument("near_path", type=Path)
@click.argument("far_path", type=Path)
@click.option("--near-host", type=click.Choice(["local", "remote"]), default="local")
@click.option("--far-host", type=click.Choice(["remote", "container"]), default="container")
@click.option("--type", "mount_type", type=click.Choice(["sshfs", "mutagen", "docker"]), default="mutagen")
@click.option(
    "--ensure",
    is_flag=True,
    callback=_ensure_callback,
    expose_value=False,
    is_eager=True,
    help="Instead of adding a new mount, ensure that all the current mounts are active"
)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def mount(
    near_path: Path,
    far_path: Path,
    near_host: Literal["local", "remote"],
    far_host: Literal["remote", "container"],
    mount_type: Literal["sshfs", "mutagen", "docker"],
    verbose: bool,
    dry_run: bool,
) -> int:
    """Mount (sshfs) or sync (mutagen) a directory"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1
    if mount_type == "docker" and session.container_state != "nothing":
        prettyprint.error("Can not add docker mount to existing container. Please remove it first.")
        return 1
    mount_specs = MountSpecs(
        near_host=near_host,
        near_path=near_path,
        far_host=far_host,
        far_path=far_path,
        mount_type=mount_type,
    )
    with prettyprint.LongAction(
        host="local",
        running_verb="Adding" if not dry_run else "Would add",
        done_verb="Added" if not dry_run else "Would add",
        running_message=f"mount: {mount_specs.descr_str()}",
    ) as task:
        if not dry_run:
            session.add_mount(mount_specs)
            session.save()
        task.set_status("OK")

    # if container is already running, mount it directly
    if session.container_state == "running":
        ensure_mounts(session)
    return 0


@cli.command()
@click.argument("local_port", type=int)
@click.argument("container_port", type=int)
@click.option(
    "--ensure",
    is_flag=True,
    callback=_ensure_callback,
    expose_value=False,
    is_eager=True,
    help="Instead of adding a new forward, ensure that all the current forwards are active"
)
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def forward(
    local_port: int,
    container_port: int,
    verbose: bool,
    dry_run: bool,
) -> int:
    """Forward a port using mutagen"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1

    forward_specs = PortForwardSpecs(
        local_port=local_port,
        container_port=container_port,
    )
    with prettyprint.LongAction(
        host="local",
        running_verb="Adding" if not dry_run else "Would add",
        done_verb="Added" if not dry_run else "Would add",
        running_message=f"forward: {forward_specs.descr_str()}",
    ) as task:
        if not dry_run:
            session.add_port_forward(forward_specs)
            session.save()
        task.set_status("OK")

    # if container is already running, create the forward directly
    if session.container_state == "running":
        ensure_port_forwards(session)
    return 0


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option("-i", "--interactive", is_flag=True, help="Connect stdin for interactive commands")
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def exec(args: List[str], interactive: bool, verbose: bool, dry_run: bool) -> int:
    """Execute a command in the container"""
    set_execution_mode(verbose, dry_run)
    session = load_session()
    if session is None:
        return 1
    command = " ".join(args)
    write_container_env_file(session)
    if session.remote_delay > 0.0:
        time.sleep(session.remote_delay)
    interactive = interactive or session.always_interactive
    retval, container_work_dir = run_container_command(command=command, session=session, interactive=interactive)
    if retval != 0:
        return retval
    session.record_command(command, container_work_dir)
    session.save()
    return 0


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print commands")
@click.option("-n", "--dry-run", is_flag=True, help="Do not execute commands")
def pwd(verbose: bool, dry_run: bool) -> int:
    """Print the working directory in the container"""
    set_execution_mode(verbose, dry_run)
    session_dir = os.environ.get("DOCKERDO_SESSION_DIR", None)
    if session_dir is None:
        prettyprint.info("No active session")
        return 0
    session = load_session()
    assert session is not None

    container_work_dir = get_container_work_dir(session)
    if not container_work_dir:
        prettyprint.warning(
            "Current working directory is not inside any of the container mount points:"
        )
        for mount_specs in session.mounts:
            if mount_specs.near_host == "local":
                prettyprint.info(str(mount_specs.near_path))
        return 1
    print(container_work_dir)
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
    if session.image_reference is not None:
        prettyprint.info(f"Docker images with tag: {session.image_reference}")
        command = f"docker images {session.image_reference}"
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
    mutagen_status = get_mutagen_status(session)
    if mutagen_status is None and not dry_run:
        prettyprint.error("Failed to get mutagen status")
    for mount_specs in session.mounts:
        active = False
        if mount_specs.mount_type == "sshfs":
            active = mount_specs.near_path.is_mount()
        elif mount_specs.mount_type == "mutagen":
            if mutagen_status is None:
                active = False
            else:
                for status in mutagen_status:
                    if status.get_id() == mount_specs.get_mutagen_id(session):
                        active = status.status == "watching"
        active_str = "Active" if active else "Inactive"
        prettyprint.info(f"{active_str:8s}:  {mount_specs.descr_str()}")

    # Check status of port forwards
    mutagen_forward_status = get_mutagen_forward_status(session)
    if mutagen_forward_status is None and not dry_run:
        prettyprint.error("Failed to get mutagen forward status")
    for forward_specs in session.port_forwards:
        active = False
        last_error = None
        if mutagen_forward_status is None:
            active = False
        else:
            for forward_status in mutagen_forward_status:
                if forward_status.get_id() == forward_specs.get_mutagen_id(session):
                    active = forward_status.status == "forwarding"
                    last_error = forward_status.lastError
                    break
        active_str = "Active" if active else "Inactive"
        prettyprint.info(f"{active_str:8s}:  {forward_specs.descr_str()}")
        if not active and last_error is not None:
            prettyprint.error(f"  {last_error}")

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
        session.model_dump_yaml(exclude={"container_state", "host_key_lines", "mounts", "port_forwards"}),
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

    stop_mounts(session)
    stop_forwards(session)

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
    in_background = set_execution_mode(verbose, dry_run)
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

    remove_mounts(session)
    remove_forwards(session)

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

    ctx_mgr: AbstractContextManager
    if in_background:
        ctx_mgr = nullcontext()
    else:
        ctx_mgr = prettyprint.LongAction(
            host="local",
            running_verb="Removing" if not dry_run else "Would remove",
            done_verb="Removed" if not dry_run else "Would remove",
            running_message="container host key from known_hosts",
        )
    with ctx_mgr as task:
        remove_known_host_key(session)
        if task:
            task.set_status("OK")

    if in_background:
        ctx_mgr = nullcontext()
    else:
        ctx_mgr = prettyprint.LongAction(
            host="local",
            running_verb="Removing" if not dry_run else "Would remove",
            done_verb="Removed" if not dry_run else "Would remove",
            running_message=f"container alias '{session.container_host_alias}' from ssh config",
        )
    with ctx_mgr as task:
        remove_session_from_ssh_config(session)
        if task:
            task.set_status("OK")

    if delete:
        # Delete the image
        if session.image_reference is not None:
            host: Literal["local", "remote"] = "local" if session.remote_host is None else "remote"
            with prettyprint.LongAction(
                host=host,
                running_verb="Deleting",
                done_verb="Deleted" if not dry_run else "Would delete",
                running_message=f"image {session.image_reference}",
            ) as task:
                if session.remote_host is not None:
                    retval = run_remote_command(
                        f"docker rmi {session.image_reference}", session
                    )
                else:
                    retval = run_local_command(
                        f"docker rmi {session.image_reference}", cwd=session.local_work_dir, silent=True
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


@cli.command()
@click.option("--preset", "preset_name", type=str, default=None, help="Preset from user config")
def show_preset(
    preset_name: Optional[str],
) -> int:
    """
    List presets, or give the specification for a particular preset
    """
    user_config_path = get_user_config_dir() / "dockerdo.yaml"
    if not user_config_path.exists():
        prettyprint.error(f"No user config found in {user_config_path}")
    with open(user_config_path, "r") as fin:
        presets = Preset.load_presets(fin.read())
    if preset_name is None:
        for key, preset in presets.items():
            prettyprint.info(f'{key:20s} {preset.description}')
    else:
        preset = presets[preset_name]
        print(preset.model_dump_yaml())
    return 0


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover
