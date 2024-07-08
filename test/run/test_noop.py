#
# Runtime Tests for No-op Pipelines
#

import json
import os

import pytest

import osbuild.main_cli

from .. import test


@pytest.fixture(name="jsondata", scope="module")
def jsondata_fixture():
    return json.dumps({
        "version": "2",
        "pipelines": [
            {
                "name": "noop",
                "stages": [
                    {
                        "type": "org.osbuild.noop",
                        "options": {"zero": 0},
                        "inputs": {
                            "tree": {
                                "type": "org.osbuild.noop",
                                "origin": "org.osbuild.pipeline",
                                "references": {
                                    "foo": {}
                                }
                            }
                        }
                    }
                ]
            }
        ]
    })


@pytest.fixture(name="osb", scope="module")
def osbuild_fixture():
    with test.OSBuild() as osb:
        yield osb

#
# Run a noop Pipeline. Run twice to verify the cache does not affect
# the operation (we do not have checkpoints, nor any stages that could
# be checkpointed).
#
# Then run the entire thing again, to verify our own `osbuild` executor
# tears things down properly and allows to be executed multiple times.
#


def test_noop(osb):
    osb.compile("{}", checkpoints=[])
    osb.compile("{}", checkpoints=[])


def test_noop2(osb):
    osb.compile("{}", checkpoints=[])
    osb.compile("{}", checkpoints=[])


@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
def test_noop_v2(osb, tmp_path, jsondata):
    osb.compile(jsondata, output_dir=tmp_path, exports=["noop"])


def test_noop_cli(monkeypatch, capfd, tmp_path, jsondata):
    fake_manifest = tmp_path / "manifest.json"
    fake_manifest.write_text(jsondata)

    monkeypatch.setattr("sys.argv", [
        "arg0",
        "--libdir=.", os.fspath(fake_manifest),
        f"--store={tmp_path}",
        "--quiet",
    ])
    ret_code = osbuild.main_cli.osbuild_cli()
    assert ret_code == 0

    captured = capfd.readouterr()
    assert captured.out == ""
