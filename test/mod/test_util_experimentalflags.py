#
# Test for the util.experimentalflags
#
import pytest

from osbuild.util import experimentalflags


@pytest.mark.parametrize("env,expected_foo", [
    # implicit false
    ("", False),
    ("bar", False),
    # explicit true
    ("foo", True),
    ("foo,bar", True),
    ("foo=1", True),
    ("foo=1,bar", True),
    ("foo=true", True),
    ("foo=t", True),
    # explicit falgs
    ("foo=false", False),
    ("foo=0", False),
    ("foo=f", False),
    ("foo=F", False),
    ("foo=FALSE", False),
])
def test_experimentalflags_bool(monkeypatch, env, expected_foo):
    monkeypatch.setenv("OSBUILD_EXPERIMENTAL", env)
    assert experimentalflags.get_bool("foo") == expected_foo


@pytest.mark.parametrize("env,expected_key", [
    ("", ""),
    ("key=val", "val"),
    ("foo,key=val,bar", "val"),
])
def test_experimentalflags_string(monkeypatch, env, expected_key):
    monkeypatch.setenv("OSBUILD_EXPERIMENTAL", env)
    assert experimentalflags.get_string("key") == expected_key
