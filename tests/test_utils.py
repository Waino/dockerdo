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
    ],
)
def test_make_image_tag(registry, base_image, session_name, expected):
    assert make_image_tag(registry, base_image, session_name) == expected
