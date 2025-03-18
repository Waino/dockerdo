"""Docker related functions"""

from pathlib import Path

GENERIC_DOCKERFILE = r"""
FROM {image} as base

ARG SSH_KEY
RUN {package_install} \
    && mkdir -p /var/run/sshd \
    && mkdir -p {homedir}/.ssh \
    && chmod 700 {homedir}/.ssh \
    && echo "$SSH_KEY" > {homedir}/.ssh/authorized_keys \
    && chmod 600 {homedir}/.ssh/authorized_keys

CMD ["/usr/sbin/sshd", "-D", "&&", "sleep", "infinity"]
""".strip()

DOCKERFILES = {
    "ubuntu": (
        GENERIC_DOCKERFILE,
        {"package_install": "apt-get update && apt-get install -y openssh-server"},
    ),
    "alpine": (
        GENERIC_DOCKERFILE,
        {"package_install": "apk add openssh-server"},
    ),
}
DISTROS = list(DOCKERFILES.keys())


def format_dockerfile(
    distro: str,
    image: str,
    homedir: Path,
    ssh_key_path: Path,
) -> str:
    """Format a Dockerfile"""
    dockerfile, kwargs = DOCKERFILES[distro]
    return dockerfile.format(
        image=image,
        homedir=homedir,
        ssh_key_path=ssh_key_path,
        **kwargs,
    )
