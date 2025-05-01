"""Test the config module"""

from unittest import mock
from pathlib import Path

from dockerdo.config import Session, UserConfig


def test_session_from_opts_defaults():
    """Test the Session.from_opts method, mocking mkdtemp"""
    user_config = UserConfig()
    with mock.patch("dockerdo.config.mkdtemp", return_value="/tmp/dockerdo_1234a67890"):
        session = Session.from_opts(
            session_name=None,
            container_name=None,
            remote_host=None,
            local=True,
            distro=None,
            base_image=None,
            container_username="root",
            docker_registry=None,
            record_inotify=False,
            remote_host_build_dir=Path("."),
            local_work_dir=Path("/obscure/workdir"),
            remote_delay=0.0,
            user_config=user_config,
        )
    assert session is not None
    assert session.name == "1234a67890"
    assert session.container_name is not None
    assert session.remote_host is None
    assert session.distro == "ubuntu"
    assert session.base_image == "ubuntu:latest"
    assert session.image_tag is None
    assert session.container_username == "root"
    assert session.docker_registry is None
    assert session.record_inotify is False
    assert session.session_dir == Path("/tmp/dockerdo_1234a67890")
    assert session.ssh_port_on_remote_host is None
    assert session.remote_host_build_dir == Path(".")
    assert session.local_work_dir == Path("/obscure/workdir")
    assert session.remote_delay == 0.0
    assert session.docker_run_args is None
    assert session.container_state == "nothing"

    assert session.get_homedir() == Path("/root")
    assert session.sshfs_remote_mount_point is None
    assert session.sshfs_container_mount_point == Path("/obscure/workdir/container")
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
    user_config = UserConfig(
        default_remote_host="reykjavik",
        default_distro="alpine",
        default_image="alpine:latest",
        default_docker_registry="docker.io",
        default_docker_run_args="--rm",
        always_record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            session_name='my_session',
            container_name='my_container',
            remote_host='reno',
            local=False,
            distro="ubuntu",
            base_image="mycustom:nightly",
            container_username="ubuntu",
            docker_registry="harbor.local",
            record_inotify=False,
            remote_host_build_dir=Path("/tmp/build"),
            local_work_dir=Path("/another/workdir"),
            remote_delay=1.0,
            user_config=user_config,
        )
    assert session is not None
    assert session.name == "my_session"
    assert session.container_name == "my_container"
    assert session.remote_host == "reno"
    assert session.distro == "ubuntu"
    assert session.base_image == "mycustom:nightly"
    assert session.image_tag is None
    assert session.container_username == "ubuntu"
    assert session.docker_registry == "harbor.local"
    assert session.record_inotify is True   # always_record_inotify overrides record_inotify
    assert session.session_dir == Path("/home/user/.local/share/dockerdo/my_session")
    assert session.ssh_port_on_remote_host is None
    assert session.remote_host_build_dir == Path("/tmp/build")
    assert session.local_work_dir == Path("/another/workdir")
    assert session.remote_delay == 1.0
    assert session.docker_run_args is None
    assert session.container_state == "nothing"

    assert session.get_homedir() == Path("/home/ubuntu")
    assert session.sshfs_remote_mount_point == Path("/another/workdir/reno")
    assert session.sshfs_container_mount_point == Path("/another/workdir/container")
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


