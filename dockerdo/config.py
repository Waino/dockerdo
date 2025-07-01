"""User configuration and session data"""

import yaml
import json
import time
import re
import os
import hashlib
from pathlib import Path
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, ConfigDict, field_validator, model_validator
from tempfile import mkdtemp
from types import SimpleNamespace
from typing import Optional, Literal, Dict, List, Any

from dockerdo.utils import ephemeral_container_name
from dockerdo import prettyprint


ARROWS = {
    "sshfs": "<-",
    "mutagen": "<=>",
    "docker": "->>",
}
ENV_VAR_REF = re.compile(r"\{host_env\.(\w+)\}")
MUTAGEN_FORBIDDEN_ID_CHARS = re.compile(r"[^a-zA-Z0-9-]")


class BaseModel(PydanticBaseModel):
    """Extend Pydantic BaseModel with common functionality"""

    model_config = ConfigDict(extra='ignore')

    def model_dump_yaml(self, exclude: Optional[set[str]] | Dict[str, Any] = None) -> str:
        """Dump the model as yaml"""
        return yaml.dump(self.model_dump(mode="json", exclude=exclude), sort_keys=True)


class MountSpecs(BaseModel):
    near_host: Literal["local", "remote"] = "local"
    near_path: Path
    far_host: Literal["remote", "container"] = "container"
    far_path: Path
    mount_type: Literal["sshfs", "mutagen", "docker"]

    @model_validator(mode='after')
    def check_hosts(self) -> "MountSpecs":
        if self.mount_type == "docker":
            if self.near_host != "remote" or self.far_host != "container":
                raise ValueError("docker mount can only be from remote to container")
        if self.near_host == "remote" and self.far_host == "remote":
            raise ValueError("can't mount from remote to remote")
        # TODO: implement sshfs and mutagen remote <-> container mounts
        if self.near_host == "remote" and self.mount_type != "docker":
            raise ValueError("currently only docker type remote -> container mount supported")
        return self

    def descr_str(self) -> str:
        arrow = ARROWS.get(self.mount_type, '--')
        return f"{self.near_host}:{self.near_path} {arrow} {self.far_host}:{self.far_path}"

    def get_far_host_name(self, session: "Session", suffix: str = "") -> str:
        if self.far_host == "container":
            return session.container_host_alias + suffix
        elif self.far_host == "remote" and session.remote_host is not None:
            return session.remote_host
        else:
            return "localhost"

    def get_mutagen_id(self, session: "Session") -> Optional[str]:
        """
        The id is deterministic, and available even if the mount is not yet created.
        mutagen_id is None if not a mutagen mount.
        """
        if self.mount_type != "mutagen":
            return None
        path_hash = hashlib.md5(
            f"{self.near_path}_{self.far_path}".encode(),
            usedforsecurity=False,
        ).hexdigest()
        id = f"dockerdo-{session.name}-{self.near_host}-{self.far_host}-{path_hash}"
        id = MUTAGEN_FORBIDDEN_ID_CHARS.sub("-", id)
        return id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MountSpecs):
            return False
        return (
            self.near_host == other.near_host
            and self.near_path == other.near_path
            and self.far_host == other.far_host
            and self.far_path == other.far_path
            and self.mount_type == other.mount_type
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.near_host,
                self.near_path,
                self.far_host,
                self.far_path,
                self.mount_type,
            )
        )


class PortForwardSpecs(BaseModel):
    local_port: int
    container_port: int

    def descr_str(self) -> str:
        arrow = '--o'
        return f"localhost:{self.local_port} {arrow} container:{self.container_port}"

    def get_mutagen_id(self, session: "Session") -> str:
        """
        The id is deterministic, and available even if the forwarding is not yet created.
        """
        id = f"dockerdo-{session.name}-{self.local_port}-{self.container_port}"
        id = MUTAGEN_FORBIDDEN_ID_CHARS.sub("-", id)
        return id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PortForwardSpecs):
            return False
        return (
            self.container_port == other.container_port
            and self.local_port == other.local_port
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.container_port,
                self.local_port,
            )
        )


