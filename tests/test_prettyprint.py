"""Test prettyprint module"""

import pytest
import re

from dockerdo.prettyprint import format_bullet, format_action

RE_MULTISPACE = re.compile(r"\s+")


@pytest.mark.parametrize("status, expected", [
    ("RUNNING", "(/)"),
    ("OK", "(+)"),
    ("WARN", "(!)"),
    ("FAIL", "(!)"),
    ("UNKNOWN", ""),
])
def test_format_bullet(status, expected):
    """Test format_bullet function"""
    result = format_bullet(status)
    assert str(result) == expected


def test_format_action():
    """Test format_action function, ignoring the amount of whitespace"""
    result = str(format_action("aaa", "bbb", "ccc"))
    result = RE_MULTISPACE.sub(" ", result)
    assert result == "(+) [aaa] bbb ccc"
