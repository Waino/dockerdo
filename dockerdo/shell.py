"""Shell related functions"""

import json
import os
import shlex
import sys
from pathlib import Path
from subprocess import Popen, PIPE, DEVNULL, check_output, CalledProcessError
from typing import Optional, TextIO, Tuple, Literal

from dockerdo import prettyprint
from dockerdo.config import Session

verbose = False
dry_run = False


def set_execution_mode(verbose_mode: bool, dry_run_mode: bool) -> None:
    """Set the execution mode"""
    global verbose, dry_run
    verbose = verbose_mode or dry_run_mode
    dry_run = dry_run_mode


def get_user_config_dir() -> Path:
    """Get the user config directory"""
    return Path("~/.config/dockerdo").expanduser()


def get_container_work_dir(session: Session) -> Optional[Path]:
    """
    Get the container work directory.
    Remove the prefix corresponding to the sshfs_container_mount_point from the current working directory.
    If the current working directory is not inside the local work directory, return None.
    """
    current_work_dir = Path(os.getcwd())
    if current_work_dir.is_relative_to(session.sshfs_container_mount_point):
        return Path("/") / current_work_dir.relative_to(
            session.sshfs_container_mount_point
        )
    else:
        return None


def run_local_command(command: str, cwd: Path, silent: bool = False) -> int:
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
            f"Current working directory is not inside the container mount point {session.sshfs_container_mount_point}"
        )
        return 1, Path()
    escaped_command = " ".join(shlex.quote(token) for token in shlex.split(command))
    flags = ssh_stdin_flags(interactive, session)
    assert session.ssh_port_on_remote_host is not None
    if session.remote_host is None:
        # remote_host is the same as local_host
        wrapped_command = (
            f"ssh {flags}"
            f" -p {session.ssh_port_on_remote_host}"
            f" {session.container_username}@localhost"
            " -o StrictHostKeyChecking=no"
            f' "source {session.env_file_path} && cd {container_work_dir} && {escaped_command}"'
        )
    else:
        # remote_host is different from local_host, so jump via remote_host to container
        wrapped_command = (
            f"ssh {flags}"
            f" -J {session.remote_host}"
            f" -p {session.ssh_port_on_remote_host}"
            f" {session.container_username}@{session.remote_host}"
            " -o StrictHostKeyChecking=no"
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
    except json.JSONDecodeError as e:
        prettyprint.error(f"Error decoding docker ps output: {e}")
        return False

    actual_state = parse_docker_ps_output(output.decode("utf-8"))
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


def run_ssh_master_process(session: Session, remote_host: str, ssh_port_on_remote_host: int) -> Optional[Popen]:
    """Runs an ssh command with the -M option to create a master connection. This will run indefinitely."""
    if session.remote_host is None:
        jump_flag = ""
    else:
        jump_flag = f"-J {session.remote_host}"
    command = (
        f"ssh {jump_flag} -M -N -S {session.session_dir}/ssh-socket-container -p {ssh_port_on_remote_host}"
        f" {session.container_username}@{remote_host} -o StrictHostKeyChecking=no"
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
