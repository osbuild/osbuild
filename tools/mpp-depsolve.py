#!/usr/bin/python3

"""Manifest-Pre-Processor - Depsolving

This manifest-pre-processor consumes a manifest on stdin, processes it, and
produces the resulting manifest on stdout.

This tool adjusts the `org.osbuild.rpm` stage. It consumes the `mpp-depsolve`
option and produces a package-list and source-entries.

The parameters for this pre-processor look like this:

```
...
    {
      "name": "org.osbuild.rpm",
      ...
      "options": {
        ...
        "mpp-depsolve": {
          "architecture": "x86_64",
          "module-platform-id": "f32",
          "baseurl": "http://mirrors.kernel.org/fedora/releases/32/Everything/x86_64/os",
          "repos": [
            {
              "id": "default",
              "metalink": "https://mirrors.fedoraproject.org/metalink?repo=fedora-32&arch=$basearch"
            }
          ],
          "packages": [
            "@core",
            "dracut-config-generic",
            "grub2-pc",
            "kernel"
          ]
        }
      }
    }
...
```
"""

import argparse
import contextlib
import json
import os
import sys
import tempfile

import dnf
import hawkey


class State:
    dnf_cache = None                    # DNF Cache Directory

    manifest = None                     # Input/Working Manifest
    manifest_urls = None                # Link to sources URL dict
    manifest_todo = []                  # Array of links to RPM stages


def _dnf_repo(conf, desc):
    repo = dnf.repo.Repo(desc["id"], conf)
    repo.metalink = desc["metalink"]
    return repo


def _dnf_base(repos, module_platform_id, persistdir, cachedir, arch):
    base = dnf.Base()
    base.conf.cachedir = cachedir
    base.conf.config_file_path = "/dev/null"
    base.conf.module_platform_id = module_platform_id
    base.conf.persistdir = persistdir
    base.conf.substitutions['arch'] = arch
    base.conf.substitutions['basearch'] = dnf.rpm.basearch(arch)

    for repo in repos:
        base.repos.add(_dnf_repo(base.conf, repo))

    base.fill_sack(load_system_repo=False)
    return base


def _dnf_resolve(state, mpp_depsolve):
    deps = []

    arch = mpp_depsolve["architecture"]
    mpid = mpp_depsolve["module-platform-id"]
    repos = mpp_depsolve.get("repos", [])
    packages = mpp_depsolve.get("packages", [])

    if len(packages) > 0:
        with tempfile.TemporaryDirectory() as persistdir:
            base = _dnf_base(repos, mpid, persistdir, state.dnf_cache, arch)
            base.install_specs(packages)
            base.resolve()

            for tsi in base.transaction:
                if tsi.action not in dnf.transaction.FORWARD_ACTIONS:
                    continue

                checksum_type = hawkey.chksum_name(tsi.pkg.chksum[0])
                checksum_hex = tsi.pkg.chksum[1].hex()
                pkg = {
                    "checksum": f"{checksum_type}:{checksum_hex}",
                    "name": tsi.pkg.name,
                    "path": tsi.pkg.relativepath,
                }
                deps.append(pkg)

    return deps


def _manifest_enter(manifest, key, default):
    if key not in manifest:
        manifest[key] = default
    return manifest[key]


def _manifest_parse(state, data):
    manifest = data

    # Resolve "sources"."org.osbuild.files"."url".
    manifest_sources = _manifest_enter(manifest, "sources", {})
    manifest_files = _manifest_enter(manifest_sources, "org.osbuild.files", {})
    manifest_urls = _manifest_enter(manifest_files, "urls", {})

    # Resolve "pipeline"."stages".
    manifest_pipeline = _manifest_enter(manifest, "pipeline", {})
    manifest_stages = _manifest_enter(manifest_pipeline, "stages", [])

    # Collect all stages of interest in `manifest_todo`.
    manifest_todo = []
    for stage in manifest_stages:
        if stage.get("name", "") != "org.osbuild.rpm":
            continue

        stage_options = _manifest_enter(stage, "options", {})
        if "mpp-depsolve" not in stage_options:
            continue

        manifest_todo.append(stage)

    # Remember links of interest.
    state.manifest = manifest
    state.manifest_urls = manifest_urls
    state.manifest_todo = manifest_todo


def _manifest_depsolve(state, stage):
    options = _manifest_enter(stage, "options", {})
    options_mpp = _manifest_enter(options, "mpp-depsolve", {})
    options_packages = _manifest_enter(options, "packages", [])
    baseurl = options_mpp["baseurl"]

    del(options["mpp-depsolve"])

    deps = _dnf_resolve(state, options_mpp)
    for dep in deps:
        options_packages.append(dep["checksum"])
        state.manifest_urls[dep["checksum"]] = baseurl + "/" + dep["path"]


def _main_args(argv):
    parser = argparse.ArgumentParser(description="Generate Test Manifests")

    parser.add_argument(
        "--dnf-cache",
        metavar="PATH",
        type=os.path.abspath,
        default=None,
        help="Path to DNF cache-directory to use",
    )

    return parser.parse_args(argv[1:])


@contextlib.contextmanager
def _main_state(args):
    state = State()

    with tempfile.TemporaryDirectory() as dnf_cache:
        state.dnf_cache = args.dnf_cache or dnf_cache
        yield state


def _main_process(state):
    src = json.load(sys.stdin)
    _manifest_parse(state, src)

    for stage in state.manifest_todo:
        _manifest_depsolve(state, stage)

    json.dump(state.manifest, sys.stdout, indent=2)
    sys.stdout.write("\n")


def main() -> int:
    args = _main_args(sys.argv)
    with _main_state(args) as state:
        _main_process(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
