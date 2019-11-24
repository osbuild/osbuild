
import contextlib
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


RESET = "\033[0m"
BOLD = "\033[1m"


class StageFailed(Exception):
    def __init__(self, name, returncode, output):
        super(StageFailed, self).__init__()
        self.name = name
        self.returncode = returncode
        self.output = output


class AssemblerFailed(Exception):
    def __init__(self, name, returncode, output):
        super(AssemblerFailed, self).__init__()
        self.name = name
        self.returncode = returncode
        self.output = output


def print_header(title, options):
    print()
    print(f"{RESET}{BOLD}{title}{RESET} " + json.dumps(options or {}, indent=2))
    print()


class Stage:
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

    def run(self, tree, runner, build_tree, interactive=False, check=True, libdir=None):
        with buildroot.BuildRoot(build_tree, runner, libdir=libdir) as build_root:
            if interactive:
                print_header(f"{self.name}: {self.id}", self.options)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            with build_root.bound_socket("osbuild") as osbuild_sock, \
                API(osbuild_sock, args, interactive) as api:
                r = build_root.run(
                    [f"/run/osbuild/lib/stages/{self.name}"],
                    binds=[f"{tree}:/run/osbuild/tree"],
                    stdin=subprocess.DEVNULL,
                )
                if check and r.returncode != 0:
                    raise StageFailed(self.name, r.returncode, api.output)

            return r.returncode == 0


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

    def run(self, tree, runner, build_tree, output_dir=None, interactive=False, check=True, libdir=None):
        with buildroot.BuildRoot(build_tree, runner, libdir=libdir) as build_root:
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
            with build_root.bound_socket("remoteloop") as loop_sock, \
                build_root.bound_socket("osbuild") as osbuild_sock, \
                remoteloop.LoopServer(loop_sock), \
                API(osbuild_sock, args, interactive) as api:
                r = build_root.run(
                    [f"/run/osbuild/lib/assemblers/{self.name}"],
                    binds=binds,
                    readonly_binds=ro_binds,
                    stdin=subprocess.DEVNULL,
                )
                if check and r.returncode != 0:
                    raise AssemblerFailed(self.name, r.returncode, api.output)

            return r.returncode == 0


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

    def add_stage(self, name, options=None):
        build = self.build.tree_id if self.build else None
        stage = Stage(name, build, self.tree_id, options or {})
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

    @contextlib.contextmanager
    def get_buildtree(self, object_store):
        if self.build:
            with object_store.get(self.build.tree_id) as tree:
                yield tree
        else:
            with tempfile.TemporaryDirectory(dir=object_store.store) as tmp:
                subprocess.run(["mount", "--make-private", "-o", "bind,ro,mode=0755", "/", tmp], check=True)
                try:
                    yield tmp
                finally:
                    subprocess.run(["umount", "--lazy", tmp], check=True)

    def run(self, store, interactive=False, check=True, libdir=None):
        os.makedirs("/run/osbuild", exist_ok=True)
        object_store = objectstore.ObjectStore(store)
        if self.build:
            if not self.build.run(store, interactive, check, libdir):
                return False

        with self.get_buildtree(object_store) as build_tree:
            if self.stages:
                if not object_store.contains(self.tree_id):
                    # Find the last stage that already exists in the object store, and use
                    # that as the base.
                    base = None
                    base_idx = -1
                    for i in reversed(range(len(self.stages))):
                        if object_store.contains(self.stages[i].id):
                            base = self.stages[i].id
                            base_idx = i
                            break
                    # The tree does not exist. Create it and save it to the object store. If
                    # two run() calls race each-other, two trees may be generated, and it
                    # is nondeterministic which of them will end up referenced by the tree_id
                    # in the content store. However, we guarantee that all tree_id's and all
                    # generated trees remain valid.
                    with object_store.new(self.tree_id, base_id=base) as tree:
                        for stage in self.stages[base_idx + 1:]:
                            if not stage.run(tree,
                                             self.runner,
                                             build_tree,
                                             interactive=interactive,
                                             check=check,
                                             libdir=libdir):
                                return False

            if self.assembler and not object_store.contains(self.output_id):
                with object_store.get(self.tree_id) as tree, \
                    object_store.new(self.output_id) as output_dir:
                    if not self.assembler.run(tree,
                                              self.runner,
                                              build_tree,
                                              output_dir=output_dir,
                                              interactive=interactive,
                                              check=check,
                                              libdir=libdir):
                        return False

        return True


def load_build(description):
    pipeline = description.get("pipeline")
    if pipeline:
        build_pipeline = load(pipeline)
    else:
        build_pipeline = None

    return build_pipeline, description["runner"]


def load(description):
    build = description.get("build")
    if build:
        build_pipeline, runner = load_build(build)
    else:
        build_pipeline, runner = None, None

    pipeline = Pipeline(runner, build_pipeline)

    for s in description.get("stages", []):
        pipeline.add_stage(s["name"], s.get("options", {}))

    a = description.get("assembler")
    if a:
        pipeline.set_assembler(a["name"], a.get("options", {}))

    return pipeline
