"""Shell related functions"""

import shlex
import sys
from subprocess import Popen


def run_command(command: str) -> int:
    """
    Run a command on the local host, piping through stdin, stdout, and stderr.
    The command may be potentially long-lived and both read and write large amounts of data.
    """
    args = shlex.split(command)
    with Popen(args, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr) as process:
        process.wait()
        return process.returncode
