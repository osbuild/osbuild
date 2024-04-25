#
# Tests for the 'osbuild.util.testutil.make_container'.
#
import subprocess
import textwrap

import pytest

from osbuild.testutil import has_executable, make_container, mock_command


def test_make_container_bad_podman_prints_podman_output(tmp_path, capfd):
    fake_broken_podman = textwrap.dedent("""\
    #!/bin/sh
    echo fake-broken-podman
    exit 1
    """)
    with mock_command("podman", fake_broken_podman):
        with pytest.raises(subprocess.CalledProcessError):
            with make_container(tmp_path, {}) as _:
                pass
    assert "fake-broken-podman" in capfd.readouterr().out


@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_make_container_integration(tmp_path, capfd):
    with make_container(tmp_path, {"/etc/foo": "foo-content"}) as cref:
        # names have the form "osubild-test-<random-number-of-len12>"
        assert len(cref) == len("osbuild-test-123456789012")
    assert "COMMIT" in capfd.readouterr().out
