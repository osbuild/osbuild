import os.path
import re
from unittest import mock

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.hmac"


@pytest.mark.parametrize("test_data,expected_errs", [
    # bad
    ({}, [r"'paths' is a required property", r"'algorithm' is a required property"]),
    ({"algorithm": "sha512"}, [r"'paths' is a required property"]),
    ({"paths": ["/somefile"]}, [r"'algorithm' is a required property"]),
    ({"paths": [], "algorithm": "sha1"}, [r"(\[\] is too short|\[\] should be non-empty)"]),

    ({"paths": ["/somefiles"], "algorithm": "md5"},
     [r"'md5' is not one of \['sha1', 'sha224', 'sha256', 'sha384', 'sha512'\]"]),

    # good
    (
        {
            "paths": [
                "/greet1.txt",
                "/greet2.txt"
            ],
            "algorithm": "sha256"
        },
        ""
    ),
    (
        {
            "paths": [
                "/path/to/some/file",
                "/boot/efi/EFI/Linux/vmlinuz-linux"
            ],
            "algorithm": "sha512"
        },
        ""
    ),
])
def test_schema_validation_hmac(stage_schema, test_data, expected_errs):
    test_input = {
        "type": STAGE_NAME,
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if not expected_errs:
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        for exp_err in expected_errs:
            testutil.assert_jsonschema_error_contains(res, re.compile(exp_err), expected_num_errs=len(expected_errs))


@mock.patch("subprocess.run")
@pytest.mark.parametrize("options", [
    ({"paths": ["/a/file/path"], "algorithm": "sha512"}),
    ({"paths": ["/b/file/path"], "algorithm": "sha512"}),
    ({"paths": ["/a/file/path", "/b/file/path"], "algorithm": "sha256"}),
])
def test_hmac_cmdline(mock_run, tmp_path, stage_module, options):
    algorithm = options["algorithm"]

    expected_cmds = []
    expected_wds = []
    hmac_paths = []
    for path in options["paths"]:
        # create parent directories because the stage opens a file to write the output to it even when mocking sp.run()
        basename = os.path.basename(path)
        real_path = os.path.join(tmp_path, path.lstrip("/"))
        parent = os.path.dirname(real_path)
        hmac_paths.append(os.path.join(parent, f".{basename}.hmac"))
        os.makedirs(parent, exist_ok=True)
        expected_cmds.append([f"{algorithm}hmac", basename])
        expected_wds.append(parent)

    stage_module.main(tmp_path, options)
    for exp, cwd, actual in zip(expected_cmds, expected_wds, mock_run.call_args_list):
        assert exp == actual[0][0]
        assert cwd == actual[1]["cwd"]

    # the file should have been created by the open() call, but should be empty because we mocked sp.run()
    for path in hmac_paths:
        info = os.stat(path)
        assert info.st_size == 0
