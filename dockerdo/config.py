"""User configuration and session data"""

import yaml
import json
from pathlib import Path
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, ConfigDict
from tempfile import mkdtemp
from typing import Optional, Set, Literal, Dict, List

from dockerdo.utils import ephemeral_container_name
from dockerdo import prettyprint


class BaseModel(PydanticBaseModel):
    """Extend Pydantic BaseModel with common functionality"""

    model_config = ConfigDict(extra='ignore')

    def model_dump_yaml(self, exclude: Optional[set[str]] = None) -> str:
        """Dump the model as yaml"""
        return yaml.dump(self.model_dump(mode="json", exclude=exclude), sort_keys=True)


class UserConfig(BaseModel):
    """User configuration for dockerdo"""

    default_remote_host: Optional[str] = None
    default_distro: str = "ubuntu"
    default_image: str = "ubuntu:latest"
    default_docker_registry: Optional[str] = None
    default_docker_run_args: str = ""
    always_record_inotify: bool = False
    ssh_key_path: Path = Path("~/.ssh/id_rsa.pub").expanduser()

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "UserConfig":
        """Load the config from yaml"""
        return cls(**yaml.safe_load(yaml_str))


class Session(BaseModel):
    """A dockerdo session"""

    name: str
    container_name: str
    env: Dict[str, str] = Field(default_factory=dict)
    remote_host: Optional[str] = None
    distro: str
    base_image: str
    image_tag: Optional[str] = None
    container_username: str = "root"
    docker_registry: Optional[str] = None
    record_inotify: bool = False
    session_dir: Path
    ssh_port_on_remote_host: Optional[int] = None
    remote_host_build_dir: Path
    local_work_dir: Path
    docker_run_args: Optional[str] = None

    modified_files: Set[Path] = set()
    container_state: Literal["nothing", "running", "stopped"] = "nothing"

    @classmethod
    def from_opts(
        cls,
        session_name: Optional[str],
        container_name: Optional[str],
        remote_host: Optional[str],
        local: bool,
        distro: Optional[str],
        base_image: Optional[str],
        container_username: str,
        docker_registry: Optional[str],
        record_inotify: bool,
        remote_host_build_dir: Path,
        local_work_dir: Path,
        user_config: UserConfig,
        dry_run: bool = False,
    ) -> Optional["Session"]:
        """
        Create a Session from command line options.
        This is only used in the dockerdo init command: otherwise, the session is loaded from a yaml file.

        Creates the session directory.
        """
        if session_name is None:
            if dry_run:
                session_dir = Path("/tmp/dockerdo_(filled in by mkdtemp)")
                prettyprint.action(
                    "local", "Would create", f"ephemeral session directory {session_dir}"
                )
                session_name = "(filled in by mkdtemp)"
            else:
                session_dir = Path(mkdtemp(prefix="dockerdo_"))
                prettyprint.action(
                    "local", "Created", f"ephemeral session directory {session_dir}"
                )
                session_name = session_dir.name.replace("dockerdo_", "")
        else:
            session_dir = Path(f"~/.local/share/dockerdo/{session_name}").expanduser()
            if session_dir.exists():
                prettyprint.warning(
                    f"Session directory {session_dir} already exists. "
                    "Either reactivate using [bold cyan]source {session_dir}/activate[/bold cyan], or delete it."
                )
                return None
        if container_name is None:
            container_name = ephemeral_container_name()
        distro = distro if distro is not None else user_config.default_distro
        base_image = base_image if base_image is not None else user_config.default_image
        if local:
            remote_host = None
        else:
            remote_host = (
                remote_host
                if remote_host is not None
                else user_config.default_remote_host
            )
        registry = (
            docker_registry
            if docker_registry is not None
            else user_config.default_docker_registry
        )
        record_inotify = record_inotify or user_config.always_record_inotify
        session = Session(
            name=session_name,
            container_name=container_name,
            remote_host=remote_host,
            distro=distro,
            base_image=base_image,
            container_username=container_username,
            docker_registry=registry,
            record_inotify=record_inotify,
            session_dir=session_dir,
            remote_host_build_dir=remote_host_build_dir,
            local_work_dir=local_work_dir,
        )
        return session

    def get_homedir(self) -> Path:
        """Get the home directory for the session"""
        if self.container_username == "root":
            return Path("/root")
        else:
            return Path(f"/home/{self.container_username}")

    def record_command(self, command: str, path: Path) -> None:
        """
        Record a command in the session history.
        The command history is appended to a file in the session directory.
        """
        history_file = self.session_dir / "command_history.jsonl"
        with open(history_file, "a") as f:
            json.dump({"cwd": str(path), "command": command}, f)
            f.write("\n")

    def record_modified_file(self, file: Path) -> None:
        """Record a file write in the session history"""
        self.modified_files.add(file)

    def _update_env(self, key: str, value: str) -> None:
        if len(value.strip()) == 0:
            if key not in self.env:
                return
            del self.env[key]
        else:
            self.env[key] = value

    def export(self, key: str, value: str) -> None:
        """Export a key-value pair to the session environment"""
        self._update_env(key, value)
        env_file = self.session_dir / "env.list"
        with open(env_file, "w") as f:
            for key, value in sorted(self.env.items()):
                f.write(f"{key}={value}\n")

    def save(self) -> None:
        """Save the session to a file in the session directory"""
        session_file = self.session_dir / "session.yaml"
        if not self.session_dir.exists():
            self.session_dir.mkdir(parents=True, exist_ok=True)
            prettyprint.action(
                "local", "Created", f"persistent session directory {self.session_dir}"
            )
        with open(session_file, "w") as f:
            f.write(self.model_dump_yaml())

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Session":
        """Load the config from yaml"""
        return cls(**yaml.safe_load(yaml_str))

    @classmethod
    def load(cls, session_dir: Path) -> "Session":
        """Load the session from a file in the session directory"""
        session_file = session_dir / "session.yaml"
        with open(session_file, "r") as f:
            return cls.from_yaml(f.read())

    @property
    def sshfs_remote_mount_point(self) -> Optional[Path]:
        """Get the path on the local host where the remote host build dir is mounted"""
        if self.remote_host is None:
            return None
        return self.local_work_dir / self.remote_host

    @property
    def sshfs_container_mount_point(self) -> Path:
        """Get the path on the local host where the container filesystem is mounted"""
        return self.local_work_dir / "container"

    def format_activate_script(self) -> str:
        """Generate the activate script"""
        result = []
        # let the user know what is happening
        result.append("set -x\n")
        result.append(f"export DOCKERDO_SESSION_DIR={self.session_dir}\n")
        result.append(f"export DOCKERDO_SESSION_NAME={self.name}\n")
        result.append("function deactivate_dockerdo { unset DOCKERDO_SESSION_DIR; unset DOCKERDO_SESSION_NAME; }\n")

        # Mount remote host build directory if using remote host
        if self.remote_host is not None:
            result.append(f"mkdir -p {self.sshfs_remote_mount_point}\n")
            result.append(
                f"sshfs {self.remote_host}:{self.remote_host_build_dir} {self.sshfs_remote_mount_point}\n"
            )
        result.append("set +x\n")
        return "".join(result)

    def write_activate_script(self) -> Path:
        """Write the activate script to a file in the session directory"""
        activate_script = self.session_dir / "activate"
        with open(activate_script, "w") as f:
            f.write(self.format_activate_script())

        activate_script.chmod(0o755)
        return activate_script

    def get_command_history(self) -> List[Dict[str, str]]:
        """Get the command history"""
        history_file = self.session_dir / "command_history.jsonl"
        if not history_file.exists():
            return []
        with open(history_file, "r") as f:
            history = []
            for line in f:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return history

    def write_container_env_file(self, verbose: bool = False) -> None:
        """Write the container env file to a file inside the container"""
        path_on_host = self.sshfs_container_mount_point / self.env_file_path.relative_to(Path('/'))
        if verbose:
            prettyprint.info(f"Writing container env file to {path_on_host}")
        with open(path_on_host, "w") as f:
            for key, value in self.env.items():
                f.write(f"export {key}={value}\n")

    @property
    def env_file_path(self) -> Path:
        """Path of the env file within the container"""
        return Path("/tmp") / f"{self.name}.env.list"
