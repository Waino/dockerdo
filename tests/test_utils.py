"""Test the utils module"""

import pytest
import time

from dockerdo.utils import ephemeral_container_name, make_image_reference


def test_ephemeral_container_name():
    name = ephemeral_container_name()
    assert len(name) == 10 + len(str(int(time.time())))
    assert name[:10].islower()
    assert name[10:].isdigit()


@pytest.mark.parametrize(
    "registry_host, registry_port, namespace, base_image, session_name, expected",
    [
        (None, None, None, "alpine:nightly", "test", "dockerdo-alpine:nightly-test"),
        ("docker.io", None, None, "alpine:nightly", "test", "docker.io/dockerdo-alpine:nightly-test"),
        ("harbor.local", 5000, None, "alpine", "foobar", "harbor.local:5000/dockerdo-alpine:latest-foobar"),
        ("docker.io", None, "myorg", "alpine", "foobar", "docker.io/myorg/dockerdo-alpine:latest-foobar"),
        ("", None, None, "alpine:3.14", "test", "dockerdo-alpine:3.14-test"),
        (None, None, None, "custom/image:tag", "test-123", "dockerdo-image:tag-test-123"),
        (None, None, None, "custom/org/image:tag", "test-456", "dockerdo-image:tag-test-456"),
        (None, None, "myorg", "custom/org/image:tag", "test-456", "myorg/dockerdo-image:tag-test-456"),
    ],
)
def test_make_image_reference(registry_host, registry_port, namespace, base_image, session_name, expected):
    result = make_image_reference(registry_host, registry_port, namespace, base_image, session_name)
    assert result == expected


@pytest.mark.parametrize(
    "registry_host, registry_port, namespace, base_image, session_name, expected",
    [
        (None, None, None, "alpine:nightly", "test", "custom:alpine-test-nightly-foo"),
        ("docker.io", None, None, "alpine:nightly", "test", "docker.io/custom:alpine-test-nightly-foo"),
        ("harbor.local", 5000, None, "alpine", "foobar", "harbor.local:5000/custom:alpine-foobar-latest-foo"),
        ("docker.io", None, "myorg", "alpine", "foobar", "docker.io/myorg/custom:alpine-foobar-latest-foo"),
        ("", None, None, "alpine:3.14", "test", "custom:alpine-test-3.14-foo"),
        (None, None, None, "custom/image:tag", "test-123", "custom:image-test-123-tag-foo"),
        (None, None, None, "custom/org/image:tag", "test-456", "custom:image-test-456-tag-foo"),
        (None, None, "myorg", "custom/org/image:tag", "test-456", "myorg/custom:image-test-456-tag-foo"),
    ],
)
def test_make_image_reference_custom_template(
    registry_host,
    registry_port,
    namespace,
    base_image,
    session_name,
    expected
):
    result = make_image_reference(
        registry_host,
        registry_port,
        namespace,
        base_image,
        session_name,
        "custom:{base_image_repository}-{session_name}-{base_image_tag}-foo"
    )
    assert result == expected