def test_session_from_opts_override_except_user_config():
    """Test the Session.from_opts method, mocking expanduser"""
    user_config = UserConfig(
        default_remote_host="reykjavik",
        default_distro="alpine",
        default_image="alpine:latest",
        default_docker_registry="docker.io",
        default_docker_run_args="--rm",
        default_remote_delay=0.5,
        always_record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            session_name='my_session',
            container_name='my_container',
            remote_host=None,
            local=False,
            distro=None,
            base_image=None,
            container_username="alpine",
            docker_registry=None,
            record_inotify=False,
            remote_host_build_dir=Path("/tmp/build"),
            local_work_dir=Path("/another/workdir"),
            remote_delay=None,
            user_config=user_config,
        )
    assert session is not None
    assert session.name == "my_session"
    assert session.container_name == "my_container"
    assert session.remote_host == "reykjavik"
    assert session.distro == "alpine"
    assert session.base_image == "alpine:latest"
    assert session.image_tag is None
    assert session.container_username == "alpine"
    assert session.docker_registry == "docker.io"
    assert session.record_inotify is True   # always_record_inotify overrides record_inotify
    assert session.session_dir == Path("/home/user/.local/share/dockerdo/my_session")
    assert session.ssh_port_on_remote_host is None
    assert session.remote_host_build_dir == Path("/tmp/build")
    assert session.local_work_dir == Path("/another/workdir")
    assert session.remote_delay == 0.5
    assert session.docker_run_args is None
    assert session.container_state == "nothing"

    assert session.get_homedir() == Path("/home/alpine")
    assert session.sshfs_remote_mount_point == Path("/another/workdir/reykjavik")
    assert session.sshfs_container_mount_point == Path("/another/workdir/container")
    assert session.env_file_path == Path("/tmp/my_session.env.list")

    # test roundtrip
    session2 = Session.from_yaml(session.model_dump_yaml())
    assert session2 == session


def test_user_config_roundtrip():
    """Test the UserConfig.from_yaml method"""
    user_config = UserConfig()
    assert user_config == UserConfig.from_yaml(user_config.model_dump_yaml())


def test_session_env_management():
    """Test the Session._update_env method"""
    user_config = UserConfig(
        default_remote_host="reykjavik",
        default_distro="alpine",
        default_image="alpine:latest",
        default_docker_registry="docker.io",
        default_docker_run_args="--rm",
        always_record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            session_name='my_session',
            container_name='my_container',
            remote_host=None,
            local=False,
            distro=None,
            base_image=None,
            container_username="alpine",
            docker_registry=None,
            record_inotify=False,
            remote_host_build_dir=Path("/tmp/build"),
            local_work_dir=Path("/another/workdir"),
            remote_delay=0.0,
            user_config=user_config,
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
    user_config = UserConfig(
        default_remote_host="reykjavik",
        default_distro="alpine",
        default_image="alpine:latest",
        default_docker_registry="docker.io",
        default_docker_run_args="--rm",
        always_record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        with mock.patch("dockerdo.config.Path.exists", return_value=True):
            session = Session.from_opts(
                session_name='my_session',
                container_name='my_container',
                remote_host='reno',
                local=False,
                distro="ubuntu",
                base_image="mycustom:nightly",
                container_username="ubuntu",
                docker_registry="harbor.local",
                record_inotify=False,
                remote_host_build_dir=Path("/tmp/build"),
                local_work_dir=Path("/another/workdir"),
                remote_delay=0.0,
                user_config=user_config,
            )
            assert session is None


def test_session_dry_run():
    """Test the Session._update_env method"""
    user_config = UserConfig(
        default_remote_host="reykjavik",
        default_distro="alpine",
        default_image="alpine:latest",
        default_docker_registry="docker.io",
        default_docker_run_args="",
        always_record_inotify=True,
    )
    with mock.patch(
        "dockerdo.config.Path.expanduser",
        return_value=Path("/home/user/.local/share/dockerdo/my_session")
    ):
        session = Session.from_opts(
            session_name=None,
            container_name='my_container',
            remote_host=None,
            local=False,
            distro=None,
            base_image=None,
            container_username="alpine",
            docker_registry=None,
            record_inotify=False,
            remote_host_build_dir=Path("/tmp/build"),
            local_work_dir=Path("/another/workdir"),
            remote_delay=0.0,
            user_config=user_config,
            dry_run=True,
        )
        assert session is not None
        assert session.name == "(filled in by mkdtemp)"
