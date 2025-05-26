"""Shell related functions"""

import json
import os
import shlex
import sys
from contextlib import nullcontext, AbstractContextManager
from pathlib import Path
from pydantic import ValidationError, Field
from subprocess import Popen, PIPE, DEVNULL, check_output, CalledProcessError
from typing import Optional, TextIO, Tuple, Literal, List, Union

from dockerdo import prettyprint
from dockerdo.config import Session, MountSpecs, BaseModel

verbose = False
dry_run = False
in_background = False


def set_execution_mode(verbose_mode: bool, dry_run_mode: bool) -> bool:
    """Set the execution mode"""
    global verbose, dry_run, in_background
    verbose = verbose_mode or dry_run_mode
    dry_run = dry_run_mode
    in_background = detect_background()
    return in_background


def get_user_config_dir() -> Path:
    """Get the user config directory"""
    return Path("~/.config/dockerdo").expanduser()


def get_container_work_dir(session: Session) -> Optional[Path]:
    """
    Get the container work directory.
    Remove the prefix corresponding to the container mount point from the current working directory.
    If the current working directory is not inside any mount point, return None.
    """
    current_work_dir = Path(os.getcwd())
    for mount_specs in session.mounts:
        if mount_specs.near_host == "local" and current_work_dir.is_relative_to(mount_specs.near_path):
            return Path("/") / current_work_dir.relative_to(mount_specs.near_path)
    return None


def run_local_command(command: str, cwd: Path = Path.cwd(), silent: bool = False) -> int:
    """
    Run a command on the local host, piping through stdin, stdout, and stderr.
    The command may be potentially long-lived and both read and write large amounts of data.
    """
    stdout: int | TextIO
    stderr: int | TextIO
    if silent:
        stdout = DEVNULL
        stderr = DEVNULL
    else:
        stdout = sys.stdout
        stderr = sys.stderr
        if verbose:
            print(f"+ {command}", file=sys.stderr)
    args = shlex.split(command)
    if not dry_run:
        with Popen(
            args, stdin=sys.stdin, stdout=stdout, stderr=stderr, cwd=cwd
        ) as process:
            process.wait()
            return process.returncode
    else:
        return 0


def make_remote_command(command: str, session: Session) -> str:
    """
    Wrap a command in ssh to run on the remote host.
    """
    escaped_command = " ".join(shlex.quote(token) for token in shlex.split(command))
    # ssh-socket-remote created when activating the session
    wrapped_command = (
        "ssh"
        f" -n -S {session.session_dir}/ssh-socket-remote"
        f" {session.remote_host}"
        f' "cd {session.remote_host_build_dir} && {escaped_command}"'
    )
    return wrapped_command


def run_remote_command(command: str, session: Session) -> int:
    """
    Run a command on the remote host, piping through stdout, and stderr.
    Stdin is not connected.
    """
    wrapped_command = make_remote_command(command, session)
    cwd = Path(os.getcwd())
    return run_local_command(wrapped_command, cwd=cwd)


def ssh_stdin_flags(interactive: bool, session: Session) -> str:
    """Get the stdin flags for ssh"""
    if not sys.stdin.isatty():
        # Data is being piped into dodo
        # We can not use the ssh master socket, and shouldn't create a tty
        return ""
    else:
        if interactive:
            # The user wants to interact with the command
            # We can not use the ssh master socket, and should create a tty.
            # Quiet suppresses an annoying log message
            return "-t -q"
        else:
            # Not interactive: we can use the ssh master socket
            # To make sure that stdin is not used (this would hang), we specify -n
            return f"-n -S {session.session_dir}/ssh-socket-container"


def run_container_command(command: str, session: Session, interactive: bool = False) -> Tuple[int, Path]:
    """
    Run a command on the container, piping through stdin, stdout, and stderr.
    """
    container_work_dir = get_container_work_dir(session)
    if not container_work_dir:
        prettyprint.error(
            "Current working directory is not inside any container mount point"
        )
        return 1, Path()
    escaped_command = " ".join(shlex.quote(token) for token in shlex.split(command))
    flags = ssh_stdin_flags(interactive, session)
    assert session.ssh_port_on_remote_host is not None
    wrapped_command = (
        f"ssh {flags}"
        f" {session.container_host_alias}"
        f' "source {session.env_file_path} && cd {container_work_dir} && {escaped_command}"'
    )
    cwd = Path(os.getcwd())
    return run_local_command(wrapped_command, cwd=cwd), container_work_dir


