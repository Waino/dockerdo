from copy import deepcopy
from pathlib import Path
from typing import Dict, List
import re

from dockerdo.config import Session
from dockerdo.shell import ssh_keyscan

RE_LEADING_SPACE = re.compile(r"^\s*")

# HostName is always localhost: when running locally the container is on localhost,
# and when running remotely we jump to the remote host and from there on to the container port published by docker
HOST_BLOCK = """
Host {session.container_host_alias}*
    Hostname localhost
    Port {session.ssh_port_on_remote_host}
    User {session.container_username}
    StrictHostKeyChecking no
    IdentityFile {session.ssh_key_path}
    UserKnownHostsFile /dev/null
""".strip()

# Mutagen would fail to connect to the container unless the ControlPath is set in the ssh config
HOST_BLOCK_WITH_SOCKET = """
Host {session.container_host_alias}_socket
    ControlPath {session.session_dir}/ssh-socket-container
""".strip()

PROXY_JUMP_BLOCK = "    ProxyJump {session.remote_host}"

SSH_INCLUDE_BLOCK = """
# Dynamic host blocks. Added by dockerdo
Host dockerdo_*
    Include ~/.ssh/config.dockerdo
""".strip()

DEFAULT_SSH_CONFIG_PATH = Path("~/.ssh/config.dockerdo")


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


def parse_ssh_config(
    ssh_config_path: Path = DEFAULT_SSH_CONFIG_PATH,
) -> Dict[str, List[str]]:
    """Parse the ssh config file into host blocks"""
    ssh_config_path = ssh_config_path.expanduser()
    if not ssh_config_path.exists():
        return {}
    host_name = None
    host_blocks = {}
    with ssh_config_path.open("r") as fin:
        for line in fin:
            if len(line.strip()) == 0 or line.startswith("#"):
                continue
            leading_spaces = RE_LEADING_SPACE.match(line)
            assert leading_spaces is not None   # due to Kleene star
            n_leading_spaces = len(leading_spaces.group())
            line = line.rstrip('\n')
            if n_leading_spaces == 0:
                cmd, host_name = line.split()
                if not cmd == 'Host':
                    raise ValueError(f"Expected Host, got {cmd!r} in {line!r}")
                host_blocks[host_name] = [line]
            else:
                if host_name is None:
                    raise ValueError(f"Found indented line {line!r} before any host block")
                host_blocks[host_name].append(line)
    return host_blocks


def add_session_to_ssh_config(host_blocks: Dict[str, List[str]], session: Session) -> Dict[str, List[str]]:
    """
    Add the session to the ssh config file.

    If the session already exists, overwrite it.
    Returns True if the session was overwritten.
    """
    host_blocks = deepcopy(host_blocks)
    host_blocks[session.container_host_alias] = HOST_BLOCK.format(session=session).split("\n")
    host_blocks[f"{session.container_host_alias}_socket"] = HOST_BLOCK_WITH_SOCKET.format(session=session).split("\n")
    if session.remote_host is not None:
        host_blocks[session.container_host_alias].append(
            PROXY_JUMP_BLOCK.format(session=session)
        )
    return host_blocks


def write_ssh_config(
    host_blocks: Dict[str, List[str]],
    ssh_config_path: Path = DEFAULT_SSH_CONFIG_PATH,
) -> None:
    ssh_config_path = ssh_config_path.expanduser()
    with ssh_config_path.open("w") as fout:
        for host_name, block in host_blocks.items():
            for line in block:
                line = line.rstrip('\n')
                fout.write(f"{line}\n")
            fout.write("\n")


def ensure_session_in_ssh_config(
    session: Session,
    ssh_config_path: Path = DEFAULT_SSH_CONFIG_PATH,
) -> bool:
    """
    Add the session to the ssh config file.

    If the session already exists, overwrite it.
    Returns True if the session was overwritten.
    """
    ssh_config_path = ssh_config_path.expanduser()
    host_blocks = parse_ssh_config(ssh_config_path)
    overwritten = session.container_host_alias in host_blocks
    host_blocks = add_session_to_ssh_config(host_blocks, session)
    write_ssh_config(host_blocks, ssh_config_path)
    return overwritten


def remove_session_from_ssh_config(
    session: Session,
    ssh_config_path: Path = DEFAULT_SSH_CONFIG_PATH,
) -> None:
    ssh_config_path = ssh_config_path.expanduser()
    host_blocks = parse_ssh_config(ssh_config_path)
    n_keys = len(host_blocks)
    if session.container_host_alias in host_blocks:
        del host_blocks[session.container_host_alias]
    if f"{session.container_host_alias}_socket" in host_blocks:
        del host_blocks[f"{session.container_host_alias}_socket"]
    if len(host_blocks) == n_keys:
        # Nothing was removed
        return
    write_ssh_config(host_blocks, ssh_config_path)
