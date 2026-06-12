from unittest import mock

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.rpm"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"kernel_install_env": {"boot_root": "../rel"}}, "'../rel' does not match "),
    ({"nodeps": "yes"}, "is not of type 'boolean'"),
    # good
    ({}, ""),
    ({"kernel_install_env": {"boot_root": "/boot"}}, ""),
    ({"nodeps": True}, ""),
    ({"nodeps": False}, ""),
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


@pytest.mark.parametrize("rpm_output,expected_packages", [
    # all optional fields present
    (
        '{\n'
        '"name": "bash",\n'
        '"version": "5.2.26",\n'
        '"release": "3.fc40",\n'
        '"epoch": "0",\n'
        '"arch": "x86_64",\n'
        '"sigmd5": "abc123",\n'
        '"sha1header": "da39a3ee5e6b4b0d3255bfef95601890afd80709",\n'
        '"sha256header": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",\n'
        '"sha3_256header": "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a",\n'
        '"sigpgp": "deadbeef",\n'
        '"siggpg": null\n'
        '},\n',
        [{
            "name": "bash",
            "version": "5.2.26",
            "release": "3.fc40",
            "epoch": "0",
            "arch": "x86_64",
            "sigmd5": "abc123",
            "sha1header": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
            "sha256header": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "sha3_256header": "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a",
            "sigpgp": "deadbeef",
            "siggpg": None,
        }],
    ),
    # all optional fields null (including new header digests)
    (
        '{\n'
        '"name": "coreutils",\n'
        '"version": "9.4",\n'
        '"release": "1.fc40",\n'
        '"epoch": null,\n'
        '"arch": null,\n'
        '"sigmd5": null,\n'
        '"sha1header": null,\n'
        '"sha256header": null,\n'
        '"sha3_256header": null,\n'
        '"sigpgp": null,\n'
        '"siggpg": null\n'
        '},\n',
        [{
            "name": "coreutils",
            "version": "9.4",
            "release": "1.fc40",
            "epoch": None,
            "arch": None,
            "sigmd5": None,
            "sha1header": None,
            "sha256header": None,
            "sha3_256header": None,
            "sigpgp": None,
            "siggpg": None,
        }],
    ),
    # multiple packages, sorted by name in output
    (
        '{\n'
        '"name": "zsh",\n'
        '"version": "5.9",\n'
        '"release": "1.fc40",\n'
        '"epoch": null,\n'
        '"arch": "x86_64",\n'
        '"sigmd5": null,\n'
        '"sha1header": null,\n'
        '"sha256header": "abc",\n'
        '"sha3_256header": null,\n'
        '"sigpgp": null,\n'
        '"siggpg": null\n'
        '},\n'
        '{\n'
        '"name": "bash",\n'
        '"version": "5.2",\n'
        '"release": "1.fc40",\n'
        '"epoch": null,\n'
        '"arch": "x86_64",\n'
        '"sigmd5": null,\n'
        '"sha1header": "def",\n'
        '"sha256header": null,\n'
        '"sha3_256header": null,\n'
        '"sigpgp": null,\n'
        '"siggpg": null\n'
        '},\n',
        [
            {
                "name": "bash",
                "version": "5.2",
                "release": "1.fc40",
                "epoch": None,
                "arch": "x86_64",
                "sigmd5": None,
                "sha1header": "def",
                "sha256header": None,
                "sha3_256header": None,
                "sigpgp": None,
                "siggpg": None,
            },
            {
                "name": "zsh",
                "version": "5.9",
                "release": "1.fc40",
                "epoch": None,
                "arch": "x86_64",
                "sigmd5": None,
                "sha1header": None,
                "sha256header": "abc",
                "sha3_256header": None,
                "sigpgp": None,
                "siggpg": None,
            },
        ],
    ),
])
@mock.patch("subprocess.run")
def test_generate_package_metadata(mock_run, tmp_path, stage_module, rpm_output, expected_packages):
    mock_run.return_value = mock.Mock(stdout=rpm_output)
    tree = str(tmp_path / "tree")
    result = stage_module.generate_package_metadata(tree, [])
    assert result["packages"] == expected_packages
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "rpm"
    assert "--root" in cmd
    assert "-qa" in cmd
