"""Shell related functions"""

import json
import os
import shlex
import sys
from pathlib import Path
from subprocess import Popen, PIPE, DEVNULL, check_output, CalledProcessError
from typing import Optional, TextIO, Tuple

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
    wrapped_command = (
        f"ssh -S {session.session_dir}/ssh-socket"
        f" {session.remote_host}"
        f' "cd {session.remote_host_build_dir} && {shlex.quote(command)}"'
    )
    return wrapped_command


def run_remote_command(command: str, session: Session) -> int:
    """
    Run a command on the remote host, piping through stdin, stdout, and stderr.
    """
    wrapped_command = make_remote_command(command, session)
    cwd = Path(os.getcwd())
    return run_local_command(wrapped_command, cwd=cwd)


def run_container_command(command: str, session: Session, set_env: str = "") -> Tuple[int, Path]:
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
    if session.remote_host is None:
        # remote_host is the same as local_host
        wrapped_command = (
            f"ssh -S {session.session_dir}/ssh-socket"
            f" -p {session.ssh_port_on_remote_host} {session.container_username}@localhost"
            " -o StrictHostKeyChecking=no"
            f" {set_env}"
            f' "cd {container_work_dir} && {escaped_command}"'
        )
    else:
        wrapped_command = (
            f"ssh -S {session.session_dir}/ssh-socket"
            f" -J {session.remote_host} -p {session.ssh_port_on_remote_host}"
            f" {session.container_username}@{session.remote_host}"
            " -o StrictHostKeyChecking=no"
            f" {set_env}"
            f' "cd {container_work_dir} && {escaped_command}"'
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


def verify_container_state(session: Session) -> bool:
    """
    Verify the container state.

    Updates the Session object, and returns True if the container is running.
    Prints a warning if the container state is unexpected.
    """
    command = f"docker ps -a --filter name={session.container_name} --format json"
    if session.remote_host is not None:
        command = make_remote_command(command, session)
    if verbose:
        print(f"+ {command}", file=sys.stderr)
    if dry_run:
        return session.container_state == "running"
    try:
        output = check_output(shlex.split(command), cwd=session.local_work_dir)
        if len(output) == 0:
            # no container found
            if session.container_state != "nothing":
                prettyprint.warning(f"Expected container state {session.container_state}, but no container found")
            session.container_state = "nothing"
            return False
        response_dict = json.loads(output)
        if response_dict["State"] == "running":
            # "running" is the only state that is acceptable when expected "running"
            if session.container_state != "running":
                prettyprint.warning(f"Expected container state {session.container_state}, but container is running")
            session.container_state = "running"
            return True
        elif response_dict["State"] in {"exited", "paused", "dead", "restarting", "created"}:
            # states considered acceptable when expected "stopped"
            if session.container_state != "stopped":
                prettyprint.warning(
                    f"Expected container state {session.container_state}, but container is {response_dict['State']}"
                )
            session.container_state = "stopped"
            return False
        else:
            prettyprint.error(f"Unexpected container state: {response_dict['State']}")
            return False
    except CalledProcessError as e:
        prettyprint.error(f"Error running docker ps: {e}")
        return False
    except json.JSONDecodeError as e:
        prettyprint.error(f"Error decoding docker ps output: {e}")
        return False


def run_ssh_master_process(session: Session, remote_host: str, ssh_port_on_remote_host: int) -> Optional[Popen]:
    """Runs an ssh command with the -M option to create a master connection. This will run indefinitely."""
    command = (
        f"ssh -M -N -S {session.session_dir}/ssh-socket -p {ssh_port_on_remote_host}"
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
    return os.getpgrp() != os.tcgetpgrp(sys.stdout.fileno())
