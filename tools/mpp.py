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
import json
import os
import sys
import pathlib
import tempfile
import urllib.parse
import collections
import dnf
import hawkey

from osbuild.util.rhsm import Subscriptions


def element_enter(element, key, default):
    if key not in element:
        element[key] = default.copy()
    return element[key]


host_subscriptions = None

# Expand non-uris as paths relative to basedir into a file:/// uri


def _dnf_expand_baseurl(baseurl, basedir):
    try:
        result = urllib.parse.urlparse(baseurl)
        if not result.scheme:
            path = basedir.joinpath(baseurl)
            return path.as_uri()
    except:
        pass
    return baseurl


def _dnf_repo(conf, desc, basedir):
    repo = dnf.repo.Repo(desc["id"], conf)
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
                value = _dnf_expand_baseurl(value, basedir)
            setattr(repo, key, value)
        else:
            raise ValueError(f"Unknown repo config option {key}")
    if url == None:
        raise ValueError("repo description does not contain baseurl, metalink, or mirrorlist keys")

    global host_subscriptions
    secrets = None
    if "secrets" in desc:
        secrets_desc = desc["secrets"]
        if "name" in secrets_desc and secrets_desc["name"] == "org.osbuild.rhsm":
            try:
                # rhsm secrets only need to be retrieved once and can then be reused
                if host_subscriptions is None:
                    host_subscriptions = Subscriptions.from_host_system()
                secrets = host_subscriptions.get_secrets(url)
            except RuntimeError as e:
                raise ValueError(f"Error gettting secrets: {e.args[0]}")

    if secrets:
        if "ssl_ca_cert" in secrets:
            repo.sslcacert = secrets["ssl_ca_cert"]
        if "ssl_client_key" in secrets:
            repo.sslclientkey = secrets["ssl_client_key"]
        if "ssl_client_cert" in secrets:
            repo.sslclientcert = secrets["ssl_client_cert"]

    return repo


def _dnf_base(mpp_depsolve, persistdir, cachedir, basedir):
    arch = mpp_depsolve["architecture"]
    module_platform_id = mpp_depsolve["module-platform-id"]
    ignore_weak_deps = bool(mpp_depsolve.get("ignore-weak-deps", False))
    repos = mpp_depsolve.get("repos", [])

    base = dnf.Base()
    if cachedir:
        base.conf.cachedir = cachedir
    base.conf.config_file_path = "/dev/null"
    base.conf.module_platform_id = module_platform_id
    base.conf.persistdir = persistdir
    base.conf.substitutions['arch'] = arch
    base.conf.substitutions['basearch'] = dnf.rpm.basearch(arch)
    base.conf.install_weak_deps = not ignore_weak_deps

    for repo in repos:
        base.repos.add(_dnf_repo(base.conf, repo, basedir))

    base.fill_sack(load_system_repo=False)
    return base


def _dnf_resolve(mpp_depsolve, basedir):
    deps = []

    repos = mpp_depsolve.get("repos", [])
    packages = mpp_depsolve.get("packages", [])
    excludes = mpp_depsolve.get("excludes", [])
    baseurl = mpp_depsolve.get("baseurl")

    baseurls = {
        repo["id"]: repo.get("baseurl", baseurl) for repo in repos
    }
    secrets = {
        repo["id"]: repo.get("secrets", None) for repo in repos
    }

    if len(packages) > 0:
        with tempfile.TemporaryDirectory() as persistdir:
            base = _dnf_base(mpp_depsolve, persistdir, dnf_cache, basedir)
            base.install_specs(packages, exclude=excludes)
            base.resolve()

            for tsi in base.transaction:
                if tsi.action not in dnf.transaction.FORWARD_ACTIONS:
                    continue

                checksum_type = hawkey.chksum_name(tsi.pkg.chksum[0])
                checksum_hex = tsi.pkg.chksum[1].hex()

                path = tsi.pkg.relativepath
                reponame = tsi.pkg.reponame
                base = _dnf_expand_baseurl(baseurls[reponame], basedir)
                # dep["path"] often starts with a "/", even though it's meant to be
                # relative to `baseurl`. Strip any leading slashes, but ensure there's
                # exactly one between `baseurl` and the path.
                url = urllib.parse.urljoin(base + "/", path.lstrip("/"))
                secret = secrets[reponame]

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

    def load_import(self, path):
        m = ManifestFile.load(self.basedir.joinpath(path))
        if m.version != self.version:
            raise ValueError(f"Incompatible manifest version {m.version}")
        return m

    def write(self, file, sort_keys=False):
        json.dump(self.root, file, indent=2, sort_keys=sort_keys)
        file.write("\n")


