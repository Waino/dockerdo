"""Test the config module"""

from unittest import mock
from pathlib import Path

from dockerdo.config import Session, Preset, MountSpecs


def test_session_from_opts_defaults():
    """Test the Session.from_opts method, mocking mkdtemp"""
    preset = Preset()
    with mock.patch("dockerdo.config.mkdtemp", return_value="/tmp/dockerdo_1234a67890"):
        session = Session.from_opts(
            always_interactive=False,
            base_image=None,
            container_name=None,
            container_username="root",
            distro=None,
            docker_registry_host=None,
            docker_registry_port=None,
            docker_namespace=None,
            local=True,
            local_work_dir=Path("/obscure/workdir"),
            record_inotify=False,
            startup_retries=None,
            remote_delay=None,
            remote_host=None,
            remote_host_build_dir=Path("."),
            session_name=None,
            ssh_key_path=Path("/use/this/key"),
            preset=preset,
        )
    assert session is not None
    assert session.always_interactive is False
    assert session.base_image == "ubuntu:latest"
    assert session.container_name is not None
    assert session.container_username == "root"
    assert session.distro == "ubuntu"
    assert session.docker_registry_host is None
    assert session.docker_registry_port is None
    assert session.docker_namespace is None
    assert session.docker_run_args is None
    assert session.image_reference is None
    assert session.local_work_dir == Path("/obscure/workdir")
    assert session.name == "1234a67890"
    assert session.record_inotify is False
    assert session.startup_retries == 10
    # remote delay is always zero for local
    assert session.remote_delay == 0.0
    assert session.remote_host is None
    assert session.remote_host_build_dir == Path(".")
    assert session.session_dir == Path("/tmp/dockerdo_1234a67890")
    assert session.ssh_port_on_remote_host is None
    assert session.container_state == "nothing"

    assert session.get_homedir() == Path("/root")
    assert session.sshfs_remote_mount_point is None
    assert session.mounts == []
    assert session.env_file_path == Path("/tmp/1234a67890.env.list")
    assert session.format_activate_script() == """
set -x
export DOCKERDO_SESSION_DIR=/tmp/dockerdo_1234a67890
export DOCKERDO_SESSION_NAME=1234a67890
function deactivate_dockerdo { unset DOCKERDO_SESSION_DIR; unset DOCKERDO_SESSION_NAME; }
set +x
""".lstrip()

    # test roundtrip
    session2 = Session.from_yaml(session.model_dump_yaml())
    assert session2 == session