def run_docker_save_pipe(
    image_tag: str, local_work_dir: Path, sshfs_remote_mount_point: Path
) -> int:
    """Run docker save, piping the output via pigz to compress it, and finally into a file"""
    try:
        command = f"docker save {image_tag}"
        output_path = sshfs_remote_mount_point / f"{image_tag}.tar.gz"
        if verbose:
            print(f"+ {command} | pigz > {output_path}", file=sys.stderr)
        args = shlex.split(command)
        if not dry_run:
            with Popen(args, stdout=PIPE, cwd=local_work_dir) as docker:
                output = check_output(("pigz"), stdin=docker.stdout)
                with open(output_path, "wb") as fout:
                    fout.write(output)
    except CalledProcessError as e:
        prettyprint.error(f"Error running docker save: {e}")
        return e.returncode
    return 0


def parse_docker_ps_output(output: str) -> Optional[str]:
    """Helper to parse docker ps output"""
    if len(output) == 0:
        return None
    state = json.loads(output).get("State", None)
    if state is None:
        return None
    return str(state)


def determine_acceptable_container_state(
    actual_state: Optional[str],
) -> Literal["nothing", "running", "stopped"] | None:
    """Helper to determine container state from parsed info"""
    if actual_state is None:
        return "nothing"
    if actual_state == "running":
        return "running"
    elif actual_state in {"exited", "paused", "dead", "restarting", "created"}:
        return "stopped"
    else:
        return None


def verify_container_state(session: Session) -> bool:
    """Orchestrates the container state verification"""
    command = f"docker ps -a --filter name={session.container_name} --format json"
    if session.remote_host is not None:
        command = make_remote_command(command, session)

    if verbose:
        print(f"+ {command}", file=sys.stderr)
    if dry_run:
        return session.container_state == "running"

    try:
        output = check_output(shlex.split(command), cwd=session.local_work_dir)
    except CalledProcessError as e:
        prettyprint.error(f"Error running docker ps: {e}")
        return False

    try:
        actual_state = parse_docker_ps_output(output.decode("utf-8"))
    except json.JSONDecodeError as e:
        prettyprint.error(f"Error decoding docker ps output: {e}")
        return False

    acceptable_state = determine_acceptable_container_state(actual_state)
    if acceptable_state is None:
        prettyprint.error(f"Unexpected container state: {actual_state}")
        return False
    if actual_state is None:
        actual_state = "no container"

    if session.container_state != acceptable_state:
        prettyprint.warning(f"Expected container state {session.container_state}, but found {actual_state}")
    session.container_state = acceptable_state
    return acceptable_state == "running"


def run_ssh_master_process(session: Session) -> Optional[Popen]:
    """Runs an ssh command with the -M option to create a master connection. This will run indefinitely."""
    # Note that ssh options, such as the jump host, are set in the dockerdo dynamic ssh config file.
    command = (
        f"ssh -M -N -S {session.session_dir}/ssh-socket-container {session.container_host_alias}"
    )
    if verbose:
        print(f"+ {command}", file=sys.stderr)
    if not dry_run:
        try:
            return Popen(
                shlex.split(command), stdin=None, stdout=None, stderr=None, cwd=session.local_work_dir
            )
        except CalledProcessError as e:
            prettyprint.error(f"Error running ssh master process: {e}")
            return None
    else:
        return None


def detect_background() -> bool:
    """Detect if the process is running in the background"""
    try:
        return os.getpgrp() != os.tcgetpgrp(sys.stdout.fileno())
    except OSError:
        return True


def detect_ssh_agent() -> bool:
    """Detect if the ssh agent is running, and there is at least one key in it"""
    if "SSH_AUTH_SOCK" not in os.environ:
        return False
    try:
        output = check_output(["ssh-add", "-l"])
        return len(output) > 0
    except CalledProcessError:
        return False


def ssh_keyscan(session: Session) -> List[str]:
    """Scan the ssh key of the container"""
    if session.remote_host is None:
        command = f"ssh-keyscan -p {session.ssh_port_on_remote_host} localhost"
    else:
        # ssh-keyscan doesn't support jumps, so we must run it on the remote host
        command = (
            "ssh"
            f" -n -S {session.session_dir}/ssh-socket-remote"
            f" {session.remote_host}"
            ' "'
            f'ssh-keyscan -p {session.ssh_port_on_remote_host} localhost |'
            r' sed -e \"s/localhost/$(hostname --short)/\"'
            '"'
        )
    if verbose:
        print(f"+ {command}", file=sys.stderr)
    if not dry_run:
        try:
            output = check_output(shlex.split(command), stderr=DEVNULL)
            return [line.strip() for line in output.decode('utf-8').split('\n')]
        except CalledProcessError:
            return []
    else:
        return []


