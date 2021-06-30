#!/usr/bin/python3

"""Manifest-Pre-Processor

This manifest-pre-processor takes a path to a manifest, loads it,
runs various pre-processing options and then produces a resultant manfest, written
to a specified filename (or stdout if filename is "-").

Manifest format version "1" and "2" are supported.

Pipeline Import:

This tool imports a pipeline from another file and inserts it into a manifest
at the same position the import instruction is located. Sources from the
imported manifest are merged with the existing sources.

The parameters for this pre-processor for format version "1" look like this:

```
...
    "mpp-import-pipeline": {
      "path": "./manifest.json"
    }
...
```

The parameters for this pre-processor for format version "2" look like this:

```
...
    "mpp-import-pipeline": {
      "path": "./manifest.json",
      "id:" "build"
    }
...
```


Depsolving:

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
import pathlib
import tempfile
from typing import Dict
import urllib.parse
import collections
import dnf
import hawkey

from osbuild.util.rhsm import Subscriptions


def element_enter(element, key, default):
    if key not in element:
        element[key] = default.copy()
    return element[key]


class DepSolver:
    def __init__(self, cachedir, persistdir):
        self.cachedir = cachedir
        self.persistdir = persistdir
        self.basedir = None

        self.subscriptions = None
        self.secrets = {}

        self.base = dnf.Base()

    def reset(self, basedir):
        base = self.base
        base.reset(goal=True, repos=True, sack=True)
        self.secrets.clear()

        if self.cachedir:
            base.conf.cachedir = self.cachedir
        base.conf.config_file_path = "/dev/null"
        base.conf.persistdir = self.persistdir

        self.base = base
        self.basedir = basedir

    def setup(self, arch, module_platform_id, ignore_weak_deps):
        base = self.base

        base.conf.module_platform_id = module_platform_id
        base.conf.substitutions['arch'] = arch
        base.conf.substitutions['basearch'] = dnf.rpm.basearch(arch)
        base.conf.install_weak_deps = not ignore_weak_deps

    def expand_baseurl(self, baseurl):
        """Expand non-uris as paths relative to basedir into a file:/// uri"""
        basedir = self.basedir
        try:
            result = urllib.parse.urlparse(baseurl)
            if not result.scheme:
                path = basedir.joinpath(baseurl)
                return path.as_uri()
        except:  # pylint: disable=bare-except
            pass
        return baseurl

    def get_secrets(self, url, desc):
        if not desc:
            return None

        name = desc.get("name")
        if name != "org.osbuild.rhsm":
            raise ValueError(f"Unknown secret type: {name}")

        try:
            # rhsm secrets only need to be retrieved once and can then be reused
            if not self.subscriptions:
                self.subscriptions = Subscriptions.from_host_system()
            secrets = self.subscriptions.get_secrets(url)
        except RuntimeError as e:
            raise ValueError(f"Error getting secrets: {e.args[0]}") from None

        secrets["type"] = "org.osbuild.rhsm"

        return secrets

    def add_repo(self, desc, baseurl):
        repo = dnf.repo.Repo(desc["id"], self.base.conf)
        url = None
        url_keys = ["baseurl", "metalink", "mirrorlist"]
        skip_keys = ["id", "secrets"]
        supported = ["baseurl", "metalink", "mirrorlist",
                     "enabled", "metadata_expire", "gpgcheck", "username", "password", "priority",
                     "sslverify", "sslcacert", "sslclientkey", "sslclientcert"]

        for key in desc.keys():
            if key in skip_keys:
                continue  # We handled this already

            if key in url_keys:
                url = desc[key]
            if key in supported:
                value = desc[key]
                if key == "baseurl":
                    value = self.expand_baseurl(value)
                setattr(repo, key, value)
            else:
                raise ValueError(f"Unknown repo config option {key}")

        if not url:
            url = self.expand_baseurl(baseurl)

        if not url:
            raise ValueError("repo description does not contain baseurl, metalink, or mirrorlist keys")

        secrets = self.get_secrets(url, desc.get("secrets"))

        if secrets:
            if "ssl_ca_cert" in secrets:
                repo.sslcacert = secrets["ssl_ca_cert"]
            if "ssl_client_key" in secrets:
                repo.sslclientkey = secrets["ssl_client_key"]
            if "ssl_client_cert" in secrets:
                repo.sslclientcert = secrets["ssl_client_cert"]
            self.secrets[repo.id] = secrets["type"]

        self.base.repos.add(repo)

        return repo

    def resolve(self, packages, excludes):
        base = self.base

        base.reset(goal=True, sack=True)
        base.fill_sack(load_system_repo=False)

        base.install_specs(packages, exclude=excludes)
        base.resolve()

        deps = []

        for tsi in base.transaction:
            if tsi.action not in dnf.transaction.FORWARD_ACTIONS:
                continue

            checksum_type = hawkey.chksum_name(tsi.pkg.chksum[0])
            checksum_hex = tsi.pkg.chksum[1].hex()

            path = tsi.pkg.relativepath
            reponame = tsi.pkg.reponame
            baseurl = self.base.repos[reponame].baseurl[0]  # self.expand_baseurl(baseurls[reponame])
            # dep["path"] often starts with a "/", even though it's meant to be
            # relative to `baseurl`. Strip any leading slashes, but ensure there's
            # exactly one between `baseurl` and the path.
            url = urllib.parse.urljoin(baseurl + "/", path.lstrip("/"))
            secret = self.secrets.get(reponame)

            pkg = {
                "checksum": f"{checksum_type}:{checksum_hex}",
                "name": tsi.pkg.name,
                "url": url,
            }

            if secret:
                pkg["secrets"] = secret
            deps.append(pkg)

        return deps