def test_session_from_opts_override_all():
    """Test the Session.from_opts method, mocking expanduser"""
    preset = Preset(
        always_interactive=False,
        remote_host="reykjavik",
        distro="alpine",
        base_image="alpine:latest",
        docker_registry_host="docker.io",
        docker_registry_port=443,
        docker_namespace="myorg",
        docker_run_args="--rm",
        record_inotify=True,
        ssh_key_path=Path("/preset/key"),
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            always_interactive=True,
            base_image="mycustom:nightly",
            container_name='my_container',
            container_username="ubuntu",
            distro="ubuntu",
            docker_registry_host="harbor.local",
            docker_registry_port=5000,
            docker_namespace="myorg",
            local=False,
            local_work_dir=Path("/another/workdir"),
            record_inotify=False,
            startup_retries=5,
            remote_delay=1.0,
            remote_host='reno',
            remote_host_build_dir=Path("/tmp/build"),
            session_name='my_session',
            ssh_key_path=Path("/use/this/key"),
            preset=preset,
        )
    assert session is not None
    assert session.always_interactive is True
    assert session.base_image == "mycustom:nightly"
    assert session.container_name == "my_container"
    assert session.container_username == "ubuntu"
    assert session.distro == "ubuntu"
    assert session.docker_registry_host == "harbor.local"
    assert session.docker_registry_port == 5000
    assert session.docker_namespace == "myorg"
    assert session.image_reference is None
    assert session.local_work_dir == Path("/another/workdir")
    assert session.name == "my_session"
    assert session.record_inotify is True   # always_record_inotify overrides record_inotify
    assert session.startup_retries == 5
    assert session.remote_delay == 1.0
    assert session.remote_host == "reno"
    assert session.remote_host_build_dir == Path("/tmp/build")
    assert session.session_dir == Path("/home/user/.local/share/dockerdo/my_session")
    assert session.ssh_key_path == Path("/use/this/key")
    assert session.ssh_port_on_remote_host is None
    assert session.container_state == "nothing"

    # Not overrideable at session init
    assert session.docker_run_args == "--rm"

    assert session.get_homedir() == Path("/home/ubuntu")
    assert session.sshfs_remote_mount_point == Path("/another/workdir/reno")
    assert session.mounts == []
    assert session.env_file_path == Path("/tmp/my_session.env.list")

    assert session.format_activate_script() == """
set -x
export DOCKERDO_SESSION_DIR=/home/user/.local/share/dockerdo/my_session
export DOCKERDO_SESSION_NAME=my_session
function deactivate_dockerdo { unset DOCKERDO_SESSION_DIR; unset DOCKERDO_SESSION_NAME; fusermount -u /another/workdir/reno; }
if [ ! -e /home/user/.local/share/dockerdo/my_session/ssh-socket-remote ]; then
  ssh -M -N -S /home/user/.local/share/dockerdo/my_session/ssh-socket-remote reno &
fi
if ( ! mountpoint -q /another/workdir/reno ); then
  ssh -S /home/user/.local/share/dockerdo/my_session/ssh-socket-remote reno mkdir -p /tmp/build
  mkdir -p /another/workdir/reno
  sshfs reno:/tmp/build /another/workdir/reno
fi
set +x
""".lstrip()

    # test roundtrip
    session2 = Session.from_yaml(session.model_dump_yaml())
    assert session2 == session


def test_session_from_opts_override_some():
    """Test the Session.from_opts method, mocking expanduser"""
    preset = Preset(
        remote_host="reykjavik",
        distro="alpine",
        base_image="alpine:latest",
        docker_registry_host="docker.io",
        docker_registry_port=443,
        docker_namespace="myorg",
        docker_run_args="--rm",
        image_name_template="my-custom-template",
        startup_retries=5,
        remote_delay=0.5,
        record_inotify=True,
        mounts=[
            MountSpecs(
                near_host="local",
                near_path=Path("/tmp/whatever"),
                far_host="container",
                far_path=Path("/deep/inside"),
                mount_type="sshfs"
            )
        ],
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            always_interactive=False,
            base_image=None,
            container_name='my_container',
            container_username="alpine",
            distro=None,
            docker_registry_host=None,
            docker_registry_port=None,
            docker_namespace="different_namespace",
            local=False,
            local_work_dir=Path("/another/workdir"),
            record_inotify=False,
            startup_retries=None,
            remote_delay=None,
            remote_host=None,
            remote_host_build_dir=Path("/tmp/build"),
            session_name='my_session',
            ssh_key_path=Path("/use/this/key"),
            preset=preset,
        )
    assert session is not None
    assert session.always_interactive is False
    assert session.base_image == "alpine:latest"
    assert session.container_name == "my_container"
    assert session.container_username == "alpine"
    assert session.distro == "alpine"
    assert session.docker_registry_host == "docker.io"
    assert session.docker_registry_port == 443
    assert session.docker_namespace == "different_namespace"
    assert session.image_reference is None
    assert session.local_work_dir == Path("/another/workdir")
    assert session.name == "my_session"
    assert session.record_inotify is True   # preset record_inotify
    assert session.startup_retries == 5
    assert session.remote_delay == 0.5
    assert session.remote_host == "reykjavik"
    assert session.remote_host_build_dir == Path("/tmp/build")
    assert session.session_dir == Path("/home/user/.local/share/dockerdo/my_session")
    assert session.ssh_key_path == Path("/use/this/key")
    assert session.ssh_port_on_remote_host is None
    assert session.container_state == "nothing"

    # Not overrideable at session init
    assert session.docker_run_args == "--rm"

    assert session.get_homedir() == Path("/home/alpine")
    assert session.sshfs_remote_mount_point == Path("/another/workdir/reykjavik")
    assert session.mounts == [
        MountSpecs(
            near_host="local",
            near_path=Path("/tmp/whatever"),
            far_host="container",
            far_path=Path("/deep/inside"),
            mount_type="sshfs"
        )
    ]
    assert session.env_file_path == Path("/tmp/my_session.env.list")

    # test roundtrip
    session2 = Session.from_yaml(session.model_dump_yaml())
    assert session2 == session


