"""User configuration and session data"""

import yaml
from pathlib import Path
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field
from tempfile import mkdtemp
from typing import Optional, Set, Literal

from dockerdo.utils import ephemeral_container_name
from dockerdo import prettyprint


class BaseModel(PydanticBaseModel):
    """Extend Pydantic BaseModel with common functionality"""

    class Config:
        """Pydantic config"""
        extra = "ignore"

    def model_dump_yaml(self) -> str:
        """Dump the model as yaml"""
        return yaml.dump(self.model_dump(mode="json"), sort_keys=True)


class UserConfig(BaseModel):
    """User configuration for dockerdo"""

    default_remote_host: Optional[str] = None
    default_image: str = "ubuntu:latest"
    default_docker_registry: Optional[str] = None
    always_record_inotify: bool = False

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "UserConfig":
        """Load the config from yaml"""
        return cls(**yaml.safe_load(yaml_str))


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
    local_work_dir: Optional[Path] = None
    modified_files: Set[Path] = set()
    container_state: Literal["nothing", "created", "running", "stopped"] = "nothing"

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

    @classmethod
    def from_opts(
        cls,
        session_name: Optional[str],
        container_name: Optional[str],
        remote_host: Optional[str],
        local: bool,
        base_image: Optional[str],
        docker_registry: Optional[str],
        record_inotify: bool,
        remote_host_build_dir: Path,
        user_config: UserConfig,
    ) -> "Session":
        if session_name is None:
            session_dir = Path(mkdtemp(prefix="dockerdo_"))
            prettyprint.action(f"Created ephemeral session directory {session_dir}")
            session_name = session_dir.name.replace("dockerdo_", "")
        else:
            session_dir = Path(f"~/.local/share/dockerdo/{session_name}").expanduser()
        if container_name is None:
            container_name = ephemeral_container_name()
        base_image = base_image if base_image is not None else user_config.default_image
        if local:
            remote_host = None
        else:
            remote_host = remote_host if remote_host is not None else user_config.default_remote_host
        registry = docker_registry if docker_registry is not None else user_config.default_docker_registry
        record_inotify = record_inotify or user_config.always_record_inotify
        session = Session(
            name=session_name,
            container_name=container_name,
            remote_host=remote_host,
            base_image=base_image,
            docker_registry=registry,
            record_inotify=record_inotify,
            session_dir=session_dir,
            remote_host_build_dir=remote_host_build_dir,
        )
        return session

    def save(self) -> None:
        """Save the session to a file in the session directory"""
        session_file = self.session_dir / "session.yaml"
        if not self.session_dir.exists():
            self.session_dir.mkdir(parents=True, exist_ok=True)
            prettyprint.action(f"Created persistent session directory {self.session_dir}")
        with open(session_file, "w") as f:
            f.write(self.model_dump_yaml())

    @classmethod
    def load(cls, session_dir: Path) -> "Session":
        """Load the session from a file in the session directory"""
        session_file = session_dir / "session.yaml"
        with open(session_file, "r") as f:
            return cls(**yaml.safe_load(f.read()))

    def write_activate_script(self) -> Path:
        """Write the activate script to a file in the session directory"""
        activate_script = self.session_dir / "activate"
        with open(activate_script, "w") as f:
            f.write(f"export DOCKERDO_SESSION_DIR={self.session_dir}\n")
            f.write(f"export DOCKERDO_SESSION_NAME={self.name}\n")
        activate_script.chmod(0o755)
        return activate_script
