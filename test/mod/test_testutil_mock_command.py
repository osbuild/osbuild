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
    echo i-am-not-echo
    """)
    with mock_command("echo", fake_echo) as mocked_cmd:
        output = subprocess.check_output(["echo", "hello"])
        assert output == b"i-am-not-echo\n"
        assert mocked_cmd.call_args_list == [
            ["hello"],
        ]
    output = subprocess.check_output(["echo", "hello"])
    assert output == b"hello\n"


def test_mock_command_multi():
    with mock_command("echo", "") as mocked_cmd:
        subprocess.check_output(["echo", "call1-arg1", "call1-arg2"])
        subprocess.check_output(["echo", "call2-arg1", "call2-arg2"])
        assert mocked_cmd.call_args_list == [
            ["call1-arg1", "call1-arg2"],
            ["call2-arg1", "call2-arg2"],
        ]


def test_mock_command_environ_is_modified_and_restored():
    orig_path = os.environ["PATH"]
    with mock_command("something", "#!/bin/sh\ntrue\n"):
        assert os.environ["PATH"] != orig_path
    assert os.environ["PATH"] == orig_path
