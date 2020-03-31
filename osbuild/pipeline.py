
import hashlib
import importlib
import json
import os
import subprocess
import tempfile

from .api import API
from . import buildroot
from . import objectstore
from . import remoteloop
from . import sources


RESET = "\033[0m"
BOLD = "\033[1m"


def cleanup(*objs):
    """Call cleanup method for all objects, filters None values out"""
    _ = map(lambda o: o.cleanup(), filter(None, objs))


class BuildResult:
    def __init__(self, origin, returncode, output):
        self.name = origin.name
        self.id = origin.id
        self.options = origin.options
        self.success = returncode == 0
        self.output = output

    def as_dict(self):
        return vars(self)


def print_header(title, options):
    print()
    print(f"{RESET}{BOLD}{title}{RESET} " + json.dumps(options or {}, indent=2))
    print()


class Stage:
    def __init__(self, name, source_options, build, base, options):
        self.name = name
        self.sources = source_options
        self.build = build
        self.base = base
        self.options = options
        self.checkpoint = False

    @property
    def id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.name, sort_keys=True).encode())
        m.update(json.dumps(self.build, sort_keys=True).encode())
        m.update(json.dumps(self.base, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()

    def description(self):
        description = {}
        description["name"] = self.name
        if self.options:
            description["options"] = self.options
        return description

    def run(self,
            tree,
            runner,
            build_tree,
            cache,
            interactive=False,
            libdir=None,
            var="/var/tmp",
            secrets=None):
        with buildroot.BuildRoot(build_tree, runner, libdir=libdir, var=var) as build_root, \
            tempfile.TemporaryDirectory(prefix="osbuild-sources-output-", dir=var) as sources_output:
            if interactive:
                print_header(f"{self.name}: {self.id}", self.options)

            args = {
                "tree": "/run/osbuild/tree",
                "sources": "/run/osbuild/sources",
                "options": self.options,
            }

            sources_dir = f"{libdir}/sources" if libdir else "/usr/lib/osbuild/sources"

            ro_binds = [f"{sources_output}:/run/osbuild/sources"]
            if not libdir:
                osbuild_module_path = os.path.dirname(importlib.util.find_spec('osbuild').origin)
                # This is a temporary workaround, once we have a common way to include osbuild in the
                # buildroot we should remove this because it includes code from the host in the buildroot thus
                # violating our effort of reproducibility.
                ro_binds.append(f"{osbuild_module_path}:/run/osbuild/lib/stages/osbuild")

            with API(f"{build_root.api}/osbuild", args, interactive) as api, \
                sources.SourcesServer(f"{build_root.api}/sources",
                                      sources_dir,
                                      self.sources,
                                      f"{cache}/sources",
                                      sources_output,
                                      secrets):
                r = build_root.run(
                    [f"/run/osbuild/lib/stages/{self.name}"],
                    binds=[f"{tree}:/run/osbuild/tree"],
                    readonly_binds=ro_binds,
                    stdin=subprocess.DEVNULL,
                )
                return BuildResult(self, r.returncode, api.output)


class Assembler:
    def __init__(self, name, build, base, options):
        self.name = name
        self.build = build
        self.base = base
        self.options = options

    @property
    def id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.name, sort_keys=True).encode())
        m.update(json.dumps(self.build, sort_keys=True).encode())
        m.update(json.dumps(self.base, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()

    def description(self):
        description = {}
        description["name"] = self.name
        if self.options:
            description["options"] = self.options
        return description

    def run(self, tree, runner, build_tree, output_dir=None, interactive=False, libdir=None, var="/var/tmp"):
        with buildroot.BuildRoot(build_tree, runner, libdir=libdir, var=var) as build_root:
            if interactive:
                print_header(f"Assembler {self.name}: {self.id}", self.options)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            binds = []
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                binds.append(f"{output_dir}:/run/osbuild/output")
                args["output_dir"] = "/run/osbuild/output"

            osbuild_module_path = os.path.dirname(importlib.util.find_spec('osbuild').origin)
            ro_binds = [f"{tree}:/run/osbuild/tree"]
            if not libdir:
                # This is a temporary workaround, once we have a common way to include osbuild in the
                # buildroot we should remove this because it includes code from the host in the buildroot thus
                # violating our effort of reproducibility.
                ro_binds.append(f"{osbuild_module_path}:/run/osbuild/lib/assemblers/osbuild")
            with remoteloop.LoopServer(f"{build_root.api}/remoteloop"), \
                API(f"{build_root.api}/osbuild", args, interactive) as api:
                r = build_root.run(
                    [f"/run/osbuild/lib/assemblers/{self.name}"],
                    binds=binds,
                    readonly_binds=ro_binds,
                    stdin=subprocess.DEVNULL,
                )
                return BuildResult(self, r.returncode, api.output)


class Pipeline:
    def __init__(self, runner=None, build=None):
        self.build = build
        self.runner = runner
        self.stages = []
        self.assembler = None

    @property
    def tree_id(self):
        return self.stages[-1].id if self.stages else None

    @property
    def output_id(self):
        return self.assembler.id if self.assembler else None

    def add_stage(self, name, sources_options=None, options=None):
        build = self.build.tree_id if self.build else None
        stage = Stage(name, sources_options, build, self.tree_id, options or {})
        self.stages.append(stage)
        if self.assembler:
            self.assembler.base = stage.id

    def set_assembler(self, name, options=None):
        build = self.build.tree_id if self.build else None
        self.assembler = Assembler(name, build, self.tree_id, options or {})

    def prepend_build_env(self, build_pipeline, runner):
        pipeline = self
        while pipeline.build:
            pipeline = pipeline.build
        pipeline.build = build_pipeline
        pipeline.runner = runner

    def description(self):
        description = {}
        if self.build:
            description["build"] = {
                "pipeline": self.build.description(),
                "runner": self.runner
            }
        if self.stages:
            description["stages"] = [s.description() for s in self.stages]
        if self.assembler:
            description["assembler"] = self.assembler.description()
        return description

    def build_stages(self, object_store, interactive, libdir, secrets):
        results = {"success": True}

        # We need a build tree for the stages below, which is either
        # another tree that needs to be built with the build pipeline
        # or the host file system if no build pipeline is specified
        # NB: the very last level of nested build pipelines is always
        # build on the host

        if not self.build:
            build_tree = objectstore.HostTree(object_store)
        else:
            build = self.build

            r, t, tree = build.build_stages(object_store,
                                            interactive,
                                            libdir,
                                            secrets)

            results["build"] = r
            if not r["success"]:
                results["success"] = False
                return results, None, None

            # Cleanup the build tree (`t`) which was used to
            # build `tree`; it is now not needed anymore
            t.cleanup()

            build_tree = tree

        # If there are no stages, just return build tree we just
        # obtained and a new, clean `tree`
        if not self.stages:
            tree = object_store.new()
            return results, build_tree, tree


        # Create a new tree. The base is our tree_id because if that
        # is already in the store, we can short-circuit directly and
        # exit directly; `tree` is then used to read the tree behind
        # `self.tree_id`
        tree = object_store.new(base_id=self.tree_id)

        if object_store.contains(self.tree_id):
            results["tree_id"] = self.tree_id
            return results, build_tree, tree

        # Not in the store yet, need to actually build it, but maybe
        # an intermediate checkpoint exists: Find the last stage that
        # already exists in the store and use that as the base.
        base_idx = -1
        tree.base = None
        for i in reversed(range(len(self.stages))):
            if object_store.contains(self.stages[i].id):
                tree.base = self.stages[i].id
                base_idx = i
                break

        # If two run() calls race each-other, two trees will get built
        # and it is nondeterministic which of them will end up
        # referenced by the `tree_id` in the content store if they are
        # both committed. However, after the call to commit all the
        # trees will be based on the winner.
        results["stages"] = []

        for stage in self.stages[base_idx + 1:]:
            with build_tree.read() as build_path, tree.write() as path:
                r = stage.run(path,
                              self.runner,
                              build_path,
                              object_store.store,
                              interactive=interactive,
                              libdir=libdir,
                              var=object_store.store,
                              secrets=secrets)

            results["stages"].append(r.as_dict())
            if not r.success:
                cleanup(build_tree, tree)
                results["success"] = False
                return results, None, None

            if stage.checkpoint:
                object_store.commit(tree, stage.id)

        results["tree_id"] = self.tree_id
        return results, build_tree, tree

    def assemble(self, object_store, build_tree, tree, interactive, libdir):
        results = {"success": True}

        if not self.assembler:
            return results

        # if the output is already in the store, short-circuit
        if object_store.contains(self.output_id):
            results["output_id"] = self.output_id
            return results

        output = object_store.new()

        with build_tree.read() as build_dir, \
             tree.read() as input_dir, \
             output.write() as output_dir:

            r = self.assembler.run(input_dir,
                                   self.runner,
                                   build_dir,
                                   output_dir=output_dir,
                                   interactive=interactive,
                                   libdir=libdir,
                                   var=object_store.store)

        results["assembler"] = r.as_dict()
        if not r.success:
            output.cleanup()
            results["success"] = False
            return results

        object_store.commit(output, self.output_id)
        output.cleanup()

        results["output_id"] = self.output_id
        return results

    def run(self, store, interactive=False, libdir=None, secrets=None):
        os.makedirs("/run/osbuild", exist_ok=True)
        results = {}

        with objectstore.ObjectStore(store) as object_store:
            # if the final result is already in the store, exit
            # early and don't attempt to build the tree, which
            # in turn might not be in the store and would in that
            # case be build but not be used
            if object_store.contains(self.output_id):
                results = {"output_id": self.output_id,
                           "success": True}
                if object_store.contains(self.tree_id):
                    results["tree_id"] = self.tree_id
                return results

            results, build_tree, tree = self.build_stages(object_store,
                                                          interactive,
                                                          libdir,
                                                          secrets)

            if not results["success"]:
                return results

            r = self.assemble(object_store,
                              build_tree,
                              tree,
                              interactive,
                              libdir)

            results.update(r)  # This will also update 'success'

        return results


def describe_os(*paths):
    """Read the Operating System Description from `os-release`

    This creates a string describing the running operating-system name and
    version. It reads the information from the path array provided as `paths`.
    The first available file takes precedence. It must be formatted according
    to the rules in `os-release(5)`.

    The returned string uses the format `${ID}${VERSION_ID}` with all dots
    stripped.
    """
    osrelease = {}

    path = next((p for p in paths if os.path.exists(p)), None)
    if path:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line[0] == "#":
                    continue
                key, value = line.split("=", 1)
                osrelease[key] = value.strip('"')

    # Fetch `ID` and `VERSION_ID`. Defaults are defined in `os-release(5)`.
    osrelease_id = osrelease.get("ID", "linux")
    osrelease_version_id = osrelease.get("VERSION_ID", "")

    return osrelease_id + osrelease_version_id.replace(".", "")


def load_build(description, sources_options):
    pipeline = description.get("pipeline")
    if pipeline:
        build_pipeline = load(pipeline, sources_options)
    else:
        build_pipeline = None

    return build_pipeline, description["runner"]


def load(description, sources_options):
    build = description.get("build")
    if build:
        build_pipeline, runner = load_build(build, sources_options)
    else:
        build_pipeline, runner = None, "org.osbuild." + describe_os("/etc/os-release", "/usr/lib/os-release")

    pipeline = Pipeline(runner, build_pipeline)

    for s in description.get("stages", []):
        pipeline.add_stage(s["name"], sources_options, s.get("options", {}))

    a = description.get("assembler")
    if a:
        pipeline.set_assembler(a["name"], a.get("options", {}))

    return pipeline