class Preset(BaseModel):
    """User configuration presets for dockerdo"""
    description: str = ""
    always_interactive: bool = False
    container_username: str = "root"
    distro: str = "ubuntu"
    docker_registry_host: Optional[str] = None
    docker_registry_port: Optional[int] = None
    docker_namespace: Optional[str] = None
    docker_run_args: Optional[str] = None
    base_image: str = "ubuntu:latest"
    image_name_template: str = "dockerdo-{base_image_repository}:{base_image_tag}-{session_name}"
    record_inotify: bool = False
    startup_retries: int = 10
    remote_delay: float = 0.3
    remote_host: Optional[str] = None
    remote_host_build_dir: Path = Path(".")
    ssh_key_path: Path = Path("~/.ssh/id_rsa.pub").expanduser()
    mounts: List[MountSpecs] = Field(default_factory=list)
    port_forwards: List[PortForwardSpecs] = Field(default_factory=list)

    @classmethod
    def load_presets(cls, yaml_str: str) -> Dict[str, "Preset"]:
        """Load the presets from yaml"""

        # Initial parse does not validate the presets
        class InitialParse(BaseModel):
            default: Preset
            presets: Any

        config_dict = yaml.safe_load(yaml_str)
        initial = InitialParse(**config_dict)

        # Reparse config, with defaults from initial parse
        class UserConfig(BaseModel):
            default: Preset
            presets: Dict[str, Preset]

            @field_validator('presets', mode='before')
            @classmethod
            def set_defaults(cls, data: Dict[str, Any]) -> Dict[str, Any]:
                if '_default' in data:
                    raise ValueError('Reserved preset name "_default"')
                data['_default'] = {'description': 'Default when no preset is given'}
                for preset_name, values in data.items():
                    for field in Preset.model_fields.keys():
                        if field not in values:
                            values[field] = initial.default.__getattribute__(field)
                return data

        config = UserConfig(**config_dict)
        return config.presets

    @classmethod
    def initial_config(cls) -> "BaseModel":
        class UserConfig(BaseModel):
            default: Preset
            presets: Dict[str, Any]

        # A preset for dockerfile development, included by default
        # Shows how to mount the full container filesystem into a local directory
        dockerfile_preset = Preset(
            description="Dockerfile development",
            record_inotify=True,
            mounts=[
                MountSpecs(
                    near_host="local",
                    near_path=Path("./container"),
                    far_host="container",
                    far_path=Path("/"),
                    mount_type="sshfs",
                )
            ],
        )
        return UserConfig(default=cls(), presets={'dockerfile': dockerfile_preset})

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Preset":
        """Load the config from yaml"""
        return cls(**yaml.safe_load(yaml_str))


