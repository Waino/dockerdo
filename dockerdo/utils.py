"""Utility functions for dockerdo"""

import random
import string
import time
from pathlib import Path
from typing import Optional


def ephemeral_container_name() -> str:
    """
    Generate a probably unique name for an ephemeral container.
    The name consists of 10 random lowercase letters followed by a unix timestamp.
    """
    letters = "".join(random.choices(string.ascii_lowercase, k=10))
    timestamp = int(time.time())
    name = f"{letters}{timestamp}"
    return name


def make_image_tag(
    docker_registry: Optional[str],
    base_image: str,
    session_name: str,
    image_name_template: str = "dockerdo-{base_image}:{base_image_tag}-{session_name}",
) -> str:
    if ":" in base_image:
        base_image, base_image_tag = base_image.split(":")
    else:
        base_image_tag = "latest"
    if "/" in base_image:
        base_image = base_image.split("/")[-1]
    image_tag = image_name_template.format(
        base_image=base_image,
        base_image_tag=base_image_tag,
        session_name=session_name,
    )
    if docker_registry is None or len(docker_registry) == 0:
        return image_tag
    else:
        return f"{docker_registry}/{image_tag}"


def empty_or_nonexistent(path: Path) -> bool:
    """Check if a path is empty or nonexistent"""
    return not path.exists() or not any(path.iterdir())