class ManifestFileV1(ManifestFile):
    def __init__(self, path, data):
        super(ManifestFileV1, self).__init__(path, data, 1)
        self.pipeline = element_enter(self.root, "pipeline", {})

        files = element_enter(self.sources, "org.osbuild.files", {})
        self.source_urls = element_enter(files, "urls", {})

    def _process_import(self, build):
        mpp = build.get("mpp-import-pipeline")
        if not mpp:
            return

        path = mpp["path"]
        imp = self.load_import(path)

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

    def process_imports(self):
        current = self.root
        while current:
            self._process_import(current)
            current = current.get("pipeline", {}).get("build")

    def _process_depsolve(self, stage):
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

        deps = _dnf_resolve(mpp, self.basedir)
        for dep in deps:
            checksum = dep["checksum"]

            packages.append(checksum)

            data = {"url": dep["url"]}
            if "secrets" in dep:
                data["secrets"] = dep["secrets"]
            self.source_urls[checksum] = data

    def process_depsolves(self, pipeline=None):
        if pipeline == None:
            pipeline = self.pipeline
        stages = element_enter(pipeline, "stages", [])
        for stage in stages:
            self._process_depsolve(stage)
        build = pipeline.get("build")
        if build:
            if "pipeline" in build:
                self.process_depsolves(build["pipeline"])


class ManifestFileV2(ManifestFile):
    def __init__(self, path, data):
        super(ManifestFileV2, self).__init__(path, data, 2)
        self.pipelines = element_enter(self.root, "pipelines", {})

        files = element_enter(self.sources, "org.osbuild.curl", {})
        self.source_urls = element_enter(files, "items", {})

    def get_pipeline_by_name(self, name):
        for pipeline in self.pipelines:
            if pipeline["name"] == name:
                return pipeline

        raise ValueError(f"Pipeline '{name}' not found in {self.path}")

    def _process_import(self, pipeline):
        mpp = pipeline.get("mpp-import-pipeline")
        if not mpp:
            return

        path = mpp["path"]
        imp = self.load_import(path)

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

    def process_imports(self):
        for pipeline in self.pipelines:
            self._process_import(pipeline)

    def _process_depsolve(self, stage):
        if stage.get("type", "") != "org.osbuild.rpm":
            return
        inputs = element_enter(stage, "inputs", {})
        packages = element_enter(inputs, "packages", {})
        mpp = packages.get("mpp-depsolve")
        if not mpp:
            return

        refs = element_enter(packages, "references", {})

        deps = _dnf_resolve(mpp, self.basedir)
        for dep in deps:
            checksum = dep["checksum"]
            refs[checksum] = {}

            data = {"url": dep["url"]}
            if "secrets" in dep:
                data["secrets"] = dep["secrets"]
            self.source_urls[checksum] = data

        del(packages["mpp-depsolve"])

    def process_depsolves(self):
        for pipeline in self.pipelines:
            stages = element_enter(pipeline, "stages", [])
            for stage in stages:
                self._process_depsolve(stage)


dnf_cache = None

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

    dnf_cache = args.dnf_cache

    m = ManifestFile.load(args.src)

    # First resolve all imports
    m.process_imports()

    m.process_depsolves()

    with sys.stdout if args.dst == "-" else open(args.dst, "w") as f:
        m.write(f, args.sort_keys)
