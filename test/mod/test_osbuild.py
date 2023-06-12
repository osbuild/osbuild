#
# Basic tests for a collection of osbuild modules.
#

import json
import os
import pathlib
import sys
import tempfile
import unittest

import osbuild
import osbuild.meta
from osbuild.monitor import NullMonitor
from osbuild.objectstore import ObjectStore
from osbuild.pipeline import Manifest, Runner

from .. import test


def names(*lst):
    return [x.name for x in lst]


class MockStore:
    def __init__(self) -> None:
        self.have = set()

    def contains(self, pipeline_id):
        return pipeline_id in self.have


class TestDescriptions(unittest.TestCase):

    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_stage_run(self):
        index = osbuild.meta.Index(os.curdir)
        info = index.get_module_info("Stage", "org.osbuild.noop")
        stage = osbuild.Stage(info, {}, None, None, {}, None)

        with tempfile.TemporaryDirectory() as tmpdir:

            storedir = pathlib.Path(tmpdir, "store")
            root = pathlib.Path("/")
            runner = Runner(index.detect_host_runner())
            monitor = NullMonitor(sys.stderr.fileno())
            libdir = os.path.abspath(os.curdir)
            store = ObjectStore(storedir)

            with ObjectStore(storedir) as store:
                data = store.new(stage.id)
                res = stage.run(data, runner, root, store, monitor, libdir)

        self.assertEqual(res.success, True)
        self.assertEqual(res.id, stage.id)

    def test_manifest(self):
        index = osbuild.meta.Index(os.curdir)

        info = index.get_module_info("Stage", "org.osbuild.noop")

        manifest = Manifest()

        # each pipeline gets a noop stage with different
        # options so that their ids are different
        build = manifest.add_pipeline("build", None, None)
        build.add_stage(info, {"option": 1})

        tree = manifest.add_pipeline("tree",
                                     "org.osbuild.linux",
                                     build.id)
        tree.add_stage(info, {"option": 2})

        assembler = manifest.add_pipeline("assembler",
                                          "org.osbuild.inux",
                                          build.id)
        assembler.add_stage(info, {"option": 3})

        self.assertEqual(len(manifest.pipelines), 3)

        self.assertIn("build", manifest.pipelines)
        self.assertIn("tree", manifest.pipelines)
        self.assertIn("assembler", manifest.pipelines)

        self.assertIn("build", manifest)
        self.assertIn("tree", manifest)
        self.assertIn("assembler", manifest)

        # make sure the order is correct
        lst = ["build", "tree", "assembler"]
        for a, b in zip(manifest.pipelines, lst):
            self.assertEqual(a, b)

        for a, b in zip(manifest, [build, tree, assembler]):
            self.assertEqual(a.name, b.name)

        # check we get exceptions on unknown names
        with self.assertRaises(KeyError):
            _ = manifest.pipelines["foo"]

        with self.assertRaises(KeyError):
            _ = manifest["foo"]

        # check helper functions
        #  access by name
        check = manifest["build"]
        self.assertEqual(build.name, check.name)

        check = manifest["tree"]
        self.assertEqual(tree.name, check.name)

        check = manifest["assembler"]
        self.assertEqual(assembler.name, check.name)

        #  `None` return for unknown items
        check = manifest.get("foo")
        self.assertIsNone(check)

        #  id based access
        for i in [build, tree, assembler]:
            check = manifest[i.id]
            self.assertEqual(i.name, check.name)

    # pylint: disable=too-many-statements
    def test_on_demand(self):
        index = osbuild.meta.Index(os.curdir)
        host_runner = Runner(index.detect_host_runner())
        runner = Runner(index.detect_runner("org.osbuild.linux"))

        manifest = Manifest()
        noop = index.get_module_info("Stage", "org.osbuild.noop")
        noip = index.get_module_info("Input", "org.osbuild.noop")

        # the shared build pipeline
        build = manifest.add_pipeline("build", host_runner, None)
        build.add_stage(noop, {"option": 1})

        # a pipeline simulating some intermediate artefact
        # that other pipeline need as dependency
        dep = manifest.add_pipeline("dep",
                                    runner,
                                    build.id)

        dep.add_stage(noop, {"option": 2})

        # a pipeline that is not linked to the "main"
        # assembler artefact and thus should normally
        # not be built unless explicitly requested
        # has an input that depends on `dep`
        ul = manifest.add_pipeline("unlinked",
                                   runner,
                                   build.id)

        stage = ul.add_stage(noop, {"option": 3})
        ip = stage.add_input("dep", noip, "org.osbuild.pipeline")
        ip.add_reference(dep.id)

        # the main os root file system
        rootfs = manifest.add_pipeline("rootfs",
                                       runner,
                                       build.id)
        stage = rootfs.add_stage(noop, {"option": 4})

        # the main raw image artefact, depending on "dep" and
        # "rootfs"
        image = manifest.add_pipeline("image",
                                      runner,
                                      build.id)

        stage = image.add_stage(noop, {"option": 5})
        ip = stage.add_input("dep", noip, "org.osbuild.pipeline")
        ip.add_reference(dep.id)

        stage = image.add_stage(noop, {"option": 6})

        #  a stage using the rootfs as input (named 'image')
        ip = stage.add_input("image", noip, "org.osbuild.pipeline")
        ip.add_reference(rootfs.id)

        # some compression of the image, like a qcow2
        qcow2 = manifest.add_pipeline("qcow2",
                                      runner,
                                      build.id)
        stage = qcow2.add_stage(noop, {"option": 7})
        ip = stage.add_input("image", noip, "org.osbuild.pipeline")
        ip.add_reference(image.id)

        fmt = index.get_format_info("osbuild.formats.v2").module
        self.assertIsNotNone(fmt)
        print(json.dumps(fmt.describe(manifest), indent=2))

        # The pipeline graph in the manifest with dependencies:
        # ├─╼ build
        # ├─╼ dep
        # │ └ build
        # ├─╼ unlinked
        # │ ├ build
        # │ └ dep
        # ├─╼ rootfs
        # │ └ build
        # ├─╼ image
        # │ ├ build
        # │ ├ dep
        # │ └ rootfs
        # └─╼ qcow2
        #   ├ build
        #   └ image

        store = MockStore()

        # check an empty input leads to an empty list
        res = manifest.depsolve(store, [])
        assert not res

        # the build pipeline should resolve to just itself
        res = manifest.depsolve(store, names(build))
        assert res == names(build)

        # if we build the 'unlinked' pipeline, we get it
        # and its dependencies, dep and build
        res = manifest.depsolve(store, names(ul))
        assert res == names(build, dep, ul)

        # building image with nothing in the store should
        # result in all pipelines but 'unlinked'
        res = manifest.depsolve(store, names(image))
        assert res == names(build, rootfs, dep, image)

        # ensure the order of inputs is preserved during
        # the depsolving so that we build things in the
        # same way they were requested
        res = manifest.depsolve(store, names(ul, image))
        assert res == names(build, dep, ul, rootfs, image)

        res = manifest.depsolve(store, names(image, ul))
        assert res == names(build, rootfs, dep, image, ul)

        # if we have the 'dep' dependency in the store,
        # we should be not be building that
        store.have.add(dep.id)
        res = manifest.depsolve(store, names(image))
        assert res == names(build, rootfs, image)

        # if we only have the build pipeline in the
        # store we should not build that
        store.have.clear()
        store.have.add(build.id)
        res = manifest.depsolve(store, names(image))
        assert res == names(rootfs, dep, image)

        # if we have the final artefact in the store,
        # nothing should be built at all
        store.have.clear()
        store.have.add(image.id)
        res = manifest.depsolve(store, names(image))
        assert not res

        # we have a checkpoint of the stage in the image
        # pipeline with the `dep` dependency, so that
        # it effectively only depends on `rootfs`
        store.have.clear()
        store.have.add(image.stages[0].id)
        res = manifest.depsolve(store, names(image))
        assert res == names(build, rootfs, image)

    def check_moduleinfo(self, version):
        index = osbuild.meta.Index(os.curdir)

        modules = []
        for klass in ("Assembler", "Device", "Input", "Mount", "Source", "Stage"):
            mods = index.list_modules_for_class(klass)
            modules += [(klass, module) for module in mods]

        self.assertTrue(modules)

        for module in modules:
            klass, name = module
            try:
                info = osbuild.meta.ModuleInfo.load(os.curdir, klass, name)
                if not info.opts[version]:
                    print(f"{klass} '{name}' does not support version '{version}'")
                    continue

                schema = osbuild.meta.Schema(info.get_schema(version), name)
                res = schema.check()
                if not res:
                    err = "SCHEMA: " + json.dumps(schema.data, indent=2) + "\n"
                    err += "\n  ".join(str(e) for e in res)
                    self.fail(str(res) + "\n  " + err)
            except json.decoder.JSONDecodeError as e:
                msg = f"{klass} '{name}' has invalid STAGE_OPTS\n\t" + str(e)
                self.fail(msg)
            except Exception as e:
                msg = f"{klass} '{name}': " + str(e)
                self.fail(msg)

    def test_moduleinfo(self):
        for version in ["1", "2"]:
            with self.subTest(version=version):
                self.check_moduleinfo(version)
