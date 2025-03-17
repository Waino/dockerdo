"""Shell related functions"""

import os
import shlex
import sys
from pathlib import Path
from subprocess import Popen
from typing import Optional

from dockerdo import prettyprint
from dockerdo.config import Session


def run_local_command(command: str) -> int:
    """
    Run a command on the local host, piping through stdin, stdout, and stderr.
    The command may be potentially long-lived and both read and write large amounts of data.
    """
    args = shlex.split(command)
    print(args)     # Debugging
    return 0
    if False:
        # FIXME: cwd required for docker build
        with Popen(args, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr) as process:
            process.wait()
            return process.returncode


def get_user_config_dir() -> Path:
    """Get the user config directory"""
    return Path("~/.config/dockerdo").expanduser()


def get_container_work_dir(session: Session) -> Optional[Path]:
    """
    Get the container work directory.
    Remove the prefix corresponding to the local work directory from the current working directory.
    If the current working directory is not inside the local work directory, return None.
    """
    if session.local_work_dir is None:
        prettyprint.warning("Session has no local work directory")
        return None
    current_work_dir = Path(os.getcwd())
    if current_work_dir.is_relative_to(session.local_work_dir):
        return current_work_dir.relative_to(session.local_work_dir)
    else:
        return None


def run_remote_command(command: str, session: Session) -> int:
    """
    Run a command on the remote host, piping through stdin, stdout, and stderr.
    """
    wrapped_command = (
        f"ssh -S {session.session_dir}/ssh-socket"
        f" {session.remote_host}"
        f' "cd {session.remote_host_build_dir} && {shlex.quote(command)}"'
    )
    return run_local_command(wrapped_command)


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
    return run_local_command(wrapped_command)
