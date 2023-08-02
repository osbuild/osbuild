#
# Runtime Tests for No-op Pipelines
#

import json
import tempfile

import pytest

from .. import test


@pytest.fixture(name="jsondata", scope="module")
def jsondata_fixture():
    return json.dumps(
        {
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
                                    "references": {"foo": {}},
                                }
                            },
                        }
                    ],
                }
            ],
        }
    )


@pytest.fixture(name="tmpdir", scope="module")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


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
def test_noop_v2(osb, tmpdir, jsondata):
    osb.compile(jsondata, output_dir=tmpdir, exports=["noop"])
