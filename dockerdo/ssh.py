from pathlib import Path

from dockerdo.config import Session
from dockerdo.shell import ssh_keyscan


def ensure_known_host_key(session: Session) -> None:
    known_hosts_path = Path("~/.ssh/known_hosts").expanduser()
    # scan host to get its key
    host_key_lines = ssh_keyscan(session=session)
    # remove lines that are already in the known_hosts file (expected to be noop)
    with known_hosts_path.open("r") as fin:
        for existing_line in fin:
            existing_line = existing_line.strip()
            host_key_lines = [line for line in host_key_lines if line != existing_line]
    # append remaining lines to the known_hosts file
    with known_hosts_path.open("a") as fout:
        for new_line in host_key_lines:
            fout.write(f"{new_line}\n")
    # store remaining lines in session for later removal
    session.host_key_lines = list(sorted(set(session.host_key_lines).union(host_key_lines)))


def remove_known_host_key(session: Session) -> None:
    known_hosts_path = Path("~/.ssh/known_hosts").expanduser()
    # read in the known_hosts file
    with known_hosts_path.open("r") as fin:
        all_lines = fin.readlines()
    # backup the known_hosts file
    with known_hosts_path.with_suffix(".dockerdo.orig").open("w") as backup_out:
        for line in all_lines:
            backup_out.write(line)
    # remove the lines added by this session
    host_key_lines = set(session.host_key_lines)
    kept_lines = [line for line in all_lines if line.strip() not in host_key_lines]
    with known_hosts_path.open("w") as fout:
        for kept_line in kept_lines:
            fout.write(kept_line)
