import contextlib
import json
import os
import pathlib
import shutil
import subprocess

import pytest

from ..test import osbuild_fixture  # noqa: F401, pylint: disable=unused-import


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


@pytest.fixture(name="testing_libdir", scope="module")
def testing_libdir_fixture(tmpdir_factory):
    tests_path = pathlib.Path(__file__).parent.parent
    project_path = tests_path.parent
    testing_libdir_path = tests_path / "stages"
    fake_libdir_path = tmpdir_factory.mktemp("fake-libdir")
    # there must be an empty "osbild" dir for a "os.listdir(self._libdir)"
    # in buildroot.py
    (fake_libdir_path / "osbuild").mkdir()
    # construct minimal viable libdir from current checkout
    for d in ["stages", "runners", "schemas", "assemblers"]:
        subprocess.run(
            ["cp", "-a", os.fspath(project_path / d), f"{fake_libdir_path}"],
            check=True)
    # now inject testing stages
    for p in testing_libdir_path.glob("org.osbuild.testing.*"):
        shutil.copy2(p, fake_libdir_path / "stages")
    yield fake_libdir_path


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
