#!/usr/bin/python3

"""Manifest-Pre-Processor - Depsolving

This manifest-pre-processor consumes a manifest on stdin, processes it, and
produces the resulting manifest on stdout.

This tool adjusts the `org.osbuild.rpm` stage. It consumes the `mpp-depsolve`
option and produces a package-list and source-entries.

It supports version "1" and version "2" of the manifest description format.

The parameters for this pre-processor, version "1", look like this:

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
          ],
          "excludes": [
            (optional excludes)
          ]
        }
      }
    }
...
```

The parameters for this pre-processor, version "2", look like this:

```
...
    {
      "name": "org.osbuild.rpm",
      ...
      "inputs": {
        packages: {
          "mpp-depsolve": {
              see above
          }
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
import urllib.parse

import dnf
import hawkey


class State:
    dnf_cache = None                    # DNF Cache Directory

    manifest = None                     # Input/Working Manifest
    manifest_urls = None                # Link to sources URL dict
    manifest_todo = []                  # Array of links to RPM stages


def _dnf_repo(conf, desc):
    repo = dnf.repo.Repo(desc["id"], conf)
    if "baseurl" in desc:
        repo.baseurl = desc["baseurl"]
    elif "metalink" in desc:
        repo.metalink = desc["metalink"]
    elif "mirrorlist" in desc:
        repo.metalink = desc["mirrorlist"]
    else:
        raise ValueError("repo description does not contain baseurl, metalink, or mirrorlist keys")
    return repo


def _dnf_base(repos, module_platform_id, persistdir, cachedir, arch):
    base = dnf.Base()
    if cachedir:
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
    excludes = mpp_depsolve.get("excludes", [])
    baseurl = mpp_depsolve.get("baseurl")

    baseurls = {
        repo["id"]: repo.get("baseurl", baseurl) for repo in repos
    }

    if len(packages) > 0:
        with tempfile.TemporaryDirectory() as persistdir:
            base = _dnf_base(repos, mpid, persistdir, state.dnf_cache, arch)
            base.install_specs(packages, exclude=excludes)
            base.resolve()

            for tsi in base.transaction:
                if tsi.action not in dnf.transaction.FORWARD_ACTIONS:
                    continue

                checksum_type = hawkey.chksum_name(tsi.pkg.chksum[0])
                checksum_hex = tsi.pkg.chksum[1].hex()

                path = tsi.pkg.relativepath
                base = baseurls[tsi.pkg.reponame]
                # dep["path"] often starts with a "/", even though it's meant to be
                # relative to `baseurl`. Strip any leading slashes, but ensure there's
                # exactly one between `baseurl` and the path.
                url = urllib.parse.urljoin(base + "/", path.lstrip("/"))

                pkg = {
                    "checksum": f"{checksum_type}:{checksum_hex}",
                    "name": tsi.pkg.name,
                    "url": url,
                }
                deps.append(pkg)

    return deps


def _manifest_enter(manifest, key, default):
    if key not in manifest:
        manifest[key] = default
    return manifest[key]


def _manifest_parse_v1(state, data):
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


def _manifest_process_v1(state, stage):
    options = _manifest_enter(stage, "options", {})
    options_mpp = _manifest_enter(options, "mpp-depsolve", {})
    options_packages = _manifest_enter(options, "packages", [])

    del(options["mpp-depsolve"])

    deps = _dnf_resolve(state, options_mpp)
    for dep in deps:
        options_packages.append(dep["checksum"])
        state.manifest_urls[dep["checksum"]] = dep["url"]


def _manifest_depsolve_v1(state, src):
    _manifest_parse_v1(state, src)

    for stage in state.manifest_todo:
        _manifest_process_v1(state, stage)


def _manifest_parse_v2(state, manifest):
    todo = []

    for pipeline in manifest.get("pipelines", {}):
        for stage in pipeline.get("stages", []):
            if stage["type"] != "org.osbuild.rpm":
                continue

            inputs = _manifest_enter(stage, "inputs", {})
            packages = _manifest_enter(inputs, "packages", {})

            if "mpp-depsolve" not in packages:
                continue

            todo.append(packages)

    sources = _manifest_enter(manifest, "sources", {})
    files = _manifest_enter(sources, "org.osbuild.curl", {})
    urls = _manifest_enter(files, "items", {})

    state.manifest = manifest
    state.manifest_todo = todo
    state.manifest_urls = urls


def _manifest_process_v2(state, ip):
    urls = state.manifest_urls
    refs = _manifest_enter(ip, "references", {})

    mpp = ip["mpp-depsolve"]

    deps = _dnf_resolve(state, mpp)

    for dep in deps:
        checksum = dep["checksum"]
        refs[checksum] = {}
        urls[checksum] = dep["url"]

    del ip["mpp-depsolve"]


def _manifest_depsolve_v2(state, src):
    _manifest_parse_v2(state, src)

    for todo in state.manifest_todo:
        _manifest_process_v2(state, todo)


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
    if args.dnf_cache:
        state.dnf_cache = args.dnf_cache
    yield state


def _main_process(state):
    src = json.load(sys.stdin)
    version = src.get("version", "1")
    if version == "1":
        _manifest_depsolve_v1(state, src)
    elif version == "2":
        _manifest_depsolve_v2(state, src)
    else:
        print(f"Unknown manifest version {version}", file=sys.stderr)
        return 1

    json.dump(state.manifest, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main() -> int:
    args = _main_args(sys.argv)
    with _main_state(args) as state:
        _main_process(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
