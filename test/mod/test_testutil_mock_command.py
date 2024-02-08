#
# Tests for the 'osbuild.util.testutil.mock_command' module.
#
import os
import subprocess
import textwrap

from osbuild.testutil import mock_command


def test_mock_command_integration():
    output = subprocess.check_output(["echo", "hello"])
    assert output == b"hello\n"
    fake_echo = textwrap.dedent("""\
    #!/bin/sh
    echo i-am-not-echo
    """)
    with mock_command("echo", fake_echo):
        output = subprocess.check_output(["echo", "hello"])
        assert output == b"i-am-not-echo\n"
    output = subprocess.check_output(["echo", "hello"])
    assert output == b"hello\n"


def test_mock_command_environ_is_modified_and_restored():
    orig_path = os.environ["PATH"]
    with mock_command("something", "#!/bin/sh\ntrue\n"):
        assert os.environ["PATH"] != orig_path
    assert os.environ["PATH"] == orig_path
