"""
Test related utilities
"""
import contextlib
import os
import pathlib
import re
import shutil
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
