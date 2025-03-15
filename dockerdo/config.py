"""User configuration and session data"""

from pydantic import BaseModel, Field
from typing import Optional, Set
from pathlib import Path


class UserConfig(BaseModel):
    """User configuration for dockerdo"""
    default_remote_host: str = "localhost"
    default_image: str = "ubuntu:latest"
    default_docker_registry: Optional[str] = None
    record_inotify: bool = False


class Session(BaseModel):
    """A dockerdo session"""
    name: str
    container_name: str
    env: dict[str, str] = Field(default_factory=dict)
    remote_host: Optional[str] = None
    base_image: str
    docker_registry: Optional[str] = None
    record_inotify: bool = False
    session_dir: Path
    remote_host_build_dir: Path
    local_work_dir: Path
    modified_files: Set[Path] = set()

    def record_command(self, command: str) -> None:
        """
        Record a command in the session history.
        The command history is appended to a file in the session directory.
        """
        history_file = self.session_dir / "command_history"
        with open(history_file, "a") as f:
            f.write(f"{command}\n")

    def record_modified_file(self, file: Path) -> None:
        """Record a file write in the session history"""
        self.modified_files.add(file)

    def export(self, key: str, value: str) -> None:
        """Export a key-value pair to the session environment"""
        self.env[key] = value
        env_file = self.session_dir / "env.list"
        with open(env_file, "w") as f:
            for key, value in sorted(self.env.items()):
                f.write(f"{key}={value}\n")
