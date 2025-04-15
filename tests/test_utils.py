"""Test the utils module"""

import pytest
import time

from dockerdo.utils import ephemeral_container_name, make_image_tag


def test_ephemeral_container_name():
    name = ephemeral_container_name()
    assert len(name) == 10 + len(str(int(time.time())))
    assert name[:10].islower()
    assert name[10:].isdigit()


@pytest.mark.parametrize(
    "registry, base_image, session_name, expected",
    [
        (None, "alpine:nightly", "test", "dockerdo-alpine:nightly-test"),
        ("harbor.local", "alpine", "foobar", "harbor.local/dockerdo-alpine:latest-foobar"),
        ("", "alpine:3.14", "test", "dockerdo-alpine:3.14-test"),
        (None, "custom/image:tag", "test-123", "dockerdo-image:tag-test-123"),
        (None, "custom/org/image:tag", "test-456", "dockerdo-image:tag-test-456"),
    ],
)
def test_make_image_tag(registry, base_image, session_name, expected):
    assert make_image_tag(registry, base_image, session_name) == expected


@pytest.mark.parametrize(
    "registry, base_image, session_name, expected",
    [
        (None, "alpine:nightly", "test", "custom:alpine-test-nightly-foo"),
        ("harbor.local", "alpine", "foobar", "harbor.local/custom:alpine-foobar-latest-foo"),
        ("", "alpine:3.14", "test", "custom:alpine-test-3.14-foo"),
        (None, "custom/image:tag", "test-123", "custom:image-test-123-tag-foo"),
        (None, "custom/org/image:tag", "test-456", "custom:image-test-456-tag-foo"),
    ],
)
def test_make_image_tag_custom_template(registry, base_image, session_name, expected):
    assert make_image_tag(
        registry,
        base_image,
        session_name,
        "custom:{base_image}-{session_name}-{base_image_tag}-foo"
    ) == expected
