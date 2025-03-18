"""Docker related functions"""

from pathlib import Path

UBUNTU_DOCKERFILE = r"""
FROM {image} as base

ARG SSH_KEY
RUN apt-get update && apt-get install -y openssh-server \
    && mkdir -p /var/run/sshd \
    && mkdir -p {homedir}/.ssh \
    && chmod 700 {homedir}/.ssh \
    && echo "$SSH_KEY" > {homedir}/.ssh/authorized_keys \
    && chmod 600 {homedir}/.ssh/authorized_keys

CMD ["/usr/sbin/sshd", "-D", "&&", "sleep", "infinity"]
""".strip()

ALPINE_DOCKERFILE = r"""
FROM {image} as base

ARG SSH_KEY
RUN apk add openssh-server \
    && mkdir -p /var/run/sshd \
    && mkdir -p {homedir}/.ssh \
    && chmod 700 {homedir}/.ssh \
    && echo "$SSH_KEY" > {homedir}/.ssh/authorized_keys \
    && chmod 600 {homedir}/.ssh/authorized_keys

CMD ["/usr/sbin/sshd", "-D", "&&", "sleep", "infinity"]
""".strip()

DOCKERFILES = {
    "ubuntu": UBUNTU_DOCKERFILE,
    "alpine": ALPINE_DOCKERFILE,
}
DISTROS = list(DOCKERFILES.keys())


def format_dockerfile(
    distro: str,
    image: str,
    homedir: Path,
    ssh_key_path: Path,
) -> str:
    """Format a Dockerfile"""
    return DOCKERFILES[distro].format(
        image=image,
        homedir=homedir,
        ssh_key_path=ssh_key_path,
    )
