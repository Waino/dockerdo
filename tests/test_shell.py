"""Test the shell module"""

import pytest

from dockerdo.shell import parse_docker_ps_output, determine_acceptable_container_state


@pytest.mark.parametrize("output, expected", [
    ("", None),
    ("{}", None),
    ('{"Command":"/bin/bash","CreatedAt":"2025-03-26 22:31:01 +0200 EET","ID":"97913facb416","Image":"dockerdo-ubuntu:latest-s4xogyvy","Labels":"org.opencontainers.image.version=24.04,org.opencontainers.image.ref.name=ubuntu","LocalVolumes":"0","Mounts":"","Names":"ywttewpqpl1743019901","Networks":"bridge","Ports":"0.0.0.0:2222-\u003e22/tcp, [::]:2222-\u003e22/tcp","RunningFor":"24 hours ago","Size":"0B","State":"running","Status":"Up 24 hours"}', "running"),  # noqa: E501
])
def test_parse_docker_ps_output(output, expected):
    assert parse_docker_ps_output(output) == expected


@pytest.mark.parametrize("actual_state, expected", [
    (None, "nothing"),
    ("running", "running"),
    ("exited", "stopped"),
    ("paused", "stopped"),
    ("dead", "stopped"),
    ("restarting", "stopped"),
    ("created", "stopped"),
    ("unknown", None),
])
def test_determine_acceptable_container_state(actual_state, expected):
    assert determine_acceptable_container_state(actual_state) == expected
