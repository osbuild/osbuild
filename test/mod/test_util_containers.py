#
# Test for util/containers.py
#

import textwrap
from unittest.mock import patch

import pytest

import osbuild.testutil
from osbuild.util import containers


def test_container_mount_error():
    fake_podman = textwrap.dedent("""\
    #!/bin/sh
    echo "some msg on stdout"
    echo "other error on stderr" >&2
    exit 1
    """)
    input_image = {
        "filepath": "path",
        "manifest-list": "manifest-list-path",
        "data": {'name': 'foo', 'format': 'containers-storage'},
        "checksum": "sha256:abcdabcd"
    }

    with patch("osbuild.util.containers.container_source") as mock_cs:
        # the context manager for container_source needs to return our mock_source
        mock_cs.return_value.__enter__.return_value = ("some-image-name", "some-image-source")
        with osbuild.testutil.mock_command("podman", fake_podman):
            with pytest.raises(RuntimeError) as exp:
                with containers.container_mount(input_image):
                    pass
        mock_cs.assert_called_once_with(input_image)
    assert "some msg on stdout" not in str(exp.value)
    assert "other error on stderr" in str(exp.value)
