import contextlib
import json
import os
import pathlib

import pytest

from .. import test


@pytest.fixture(name="jsondata", scope="module")
def jsondata_fixture():
    return json.dumps({
        "version": "2",
        "pipelines": [
            {
                "name": "image",
                "stages": [
                    {
                        "type": "org.osbuild.truncate",
                        "options": {
                            "filename": "foo.img",
                            "size": "10",
                        },
                    },
                    {
                        # cannot use org.osbuild.chown as it needs the chown
                        # binary in the stage
                        "type": "org.osbuild.testing.injectpy",
                        "options": {
                            "code": [
                                'import os',
                                'os.chown(f"{tree}/foo.img", 1000, 1000)',
                            ],
                        },
                    },
                ]
            }
        ]
    })


@pytest.fixture(name="osb", scope="module")
def osbuild_fixture():
    with test.OSBuild() as osb:
        yield osb


@pytest.fixture(name="testing_libdir")
def testing_libdir_fixture():
    tests_path = pathlib.Path(__file__).parent.parent
    yield f".:{tests_path}"


@pytest.mark.skipif(os.getuid() != 0, reason="root-only")
def test_exports_normal(osb, tmp_path, jsondata, testing_libdir):  # pylint: disable=unused-argument
    osb.compile(jsondata, output_dir=tmp_path, exports=["image"], libdir=testing_libdir)
    expected_export = tmp_path / "image/foo.img"
    assert expected_export.exists()
    assert expected_export.stat().st_uid == 1000


@pytest.mark.skipif(os.getuid() != 0, reason="root-only")
def test_exports_with_force_no_preserve_owner(osb, tmp_path, jsondata, testing_libdir):
    k = "OSBUILD_EXPORT_FORCE_NO_PRESERVE_OWNER"
    with contextlib.ExitStack() as cm:
        os.environ[k] = "1"

        def _delenv():
            del os.environ[k]
        cm.callback(_delenv)

        osb.compile(jsondata, output_dir=tmp_path, exports=["image"], libdir=testing_libdir)
        expected_export = tmp_path / "image/foo.img"
        assert expected_export.exists()
        assert expected_export.stat().st_uid == 0
    assert k not in os.environ
