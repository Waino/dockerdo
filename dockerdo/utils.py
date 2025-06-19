"""Utility functions for dockerdo"""

import random
import string
import time
from pathlib import Path
from typing import Optional, Callable, TypeVar

T = TypeVar("T")


def ephemeral_container_name() -> str:
    """
    Generate a probably unique name for an ephemeral container.
    The name consists of 10 random lowercase letters followed by a unix timestamp.
    """
    letters = "".join(random.choices(string.ascii_lowercase, k=10))
    timestamp = int(time.time())
    name = f"{letters}{timestamp}"
    return name


def make_image_reference(
    docker_registry_host: Optional[str],
    docker_registry_port: Optional[int],
    docker_namespace: Optional[str],
    base_image: str,
    session_name: str,
    image_name_template: str = "dockerdo-{base_image_repository}:{base_image_tag}-{session_name}",
) -> str:
    if ":" in base_image:
        base_image, base_image_tag = base_image.split(":")
    else:
        base_image_tag = "latest"
    if "/" in base_image:
        base_image_repository = base_image.split("/")[-1]
    else:
        base_image_repository = base_image
    image_name = image_name_template.format(
        base_image_repository=base_image_repository,
        base_image_tag=base_image_tag,
        session_name=session_name,
    )
    if docker_namespace is not None:
        image_name = f"{docker_namespace}/{image_name}"
    if docker_registry_host is None or len(docker_registry_host) == 0:
        return image_name
    else:
        docker_registry = docker_registry_host
        if docker_registry_port is not None:
            docker_registry += f":{docker_registry_port}"
        return f"{docker_registry}/{image_name}"


def empty_or_nonexistent(path: Path) -> bool:
    """Check if a path is empty or nonexistent"""
    return not path.exists() or not any(path.iterdir())


def retry(
    func: Callable[[], T],
    on_error: Callable[[Exception], None] = lambda e: None,
    retries: int = 10,
    delay: float = 2.0
) -> Optional[T]:
    """Retry a function call a number of times"""
    for i in range(retries):
        try:
            return func()
        except Exception as e:
            if i == retries - 1:
                raise
            else:
                on_error(e)
        time.sleep(delay)
    return None
