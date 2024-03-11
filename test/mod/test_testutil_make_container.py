#
# Tests for the 'osbuild.util.testutil.make_container'.
#
import subprocess
import textwrap

import pytest

from osbuild.testutil import has_executable, make_container, mock_command


def test_make_container_bad_podman_prints_podman_output(tmp_path, capsys):
    fake_broken_podman = textwrap.dedent("""\
    #!/bin/sh
    echo fake-broken-podman
    exit 1
    """)
    with mock_command("podman", fake_broken_podman):
        with pytest.raises(subprocess.CalledProcessError):
            with make_container(tmp_path, {}) as _:
                pass
    assert "fake-broken-podman" in capsys.readouterr().out


@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_make_container_integration(tmp_path, capsys):
    with make_container(tmp_path, {"/etc/foo": "foo-content"}) as cref:
        assert len(cref) == 64
    assert "COMMIT" in capsys.readouterr().out