def test_preset_roundtrip():
    """Test the Preset.from_yaml method"""
    preset = Preset()
    assert preset == Preset.from_yaml(preset.model_dump_yaml())


def test_session_env_management():
    """Test the Session._update_env method"""
    preset = Preset(
        remote_host="reykjavik",
        distro="alpine",
        base_image="alpine:latest",
        docker_registry_host="docker.io",
        docker_registry_port=443,
        docker_namespace="myorg",
        docker_run_args="--rm",
        record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            always_interactive=False,
            base_image=None,
            container_name='my_container',
            container_username="alpine",
            distro=None,
            docker_registry_host=None,
            docker_registry_port=None,
            docker_namespace=None,
            local=False,
            local_work_dir=Path("/another/workdir"),
            record_inotify=False,
            startup_retries=None,
            remote_delay=0.0,
            remote_host=None,
            remote_host_build_dir=Path("/tmp/build"),
            session_name='my_session',
            ssh_key_path=Path("/use/this/key"),
            preset=preset,
        )

    assert len(session.env) == 0
    session._update_env("UNCHANGED", "unchanged")
    session._update_env("FOO", "bar")
    assert session.env == {"FOO": "bar", "UNCHANGED": "unchanged"}
    # update
    session._update_env("FOO", "baz")
    assert session.env == {"FOO": "baz", "UNCHANGED": "unchanged"}
    # unset
    session._update_env("FOO", "")
    assert session.env == {"UNCHANGED": "unchanged"}
    # unset nonexistent
    session._update_env("NONEXISTENT", "")
    assert session.env == {"UNCHANGED": "unchanged"}


def test_session_from_opts_persistent_already_exists():
    """Test the Session.from_opts method, mocking expanduser and exists"""
    preset = Preset(
        remote_host="reykjavik",
        distro="alpine",
        base_image="alpine:latest",
        docker_registry_host="docker.io",
        docker_registry_port=443,
        docker_namespace="myorg",
        docker_run_args="--rm",
        record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        with mock.patch("dockerdo.config.Path.exists", return_value=True):
            session = Session.from_opts(
                always_interactive=False,
                base_image="mycustom:nightly",
                container_name='my_container',
                container_username="ubuntu",
                distro="ubuntu",
                docker_registry_host="harbor.local",
                docker_registry_port=5000,
                docker_namespace="different_namespace",
                local=False,
                local_work_dir=Path("/another/workdir"),
                record_inotify=False,
                startup_retries=5,
                remote_delay=0.0,
                remote_host='reno',
                remote_host_build_dir=Path("/tmp/build"),
                session_name='my_session',
                ssh_key_path=Path("/use/this/key"),
                preset=preset,
            )
            assert session is None


def test_session_dry_run():
    """Test the Session._update_env method"""
    preset = Preset(
        remote_host="reykjavik",
        distro="alpine",
        base_image="alpine:latest",
        docker_registry_host="docker.io",
        docker_registry_port=443,
        docker_namespace="myorg",
        docker_run_args="",
        record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            always_interactive=False,
            base_image=None,
            container_name='my_container',
            container_username="alpine",
            distro=None,
            docker_registry_host=None,
            docker_registry_port=None,
            docker_namespace=None,
            local=False,
            local_work_dir=Path("/another/workdir"),
            record_inotify=False,
            startup_retries=None,
            remote_delay=0.0,
            remote_host=None,
            remote_host_build_dir=Path("/tmp/build"),
            session_name=None,
            ssh_key_path=Path("/use/this/key"),
            preset=preset,
            dry_run=True,
        )
        assert session is not None
        assert session.name == "(filled in by mkdtemp)"
