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
) -> str:
    if ':' in base_image:
        base_image, base_image_tag = base_image.split(':')
    else:
        base_image_tag = "latest"
    image_tag = f"dockerdo-{base_image}:{base_image_tag}-{session_name}"
    if docker_registry is None:
        return image_tag
    else:
        return f"{docker_registry}/{image_tag}"


def empty_or_nonexistent(path: Path) -> bool:
    """Check if a path is empty or nonexistent"""
    return not path.exists() or not any(path.iterdir())