class ManifestFile:
    @staticmethod
    def load(path):
        with open(path) as f:
            return ManifestFile.load_from_fd(f, path)

    @staticmethod
    def load_from_fd(f, path):
        # We use OrderedDict to preserve key order (for python < 3.6)
        data = json.load(f, object_pairs_hook=collections.OrderedDict)

        version = int(data.get("version", "1"))
        if version == 1:
            return ManifestFileV1(path, data)
        elif version == 2:
            return ManifestFileV2(path, data)
        raise ValueError(f"Unknown manfest version {version}")

    def __init__(self, path, root, version):
        self.path = pathlib.Path(path)
        self.basedir = self.path.parent
        self.root = root
        self.version = version
        self.sources = element_enter(self.root, "sources", {})
        self.source_urls = {}

    def load_import(self, path, search_dirs):
        m = self.find_and_load_manifest(path, search_dirs)
        if m.version != self.version:
            raise ValueError(f"Incompatible manifest version {m.version}")
        return m

    def find_and_load_manifest(self, path, dirs):
        for p in [self.basedir] + dirs:
            with contextlib.suppress(FileNotFoundError):
                fullpath = os.path.join(p, path)
                with open(fullpath, "r") as f:
                    return ManifestFile.load_from_fd(f, path)

        raise FileNotFoundError(f"Could not find manifest '{path}'")

    def depsolve(self, solver: DepSolver, desc: Dict):
        repos = desc.get("repos", [])
        packages = desc.get("packages", [])
        excludes = desc.get("excludes", [])
        baseurl = desc.get("baseurl")

        if not packages:
            return []

        solver.reset(self.basedir)

        for repo in repos:
            solver.add_repo(repo, baseurl)

        return solver.resolve(packages, excludes)

    def add_packages(self, deps):
        checksums = []

        for dep in deps:
            checksum, url = dep["checksum"], dep["url"]

            secretes = dep.get("secrets")
            if secretes:
                data = {
                    "url": url,
                    "secrets": secretes
                }
            else:
                data = url

            self.source_urls[checksum] = data
            checksums.append(checksum)

        return checksums

    def sort_urls(self):
        def get_sort_key(item):
            key = item[1]
            if isinstance(key, dict):
                key = key["url"]
            return key

        urls = self.source_urls
        if not urls:
            return urls

        urls_sorted = sorted(urls.items(), key=get_sort_key)
        urls.clear()
        urls.update(collections.OrderedDict(urls_sorted))

    def write(self, file, sort_keys=False):
        self.sort_urls()
        json.dump(self.root, file, indent=2, sort_keys=sort_keys)
        file.write("\n")


