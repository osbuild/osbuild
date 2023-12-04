import os
import pathlib
import textwrap
from tempfile import TemporaryDirectory

import pytest

import osbuild
import osbuild.meta


def create_runners(path, distro: str, base: str, versions):
    """Create runner"""
    runners = []

    basename = f"{distro}{base}"
    basepath = os.path.join(path, basename)
    with open(basepath, "x", encoding="utf-8") as f:
        f.write("#!/bin/bash")
        runners.append(basename)

    for x in versions:
        name = f"{distro}{x}"
        link = os.path.join(path, name)
        os.symlink(basepath, link)
        runners.append(name)

    return runners


def test_parse_name():
    table = {
        "arch": {
            "distro": "arch",
            "version": 0,
        },
        "fedora30": {
            "distro": "fedora",
            "version": 30,
        },
        "rhel7": {
            "distro": "rhel",
            "version": 7,
        },
        "ubuntu1804": {
            "distro": "ubuntu",
            "version": 1804,
        }
    }

    for name, want in table.items():
        d, v = osbuild.meta.RunnerInfo.parse_name(name)

        assert d == want["distro"]
        assert v == want["version"]


def test_runner_detection(tmp_path):

    runners = os.path.join(tmp_path, "runners")
    os.makedirs(runners)

    table = {
        "arch": {
            "base": "",
            "versions": [],
            "check": {"": 0},
            "fail": []
        },
        "fedora": {
            "base": 30,
            "versions": list(range(31, 40)),
            "check": {40: 39, 31: 31, 35: 35},
            "fail": [29],
        },
        "ubuntu": {
            "base": 1810,
            "versions": [1904, 1910, 2004],
            "check": {2010: 2004, 1912: 1910},
            "fail": [1804],
        },
        "rhel": {
            "base": 90,
            "versions": [91, 92, 93],
            "check": {94: 93},
        },
        "future": {
            "base": 100,
            "versions": [101, 102, 103],
            "check": {110: 103},
        }
    }

    want_all = []
    for distro, info in table.items():
        base = info["base"] or 0
        versions = info["versions"]
        want = create_runners(runners, distro, str(base), versions)
        meta = osbuild.meta.Index(tmp_path)
        have = meta.list_runners(distro)
        assert len(want) == len(have)
        want_all += want

        for v in [base] + versions:
            name = f"{distro}{v}"
            runner = meta.detect_runner(name)
            assert runner
            assert runner.distro == distro
            assert runner.version == v

        for v, t in info["check"].items():
            name = f"{distro}{v}"
            runner = meta.detect_runner(name)
            assert runner
            assert runner.distro == distro
            assert runner.version == t

        for v in info.get("fail", []):
            name = f"{distro}{v}"
            with pytest.raises(ValueError):
                runner = meta.detect_runner(name)

    have = meta.list_runners()
    assert len(have) == len(want_all)


def test_runner_sorting(tmp_path):

    runners = os.path.join(tmp_path, "runners")
    os.makedirs(runners)

    table = {
        "A": {
            "base": 1,
            "versions": [2, 3]
        },
        "B": {
            "base": 1,
            "versions": [2, 3]
        }
    }

    for distro, info in table.items():
        base = info["base"] or 0
        versions = info["versions"]
        create_runners(runners, distro, str(base), versions)

    meta = osbuild.meta.Index(tmp_path)
    have = meta.list_runners()

    names = [
        f"{i.distro}{i.version}" for i in have
    ]

    assert names == ["A1", "A2", "A3", "B1", "B2", "B3"]


def test_schema():
    schema = osbuild.meta.Schema(None)
    assert not schema

    schema = osbuild.meta.Schema({"type": "bool"})  # should be 'boolean'
    assert not schema.check().valid
    assert not schema

    schema = osbuild.meta.Schema({"type": "array", "minItems": 3})
    assert schema.check().valid
    assert schema

    res = schema.validate([1, 2])
    assert not res
    res = schema.validate([1, 2, 3])
    assert res


def make_fake_meta_json(tmp_path, name):
    meta_json_path = pathlib.Path(f"{tmp_path}/stages/{name}.meta-json")
    meta_json_path.parent.mkdir(exist_ok=True)
    meta_json_path.write_text("""
    {
      "summary": "some json summary",
      "description": [
        "long text",
        "with newlines"
      ],
      "capabilities": ["CAP_MAC_ADMIN", "CAP_BIG_MAC"],
      "schema": {
        "properties": {
          "json_filename": {
            "type": "string"
          }
        }
      },
      "schema_2": {
        "json_devices": {
          "type": "object"
        }
      }
    }
    """.replace("\n", " "), encoding="utf-8")
    return meta_json_path


def make_fake_py_module(tmp_path, name):
    py_path = pathlib.Path(f"{tmp_path}/stages/{name}")
    py_path.parent.mkdir(exist_ok=True)
    fake_py = '"""some py summary\nlong description\nwith newline"""'
    fake_py += textwrap.dedent("""
    SCHEMA = '"properties": {"py_filename":{"type": "string"}}'
    SCHEMA_2 = '"py_devices": {"type":"object"}'
    CAPABILITIES = ['CAP_MAC_ADMIN']
    """)
    py_path.write_text(fake_py, encoding="utf-8")


def test_load_from_json(tmp_path):
    make_fake_meta_json(tmp_path, "org.osbuild.noop")
    modinfo = osbuild.meta.ModuleInfo.load(tmp_path, "Stage", "org.osbuild.noop")
    assert modinfo.desc == "some json summary"
    assert modinfo.info == "long text\nwith newlines"
    assert modinfo.caps == ["CAP_MAC_ADMIN", "CAP_BIG_MAC"]
    assert modinfo.opts == {
        "1": {"properties": {"json_filename": {"type": "string"}}},
        "2": {"json_devices": {"type": "object"}},
    }


def test_load_from_py(tmp_path):
    make_fake_py_module(tmp_path, "org.osbuild.noop")
    modinfo = osbuild.meta.ModuleInfo.load(tmp_path, "Stage", "org.osbuild.noop")
    assert modinfo.desc == "some py summary"
    assert modinfo.info == "long description\nwith newline"
    assert modinfo.caps == set(["CAP_MAC_ADMIN"])
    assert modinfo.opts == {
        "1": {"properties": {"py_filename": {"type": "string"}}},
        "2": {"py_devices": {"type": "object"}},
    }


def test_load_from_json_prefered(tmp_path):
    make_fake_meta_json(tmp_path, "org.osbuild.noop")
    make_fake_py_module(tmp_path, "org.osbuild.noop")
    modinfo = osbuild.meta.ModuleInfo.load(tmp_path, "Stage", "org.osbuild.noop")
    assert modinfo.desc == "some json summary"
    assert modinfo.info == "long text\nwith newlines"
    assert modinfo.caps == ["CAP_MAC_ADMIN", "CAP_BIG_MAC"]
    assert modinfo.opts == {
        "1": {"properties": {"json_filename": {"type": "string"}}},
        "2": {"json_devices": {"type": "object"}},
    }