# ## Sshfs and mutagen mounts


class MutagenEndpointLocal(BaseModel):
    protocol: Literal["local"] = "local"
    path: Path
    directories: int = 0
    files: int = 0
    symbolicLinks: int = 0


class MutagenEndpointSsh(BaseModel):
    protocol: Literal["ssh"] = "ssh"
    path: Path
    user: str
    host: str
    port: int
    directories: int = 0
    files: int = 0
    symbolicLinks: int = 0


class MutagenStatus(BaseModel):
    """Status of a mutagen sync. Only the fields we care about."""

    identifier: str
    alpha: Union[MutagenEndpointLocal, MutagenEndpointSsh] = Field(discriminator="protocol")
    beta: Union[MutagenEndpointLocal, MutagenEndpointSsh] = Field(discriminator="protocol")
    status: str


def ensure_mounts(session: Session) -> None:
    """
    Ensure that the mounts are active.

    Idempotent: if a mount is already active, does nothing.
    Note that this function causes prettyprint.LongAction logging.
    """
    mutagen_status: Optional[List[MutagenStatus]]
    if any(mount_specs.mount_type == "mutagen" for mount_specs in session.mounts):
        mutagen_status = get_mutagen_status(session)
        if dry_run:
            return
        if mutagen_status is None:
            prettyprint.error("Failed to get mutagen status")
            return
    else:
        mutagen_status = None
    for mount_specs in session.mounts:
        if mount_specs.mount_type == "sshfs":
            ensure_sshfs_mount(mount_specs, session)
        elif mount_specs.mount_type == "mutagen":
            assert mutagen_status is not None
            ensure_mutagen_mount(mount_specs, mutagen_status, session)
        elif mount_specs.mount_type == "docker":
            # Docker mounts can only be made when starting the container
            pass
        else:
            raise ValueError(f"Unknown mount type {mount_specs.mount_type}")


def ensure_sshfs_mount(mount_specs: MountSpecs, session: Session) -> None:
    """Ensure that the sshfs mount is active"""
    assert mount_specs.mount_type == "sshfs"
    # check if already mounted
    if mount_specs.near_path.is_mount():
        return

    # mount
    far_host = mount_specs.get_far_host_name(session)
    ctx_mgr: AbstractContextManager
    if not in_background:
        ctx_mgr = prettyprint.LongAction(
            host="local",
            running_verb="Mounting" if not dry_run else "Would mount",
            done_verb="Mounted" if not dry_run else "Would mount",
            running_message=mount_specs.descr_str(),
        )
    else:
        ctx_mgr = nullcontext()
    with ctx_mgr as task:
        if not dry_run:
            os.makedirs(mount_specs.near_path, exist_ok=True)
        retval = run_local_command(
            f"sshfs "
            f" {far_host}:{mount_specs.far_path}"
            f" {mount_specs.near_path}",
            cwd=session.local_work_dir,
            silent=in_background,
        )
        if retval != 0:
            raise Exception(f"Failed to mount {mount_specs.descr_str()}")
        if task and mount_specs.near_path.is_mount():
            task.set_status("OK")
        if dry_run:
            task.set_status("OK")


def ensure_mutagen_mount(mount_specs: MountSpecs, mutagen_status: List[MutagenStatus], session: Session) -> None:
    """Ensure that the mutagen sync is active"""
    assert mount_specs.mount_type == "mutagen"

    # check if already mounted
    for status in mutagen_status:
        if status.identifier == mount_specs.mutagen_id:
            if status.status == "watching":
                return

    # mount
    far_host = mount_specs.get_far_host_name(session)
    ctx_mgr: AbstractContextManager
    if not in_background:
        ctx_mgr = prettyprint.LongAction(
            host="local",
            running_verb="Mounting" if not dry_run else "Would mount",
            done_verb="Mounted" if not dry_run else "Would mount",
            running_message=mount_specs.descr_str(),
        )
    else:
        ctx_mgr = nullcontext()
    with ctx_mgr as task:
        if not dry_run:
            os.makedirs(mount_specs.near_path, exist_ok=True)
        # FIXME: parse to get id "Created session sync_..."
        retval = run_local_command(
            f"mutagen sync create"
            f" {mount_specs.near_path}"
            f" {far_host}:{mount_specs.far_path}",
            cwd=session.local_work_dir,
            silent=in_background,
        )
        if retval != 0:
            raise Exception(f"Failed to mount {mount_specs.descr_str()}")
        if task:
            task.set_status("OK")
        if dry_run:
            task.set_status("OK")


