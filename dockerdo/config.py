"""User configuration and session data"""

from pydantic import BaseModel, Field
from typing import Optional


class UserConfig(BaseModel):
    """User configuration for dockerdo"""
    default_remote_host: str = "localhost"
    default_image: str = "ubuntu:latest"
    default_docker_registry: Optional[str] = None
    record_inotify: bool = False


class Session(BaseModel):
    """Session data for dockerdo"""
    name: str
    env: dict[str, str] = Field(default_factory=dict)
    remote_host: str
    image: str
    docker_registry: Optional[str] = None
    record_inotify: bool = False
