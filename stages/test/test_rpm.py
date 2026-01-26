from unittest import mock

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.rpm"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"kernel_install_env": {"boot_root": "../rel"}}, "'../rel' does not match "),
    # good
    ({}, ""),
    ({"kernel_install_env": {"boot_root": "/boot"}}, ""),
])
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.parametrize("ignore_failures", [
    (False),
    (True),
])
@mock.patch("subprocess.run")
def test_import_gpg_keys(mock_run, tmp_path, stage_module, ignore_failures):
    tree = tmp_path / "tree"
    tree.mkdir()
    stage_module.import_gpg_keys(tree, ["some-key"], "my-binary", [], ignore_failures)
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][0] == "my-binary"
    assert mock_run.call_args[1] == {"check": not ignore_failures}


def test_parse_gpgkeys_input_missing(stage_module):
    inputs = {"packages": {}}
    path, files = stage_module.parse_gpgkeys_input(inputs)
    assert path is None
    assert files is None


def test_parse_gpgkeys_input_present(stage_module):
    inputs = {
        "gpgkeys": {
            "path": "/keys/dir",
            "data": {"files": {"sha256:abc": {}, "sha256:def": {}}},
        }
    }
    path, files = stage_module.parse_gpgkeys_input(inputs)
    assert path == "/keys/dir"
    assert files == {"sha256:abc": {}, "sha256:def": {}}


def test_main_imports_gpgkeys_from_input(tmp_path, stage_module):
    """Keys from options.gpgkeys and inputs.gpgkeys are both passed to import_gpg_keys."""
    tree = tmp_path / "tree"
    tree.mkdir()
    pkgpath = tmp_path / "packages"
    pkgpath.mkdir()
    (pkgpath / "pkg.rpm").write_bytes(b"fake-rpm")
    keypath = tmp_path / "gpgkeys"
    keypath.mkdir()
    key_file = keypath / "sha256:key1"
    key_file.write_text("KEY-CONTENT-FROM-INPUT", encoding="utf-8")

    inputs = {
        "packages": {
            "path": str(pkgpath),
            "data": {"files": {"pkg.rpm": {}}},
        },
        "gpgkeys": {
            "path": str(keypath),
            "data": {"files": {"sha256:key1": {}}},
        },
    }
    options = {"gpgkeys": ["INLINE-KEY-CONTENT"]}

    imported_keys = []

    def capture_import(_tree, keys, *_args, **_kwargs):
        imported_keys.extend(keys)
        raise SystemExit(0)

    with mock.patch.object(stage_module, "import_gpg_keys", side_effect=capture_import):
        with pytest.raises(SystemExit):
            stage_module.main(str(tree), inputs, options)

    assert imported_keys == ["INLINE-KEY-CONTENT", "KEY-CONTENT-FROM-INPUT"]
