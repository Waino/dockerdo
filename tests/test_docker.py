"""Test the docker module"""
from pathlib import Path

from dockerdo.docker import format_dockerfile

EXPECTED_UBUNTU_DOCKERFILE = r"""
# syntax=docker/dockerfile:1
# check=skip=SecretsUsedInArgOrEnv
# We *do* want to bake the ssh public key into the image
FROM ubuntu:latest AS base

ARG SSH_PUB_KEY
RUN apt-get update && apt-get install -y openssh-server && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /var/run/sshd \
    && mkdir -p /root/.ssh \
    && chmod 700 /root/.ssh \
    && echo "$SSH_PUB_KEY" > /root/.ssh/authorized_keys \
    && chmod 600 /root/.ssh/authorized_keys \
    && ssh-keygen -A

CMD ["/bin/bash", "-c", "/usr/sbin/sshd -D && sleep infinity"]
""".strip()


def test_ubuntu_dockerfile():
    result = format_dockerfile("ubuntu", "ubuntu:latest", Path("/root"))
    assert result == EXPECTED_UBUNTU_DOCKERFILE
