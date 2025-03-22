"""Shell related functions"""

import json
import os
import shlex
import sys
from pathlib import Path
from subprocess import Popen, PIPE, check_output, CalledProcessError
from typing import Optional

from dockerdo import prettyprint
from dockerdo.config import Session


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


def run_local_command(command: str, cwd: Path) -> int:
    """
    Run a command on the local host, piping through stdin, stdout, and stderr.
    The command may be potentially long-lived and both read and write large amounts of data.
    """
    print(command)  # Debugging
    args = shlex.split(command)
    return 0
    if False:
        with Popen(
            args, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, cwd=cwd
        ) as process:
            process.wait()
            return process.returncode


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


def run_container_command(command: str, session: Session) -> int:
    """
    Run a command on the container, piping through stdin, stdout, and stderr.
    """
    container_work_dir = get_container_work_dir(session)
    if not container_work_dir:
        prettyprint.error(
            f"Current working directory is not inside the container mount point {session.sshfs_container_mount_point}"
        )
        return 1
    escaped_command = " ".join(shlex.quote(token) for token in shlex.split(command))
    if session.remote_host is None:
        # remote_host is the same as local_host
        wrapped_command = (
            f"ssh -S {session.session_dir}/ssh-socket"
            f" -p {session.ssh_port_on_remote_host} {session.container_username}@localhost"
            " -o StrictHostKeyChecking=no"
            f' "cd {container_work_dir} && {escaped_command}"'
        )
    else:
        wrapped_command = (
            f"ssh -S {session.session_dir}/ssh-socket"
            f" -J {session.remote_host} -p {session.ssh_port_on_remote_host}"
            f" {session.container_username}@{session.remote_host}"
            " -o StrictHostKeyChecking=no"
            f' "cd {container_work_dir} && {escaped_command}"'
        )
    cwd = Path(os.getcwd())
    return run_local_command(wrapped_command, cwd=cwd)


def run_docker_save_pipe(
    image_tag: str, local_work_dir: Path, sshfs_remote_mount_point: Path
) -> int:
    """Run docker save, piping the output via pigz to compress it, and finally into a file"""
    try:
        args = shlex.split(f"docker save {image_tag}")
        with Popen(args, stdout=PIPE, cwd=local_work_dir) as docker:
            output = check_output(("pigz"), stdin=docker.stdout)
            with open(sshfs_remote_mount_point / f"{image_tag}.tar.gz", "wb") as fout:
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
    try:
        output = check_output(shlex.split(command), cwd=session.local_work_dir)
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


def run_ssh_master_process(session: Session, remote_host: str, ssh_port_on_remote_host: int) -> Popen:
    """Runs an ssh command with the -M option to create a master connection. This will run indefinitely."""
    command = (
        f"ssh -M -N -S {session.session_dir}/ssh-socket -p {ssh_port_on_remote_host}"
        f" {session.container_username}@{remote_host} -o StrictHostKeyChecking=no"
    )
    return Popen(
        shlex.split(command), stdin=None, stdout=None, stderr=None, cwd=session.local_work_dir
    )