class ManifestFileV1(ManifestFile):
    def __init__(self, path, data):
        super().__init__(path, data, 1)
        self.pipeline = element_enter(self.root, "pipeline", {})

        files = element_enter(self.sources, "org.osbuild.files", {})
        self.source_urls = element_enter(files, "urls", {})

    def _process_import(self, build, search_dirs):
        mpp = build.get("mpp-import-pipeline")
        if not mpp:
            return

        path = mpp["path"]
        imp = self.load_import(path, search_dirs)

        # We only support importing manifests with URL sources. Other sources are
        # not supported, yet. This can be extended in the future, but we should
        # maybe rather try to make sources generic (and repeatable?), so we can
        # deal with any future sources here as well.
        assert list(imp.sources.keys()) == ["org.osbuild.files"]

        # We import `sources` from the manifest, as well as a pipeline description
        # from the `pipeline` entry. Make sure nothing else is in the manifest, so
        # we do not accidentally miss new features.
        assert list(imp.root.keys()).sort() == ["pipeline", "sources"].sort()

        # Now with everything imported and verified, we can merge the pipeline back
        # into the original manifest. We take all URLs and merge them in the pinned
        # url-array, and then we take the pipeline and simply override any original
        # pipeline at the position where the import was declared.

        self.source_urls.update(imp.source_urls)

        build["pipeline"] = imp.pipeline
        del(build["mpp-import-pipeline"])

    def process_imports(self, search_dirs):
        current = self.root
        while current:
            self._process_import(current, search_dirs)
            current = current.get("pipeline", {}).get("build")

    def _process_depsolve(self, solver, stage):
        if stage.get("name", "") != "org.osbuild.rpm":
            return
        options = stage.get("options")
        if not options:
            return
        mpp = options.get("mpp-depsolve")
        if not mpp:
            return

        del(options["mpp-depsolve"])

        packages = element_enter(options, "packages", [])

        deps = self.depsolve(solver, mpp)
        checksums = self.add_packages(deps)

        packages += checksums

    def process_depsolves(self, solver, pipeline=None):
        if pipeline is None:
            pipeline = self.pipeline
        stages = element_enter(pipeline, "stages", [])
        for stage in stages:
            self._process_depsolve(solver, stage)
        build = pipeline.get("build")
        if build:
            if "pipeline" in build:
                self.process_depsolves(solver, build["pipeline"])


class ManifestFileV2(ManifestFile):
    def __init__(self, path, data):
        super().__init__(path, data, 2)
        self.pipelines = element_enter(self.root, "pipelines", {})

        files = element_enter(self.sources, "org.osbuild.curl", {})
        self.source_urls = element_enter(files, "items", {})

    def get_pipeline_by_name(self, name):
        for pipeline in self.pipelines:
            if pipeline["name"] == name:
                return pipeline

        raise ValueError(f"Pipeline '{name}' not found in {self.path}")

    def _process_import(self, pipeline, search_dirs):
        mpp = pipeline.get("mpp-import-pipeline")
        if not mpp:
            return

        path = mpp["path"]
        imp = self.load_import(path, search_dirs)

        for source, desc in imp.sources.items():
            target = self.sources.get(source)
            if not target:
                # new source, just copy everything
                self.sources[source] = desc
                continue

            if desc.get("options"):
                options = element_enter(target, "options", {})
                options.update(desc["options"])

            items = element_enter(target, "items", {})
            items.update(desc.get("items", {}))

        del(pipeline["mpp-import-pipeline"])
        target = imp.get_pipeline_by_name(mpp["id"])
        pipeline.update(target)

    def process_imports(self, search_dirs):
        for pipeline in self.pipelines:
            self._process_import(pipeline, search_dirs)

    def _process_depsolve(self, solver, stage):
        if stage.get("type", "") != "org.osbuild.rpm":
            return
        inputs = element_enter(stage, "inputs", {})
        packages = element_enter(inputs, "packages", {})
        mpp = packages.get("mpp-depsolve")
        if not mpp:
            return

        del(packages["mpp-depsolve"])

        refs = element_enter(packages, "references", {})

        deps = self.depsolve(solver, mpp)
        checksums = self.add_packages(deps)

        for checksum in checksums:
            refs[checksum] = {}

    def process_depsolves(self, solver):
        for pipeline in self.pipelines:
            stages = element_enter(pipeline, "stages", [])
            for stage in stages:
                self._process_depsolve(solver, stage)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manifest pre processor")
    parser.add_argument(
        "--dnf-cache",
        metavar="PATH",
        type=os.path.abspath,
        default=None,
        help="Path to DNF cache-directory to use",
    )
    parser.add_argument(
        "-I,--import-dir",
        dest="searchdirs",
        default=[],
        action="append",
        help="Search for import in that directory",
    )
    parser.add_argument(
        "--sort-keys",
        dest="sort_keys",
        action='store_true',
        help="Sort keys in generated json",
    )
    parser.add_argument(
        "src",
        metavar="SRCPATH",
        help="Input manifest",
    )
    parser.add_argument(
        "dst",
        metavar="DESTPATH",
        help="Output manifest",
    )

    args = parser.parse_args(sys.argv[1:])

    m = ManifestFile.load(args.src)

    # First resolve all imports
    m.process_imports(args.searchdirs)

    with tempfile.TemporaryDirectory() as persistdir:
        solver = DepSolver(args.dnf_cache, persistdir)
        m.process_depsolves(solver)

    with sys.stdout if args.dst == "-" else open(args.dst, "w") as f:
        m.write(f, args.sort_keys)