def stop_mounts(session: Session) -> None:
    """
    Stop all mounts.

    Idempotent: if a mount is not active, does nothing.
    Note that this function causes prettyprint.LongAction logging.
    """
    for mount_specs in session.mounts:
        if mount_specs.mount_type == "sshfs":
            stop_sshfs_mount(mount_specs)
        elif mount_specs.mount_type == "mutagen":
            stop_mutagen_mount(mount_specs)
        elif mount_specs.mount_type == "docker":
            pass
        else:
            raise ValueError(f"Unknown mount type {mount_specs.mount_type}")


def stop_sshfs_mount(mount_specs: MountSpecs) -> None:
    """Unmount the sshfs mount"""
    assert mount_specs.mount_type == "sshfs"
    if not mount_specs.near_path.is_mount():
        return
    with prettyprint.LongAction(
        host="local",
        running_verb="Unmounting",
        done_verb="Unmounted" if not dry_run else "Would unmount",
        running_message="container filesystem",
    ) as task:
        run_local_command(f"fusermount -u {mount_specs.near_path}")
        task.set_status("OK")


def stop_mutagen_mount(mount_specs: MountSpecs) -> None:
    """Stop the mutagen sync"""
    assert mount_specs.mount_type == "mutagen"
    if mount_specs.mutagen_id is None:
        return
    with prettyprint.LongAction(
        host="local",
        running_verb="Stopping",
        done_verb="Stopped" if not dry_run else "Would stop",
        running_message="mutagen sync",
    ) as task:
        run_local_command(f"mutagen sync pause {mount_specs.mutagen_id}")
        task.set_status("OK")


def remove_mounts(session: Session) -> None:
    """
    Permanently remove all mounts.
    """
    pass
    for mount_specs in session.mounts:
        if mount_specs.mount_type == "sshfs":
            # for sshfs stop equals remove
            stop_sshfs_mount(mount_specs)
        elif mount_specs.mount_type == "mutagen":
            remove_mutagen_mount(mount_specs)
        elif mount_specs.mount_type == "docker":
            pass
        else:
            raise ValueError(f"Unknown mount type {mount_specs.mount_type}")


def remove_mutagen_mount(mount_specs: MountSpecs) -> None:
    """Permanently remove the mutagen sync"""
    assert mount_specs.mount_type == "mutagen"
    if mount_specs.mutagen_id is None:
        return
    with prettyprint.LongAction(
        host="local",
        running_verb="Stopping",
        done_verb="Stopped" if not dry_run else "Would stop",
        running_message="mutagen sync",
    ) as task:
        run_local_command(f"mutagen sync terminate {mount_specs.mutagen_id}")
        task.set_status("OK")


def parse_mutagen_status(output: str) -> List[MutagenStatus]:
    """Parse the output of mutagen sync list"""
    return [MutagenStatus(**x) for x in json.loads(output)]


def get_mutagen_status(session: Session) -> Optional[List[MutagenStatus]]:
    """Get the status of all mutagen syncs"""
    command = 'mutagen sync list --template "{{ json . }}"'
    if session.remote_host is not None:
        command = make_remote_command(command, session)

    if verbose:
        print(f"+ {command}", file=sys.stderr)
    if dry_run:
        return None

    try:
        output = check_output(shlex.split(command), cwd=session.local_work_dir)
    except CalledProcessError as e:
        prettyprint.error(f"Error running mutagen sync list: {e}")
        return None

    try:
        return parse_mutagen_status(output.decode("utf-8"))
    except json.JSONDecodeError as e:
        prettyprint.error(f"Error decoding mutagen status: {e}")
        return None
    except ValidationError as e:
        prettyprint.error(f"Error validating mutagen status: {e}")
        return None


def write_container_env_file(session: Session) -> None:
    """Place the container env file inside the container"""
    # Write the env file in a temporary file on the host, then copy it to the container
    tmp_env_file = session.session_dir / "env.list"
    session.write_env_file(tmp_env_file)
    # Use scp to copy the file to the container
    command = f"scp {tmp_env_file} {session.container_host_alias}:{session.env_file_path}"
    run_local_command(command, cwd=session.local_work_dir, silent=not verbose)
    # Remove the temporary file
    tmp_env_file.unlink()
