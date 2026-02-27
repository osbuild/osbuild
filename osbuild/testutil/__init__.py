"""
Test related utilities
"""
import contextlib
import inspect
import os
import pathlib
import random
import re
import shutil
import socket
import string
import subprocess
import tempfile
import textwrap
from types import ModuleType
from typing import Type


def has_executable(executable: str) -> bool:
    return shutil.which(executable) is not None


def assert_dict_has(v, keys, expected_value):
    for key in keys.split("."):
        assert key in v
        v = v[key]
    assert v == expected_value


def make_fake_tree(basedir: pathlib.Path, fake_content: dict):
    """Create a directory tree of files with content.

    Call it with:
        {"filename": "content", "otherfile": "content"}

    filename paths will have their parents created as needed, under tmpdir.
    """
    for path, content in fake_content.items():
        dirp, name = os.path.split(os.path.join(basedir, path.lstrip("/")))
        os.makedirs(dirp, exist_ok=True)
        with open(os.path.join(dirp, name), "w", encoding="utf-8") as fp:
            fp.write(content)


def make_fake_input_tree(tmpdir: pathlib.Path, fake_content: dict, name: str = "tree") -> str:
    """
    Wrapper around make_fake_tree for "input trees"
    """
    basedir = tmpdir / name
    make_fake_tree(basedir, fake_content)
    return os.fspath(basedir)


def assert_jsonschema_error_contains(res, expected_err, expected_num_errs=None):
    err_msgs = [e.as_dict()["message"] for e in res.errors]
    if expected_num_errs is not None:
        assert len(err_msgs) == expected_num_errs, \
            f"expected exactly {expected_num_errs} errors in {[e.as_dict() for e in res.errors]}"
    re_typ = getattr(re, 'Pattern', None)
    # this can be removed once we no longer support py3.6 (re.Pattern is modern)
    if not re_typ:
        re_typ = getattr(re, '_pattern_type')
    if isinstance(expected_err, re_typ):
        finder = expected_err.search
    else:
        def finder(s): return expected_err in s  # pylint: disable=C0321
    assert any(finder(err_msg)
               for err_msg in err_msgs), f"{expected_err} not found in {err_msgs}"


class MockCommandCallArgs:
    """MockCommandCallArgs provides the arguments a mocked command
    was called with.

    Use :call_args_list: to get a list of calls and each of these calls
    will have the argv[1:] from the mocked binary.
    """

    def __init__(self, calllog_path):
        self._calllog = pathlib.Path(calllog_path)

    @property
    def call_args_list(self):
        call_arg_list = []
        for acall in self._calllog.read_text(encoding="utf8").split("\n\n"):
            if acall:
                call_arg_list.append(acall.split("\n"))
        return call_arg_list


@contextlib.contextmanager
def mock_command(cmd_name: str, script: str):
    """
    mock_command creates a mocked binary with the given :cmd_name: and :script:
    content. This is useful to e.g. mock errors from binaries or validate that
    external binaries are called in the right way.

    It returns a MockCommandCallArgs class that can be used to inspect the
    way the binary was called.
    """
    original_path = os.environ["PATH"]
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd_path = pathlib.Path(tmpdir) / cmd_name
        cmd_calllog_path = pathlib.Path(os.fspath(cmd_path) + ".calllog")
        # This is a little bit naive right now, if args contains \n things
        # will break. easy enough to fix by using \0 as the separator but
        # then \n in args is kinda rare
        fake_cmd_content = textwrap.dedent(f"""\
        #!/bin/bash -e

        for arg in "$@"; do
           echo "$arg" >> {cmd_calllog_path}
        done
        # extra separator to differenciate between calls
        echo "" >> {cmd_calllog_path}

        """) + script
        cmd_path.write_text(fake_cmd_content, encoding="utf8")
        cmd_path.chmod(0o755)
        os.environ["PATH"] = f"{tmpdir}:{original_path}"
        try:
            yield MockCommandCallArgs(cmd_calllog_path)
        finally:
            os.environ["PATH"] = original_path


@contextlib.contextmanager
def make_container(tmp_path, fake_content, base="scratch"):
    fake_container_tag = "osbuild-test-" + "".join(random.choices(string.digits, k=12))
    fake_container_src = tmp_path / "fake-container-src"
    fake_container_src.mkdir(exist_ok=True)
    make_fake_tree(fake_container_src, fake_content)
    fake_containerfile_path = fake_container_src / "Containerfile"
    container_file_content = f"""
    FROM {base}
    COPY . .
    """
    fake_containerfile_path.write_text(container_file_content, encoding="utf8")
    subprocess.check_call([
        "podman", "build",
        "--no-cache",
        "-t", fake_container_tag,
        "-f", os.fspath(fake_containerfile_path),
    ])
    try:
        yield fake_container_tag
    finally:
        subprocess.check_call(["podman", "image", "rm", fake_container_tag])


@contextlib.contextmanager
def pull_oci_archive_container(archive_path, image_name):
    subprocess.check_call(["skopeo", "copy", f"oci-archive:{archive_path}", f"containers-storage:{image_name}"])
    try:
        yield
    finally:
        subprocess.check_call(["skopeo", "delete", f"containers-storage:{image_name}"])


def make_fake_service_fd() -> int:
    """Create a file descriptor suitable as input for --service-fd for any
    host.Service

    Note that the service will take over the fd and take care of the
    lifecycle so no need to close it.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    fd = os.dup(sock.fileno())
    return fd


def find_one_subclass_in_module(module: ModuleType, subclass: Type) -> object:
    """Find the class in the given module that is a subclass of the given input

    If multiple classes are found an error is raised.
    """
    cls = None
    for name, memb in inspect.getmembers(
            module,
            predicate=lambda obj: inspect.isclass(obj) and issubclass(obj, subclass)):
        if cls:
            raise ValueError(f"already have {cls}, also found {name}:{memb}")
        cls = memb
    return cls


def make_fake_images_inputs(fake_oci_path, name):
    fname = fake_oci_path.name
    dirname = fake_oci_path.parent
    return {
        "images": {
            "path": dirname,
            "data": {
                "archives": {
                    fname: {
                        "format": "oci-archive",
                        "name": name,
                    },
                },
            },
        },
    }
