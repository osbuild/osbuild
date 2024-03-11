"""
Test related utilities
"""
import contextlib
import os
import pathlib
import re
import shutil
import subprocess
import tempfile


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


def make_fake_input_tree(tmpdir: pathlib.Path, fake_content: dict) -> str:
    """
    Wrapper around make_fake_tree for "input trees"
    """
    basedir = tmpdir / "tree"
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


@contextlib.contextmanager
def mock_command(cmd_name: str, script: str):
    """
    mock_command creates a mocked binary with the given :cmd_name: and :script:
    content. This is useful to e.g. mock errors from binaries.
    """
    original_path = os.environ["PATH"]
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd_path = pathlib.Path(tmpdir) / cmd_name
        cmd_path.write_text(script, encoding="utf8")
        cmd_path.chmod(0o755)
        os.environ["PATH"] = f"{tmpdir}:{original_path}"
        try:
            yield
        finally:
            os.environ["PATH"] = original_path


@contextlib.contextmanager
def make_container(tmp_path, fake_content, base="scratch"):
    fake_container_src = tmp_path / "fake-container-src"
    fake_container_src.mkdir(exist_ok=True)
    make_fake_tree(fake_container_src, fake_content)
    fake_containerfile_path = fake_container_src / "Containerfile"
    container_file_content = f"""
    FROM {base}
    COPY . .
    """
    fake_containerfile_path.write_text(container_file_content, encoding="utf8")
    p = subprocess.Popen([
        "podman", "build",
        "--no-cache",
        "-f", os.fspath(fake_containerfile_path),
    ], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while True:
        line = p.stdout.readline()
        if line == "":
            break
        print(line)
        container_id = line.strip()
    p.wait()
    try:
        yield container_id
    finally:
        subprocess.check_call(["podman", "image", "rm", container_id])


@contextlib.contextmanager
def pull_oci_archive_container(archive_path, image_name):
    subprocess.check_call(["skopeo", "copy", f"oci-archive:{archive_path}", f"containers-storage:{image_name}"])
    try:
        yield
    finally:
        subprocess.check_call(["skopeo", "delete", f"containers-storage:{image_name}"])
