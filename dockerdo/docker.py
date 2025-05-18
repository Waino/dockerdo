"""Docker related functions"""

from pathlib import Path

GENERIC_DOCKERFILE = r"""
# syntax=docker/dockerfile:1
# check=skip=SecretsUsedInArgOrEnv
# We *do* want to bake the ssh public key into the image
FROM {image} AS base

ARG SSH_PUB_KEY
RUN {package_install}
RUN mkdir -p /var/run/sshd \
    && mkdir -p {homedir}/.ssh \
    && chmod 700 {homedir}/.ssh \
    && echo "$SSH_PUB_KEY" > {homedir}/.ssh/authorized_keys \
    && chmod 600 {homedir}/.ssh/authorized_keys \
    && ssh-keygen -A

CMD ["{shell}", "-c", "/usr/sbin/sshd -D && sleep infinity"]
""".strip()

DOCKERFILES = {
    "ubuntu": (
        GENERIC_DOCKERFILE,
        {
            "package_install": "apt-get update && apt-get install -y openssh-server && rm -rf /var/lib/apt/lists/*",
            "shell": "/bin/bash",
        },
    ),
    "alpine": (
        GENERIC_DOCKERFILE,
        {
            "package_install": "apk add openssh-server openssh-client",
            "shell": "/bin/sh",
        },
    ),
}
DISTROS = list(DOCKERFILES.keys())


def format_dockerfile(
    distro: str,
    image: str,
    homedir: Path,
) -> str:
    """Format a Dockerfile"""
    dockerfile, kwargs = DOCKERFILES[distro]
    return dockerfile.format(
        image=image,
        homedir=homedir,
        **kwargs,
    )
