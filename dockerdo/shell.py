"""Shell related functions"""

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
    Remove the prefix corresponding to the local work directory from the current working directory.
    If the current working directory is not inside the local work directory, return None.
    """
    current_work_dir = Path(os.getcwd())
    if current_work_dir.is_relative_to(session.local_work_dir):
        return current_work_dir.relative_to(session.local_work_dir)
    else:
        return None


def get_sshfs_remote_dir(session: Session) -> Optional[Path]:
    """Get the path on the local host where the remote host filesystem is mounted"""
    if session.remote_host is None:
        return None
    return session.local_work_dir / session.remote_host


def run_local_command(command: str, cwd: Path) -> int:
    """
    Run a command on the local host, piping through stdin, stdout, and stderr.
    The command may be potentially long-lived and both read and write large amounts of data.
    """
    args = shlex.split(command)
    print(" ".join(args))  # Debugging
    return 0
    if False:
        with Popen(
            args, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, cwd=cwd
        ) as process:
            process.wait()
            return process.returncode


def run_remote_command(command: str, session: Session) -> int:
    """
    Run a command on the remote host, piping through stdin, stdout, and stderr.
    """
    wrapped_command = (
        f"ssh -S {session.session_dir}/ssh-socket"
        f" {session.remote_host}"
        f' "cd {session.remote_host_build_dir} && {shlex.quote(command)}"'
    )
    cwd = Path(os.getcwd())
    return run_local_command(wrapped_command, cwd=cwd)


def run_container_command(command: str, session: Session) -> int:
    """
    Run a command on the container, piping through stdin, stdout, and stderr.
    """
    container_work_dir = get_container_work_dir(session)
    if session.remote_host is None:
        # remote_host is the same as local_host
        wrapped_command = (
            f"ssh -S {session.session_dir}/ssh-socket"
            f" {session.container_name}"
            f' "cd {container_work_dir} && {shlex.quote(command)}"'
        )
    else:
        wrapped_command = (
            f"ssh -S {session.session_dir}/ssh-socket"
            f" -J {session.remote_host} {session.container_name}"
            f' "cd {container_work_dir} && {shlex.quote(command)}"'
        )
    cwd = Path(os.getcwd())
    return run_local_command(wrapped_command, cwd=cwd)


def run_docker_save_pipe(
    image_tag: str, local_work_dir: Path, sshfs_remote_dir: Path
) -> int:
    """Run docker save, piping the output via pigz to compress it, and finally into a file"""
    try:
        args = shlex.split(f"docker save {image_tag}")
        with Popen(args, stdout=PIPE, cwd=local_work_dir) as docker:
            output = check_output(("pigz"), stdin=docker.stdout)
            with open(sshfs_remote_dir / f"{image_tag}.tar.gz", "wb") as fout:
                fout.write(output)
    except CalledProcessError as e:
        prettyprint.error(f"Error running docker save: {e}")
        return e.returncode
    return 0