class Session(BaseModel):
    """A dockerdo session"""

    # Defaults from preset, override on creation
    always_interactive: bool
    base_image: str
    container_username: str
    distro: str
    docker_registry_host: Optional[str]
    docker_registry_port: Optional[int]
    docker_namespace: Optional[str]
    record_inotify: bool
    startup_retries: int
    remote_delay: float
    remote_host: Optional[str]
    # remote_host_build_dir is made absolute when the container is run
    remote_host_build_dir: Path
    ssh_key_path: Path

    # Default from preset, override on run
    docker_run_args: Optional[str]
    image_name_template: str

    # Other fields
    container_name: str
    env: Dict[str, str] = Field(default_factory=dict)
    image_reference: Optional[str] = None
    local_work_dir: Path
    name: str
    session_dir: Path
    ssh_port_on_remote_host: Optional[int] = None

    container_state: Literal["nothing", "running", "stopped"] = "nothing"
    host_key_lines: List[str] = []
    mounts: List[MountSpecs] = Field(default_factory=list)
    port_forwards: List[PortForwardSpecs] = Field(default_factory=list)

    @classmethod
    def from_opts(
        cls,
        always_interactive: bool,
        base_image: Optional[str],
        container_name: Optional[str],
        container_username: Optional[str],
        distro: Optional[str],
        docker_registry_host: Optional[str],
        docker_registry_port: Optional[int],
        docker_namespace: Optional[str],
        local: bool,
        local_work_dir: Path,
        preset: Preset,
        record_inotify: bool,
        startup_retries: Optional[int],
        remote_delay: Optional[float],
        remote_host: Optional[str],
        remote_host_build_dir: Optional[Path],
        session_name: Optional[str],
        ssh_key_path: Optional[Path],
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
        always_interactive = always_interactive or preset.always_interactive
        base_image = base_image if base_image is not None else preset.base_image
        container_username = container_username if container_username is not None else preset.container_username
        distro = distro if distro is not None else preset.distro
        ssh_key_path = ssh_key_path if ssh_key_path is not None else preset.ssh_key_path
        remote_host_build_dir = (
            remote_host_build_dir if remote_host_build_dir is not None else preset.remote_host_build_dir
        )
        startup_retries = (
            startup_retries if startup_retries is not None else preset.startup_retries
        )
        if local:
            remote_host = None
            remote_delay = 0.0
        else:
            remote_host = (
                remote_host
                if remote_host is not None
                else preset.remote_host
            )
            remote_delay = (
                remote_delay
                if remote_delay is not None
                else preset.remote_delay
            )
        registry_host = (
            docker_registry_host
            if docker_registry_host is not None
            else preset.docker_registry_host
        )
        registry_port = (
            docker_registry_port
            if docker_registry_port is not None
            else preset.docker_registry_port
        )
        registry_namespace = (
            docker_namespace
            if docker_namespace is not None
            else preset.docker_namespace
        )
        record_inotify = record_inotify or preset.record_inotify
        session = Session(
            always_interactive=always_interactive,
            base_image=base_image,
            container_name=container_name,
            container_username=container_username,
            distro=distro,
            docker_registry_host=registry_host,
            docker_registry_port=registry_port,
            docker_namespace=registry_namespace,
            docker_run_args=preset.docker_run_args,
            image_name_template=preset.image_name_template,
            local_work_dir=local_work_dir,
            name=session_name,
            record_inotify=record_inotify,
            startup_retries=startup_retries,
            remote_delay=remote_delay,
            remote_host=remote_host,
            remote_host_build_dir=remote_host_build_dir,
            session_dir=session_dir,
            ssh_key_path=ssh_key_path,
            mounts=preset.mounts,
            port_forwards=preset.port_forwards,
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

    def record_modified_file(self, file: Path) -> bool:
        """Record a file write in the session history"""
        if file == self.env_file_path:
            return False
        modified_files_path = self.session_dir / "modified_files"
        if modified_files_path.exists():
            with open(modified_files_path, "r") as f:
                modified_files = {Path(line.strip()) for line in f}
        else:
            modified_files = set()
        if file in modified_files:
            return False
        with open(modified_files_path, "a") as fout:
            fout.write(f"{file}\n")
        return True

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
        retries = 3
        while retries > 0:
            with open(session_file, "r") as f:
                contents = f.read()
                if len(contents) == 0:
                    if retries == 0:
                        raise Exception(f"Empty session file {session_file}")
                    else:
                        time.sleep(0.2)
                        retries -= 1
                        continue
                return cls.from_yaml(contents)
        raise Exception(f"Failed to load session from {session_file}")

    @property
    def sshfs_remote_mount_point(self) -> Optional[Path]:
        """Get the path on the local host where the remote host build dir is mounted"""
        if self.remote_host is None:
            return None
        return self.local_work_dir / self.remote_host

    def format_activate_script(self) -> str:
        """Generate the activate script"""
        result = []
        # let the user know what is happening
        result.append("set -x\n")
        result.append(f"export DOCKERDO_SESSION_DIR={self.session_dir}\n")
        result.append(f"export DOCKERDO_SESSION_NAME={self.name}\n")

        if self.remote_host is not None:
            unmount = f"fusermount -u {self.sshfs_remote_mount_point}; "
        else:
            unmount = ""
        result.append(
            "function deactivate_dockerdo { unset DOCKERDO_SESSION_DIR; unset DOCKERDO_SESSION_NAME; " + unmount + "}\n"
        )

        if self.remote_host is not None:
            # Create a socket for ssh master connection to the remote host (unless it already exists)
            result.append(f"if [ ! -e {self.session_dir}/ssh-socket-remote ]; then\n")
            result.append(f"  ssh -M -N -S {self.session_dir}/ssh-socket-remote {self.remote_host} &\n")
            result.append("fi\n")

            # Unless the remote host build directory is already mounted
            result.append(f"if ( ! mountpoint -q {self.sshfs_remote_mount_point} ); then\n")
            # Ensure that the build directory exists on the remote host
            result.append(
                f"  ssh -S {self.session_dir}/ssh-socket-remote {self.remote_host}"
                f" mkdir -p {self.remote_host_build_dir}\n"
            )
            # Mount remote host build directory
            result.append(f"  mkdir -p {self.sshfs_remote_mount_point}\n")
            result.append(
                f"  sshfs {self.remote_host}:{self.remote_host_build_dir} {self.sshfs_remote_mount_point}\n"
            )
            result.append("fi\n")

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

    def get_modified_files(self) -> List[Path]:
        """Get the list of modified files"""
        modified_files_path = self.session_dir / "modified_files"
        if not modified_files_path.exists():
            return []
        with open(modified_files_path, "r") as f:
            modified_files = {Path(line.strip()) for line in f}
        return list(sorted(modified_files))

    def write_env_file(self, path: Optional[Path]) -> None:
        """Write the container env file"""
        # Write the env file in a temporary file on the host, then copy it to the container
        path = path if path else self.session_dir / "env.list"
        with open(path, "w") as f:
            for key, value in self.env.items():
                f.write(f"{key}={value}\n")

    @property
    def env_file_path(self) -> Path:
        """Path of the env file within the container"""
        return Path("/tmp") / f"{self.name}.env.list"

    @property
    def container_host_alias(self) -> str:
        return f'dockerdo_{self.name}'

    def add_mount(self, mount_specs: MountSpecs) -> None:
        # Prevent duplicate mounts
        if any(mount_specs == m for m in self.mounts):
            return
        self.mounts.append(mount_specs)
        self.save()

    def add_port_forward(self, port_forward_specs: PortForwardSpecs) -> None:
        # Prevent duplicate port forwards
        if any(port_forward_specs == p for p in self.port_forwards):
            return
        self.port_forwards.append(port_forward_specs)
        self.save()

    def _format_mount_path(self, path: Path) -> Path:
        """
        Format a path template with session and environment variables
        Session variables are accessed as {session.var_name}
        Host environment variables are accessed as {host_env.var_name}
        Container environment variables are accessed as {container_env.var_name}
        """

        path_str = str(path)
        # find all env var references "{host_env.var_name}" in the path template
        env_var_refs = ENV_VAR_REF.findall(path_str)
        env_vars = {var_name: os.environ.get(var_name, None) for var_name in env_var_refs}
        unset_env_vars = [var_name for var_name, value in env_vars.items() if value is None]
        if unset_env_vars:
            raise Exception(f"Environment variables {unset_env_vars} used in path template are not set")
        return Path(
            path_str.format(
                session=self,
                host_env=SimpleNamespace(**env_vars),
                container_env=SimpleNamespace(**self.env),
            )
        )

    def format_mount_paths(self) -> None:
        for mount_specs in self.mounts:
            mount_specs.near_path = self._format_mount_path(mount_specs.near_path)
            mount_specs.far_path = self._format_mount_path(mount_specs.far_path)
