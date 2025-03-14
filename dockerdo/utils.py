"""Utility functions for dockerdo"""

import random
import string
import time
from pathlib import Path


def ephemeral_container_name() -> str:
    """
    Generate a probably unique name for an ephemeral container.
    The name consists of 10 random lowercase letters followed by a unix timestamp.
    """
    letters = "".join(random.choices(string.ascii_lowercase, k=10))
    timestamp = int(time.time())
    name = f"{letters}{timestamp}"
    return name


def empty_or_nonexistent(path: Path) -> bool:
    """Check if a path is empty or nonexistent"""
    return not path.exists() or not any(path.iterdir())
