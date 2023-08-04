import collections
from typing import List

from ..util import cleanup
from .runner import Runner
from .stage import Stage


class Pipeline:
    def __init__(self, name: str, runner: Runner, build=None, source_epoch=None):
        self.name = name
        self.build = build
        self.runner = runner
        self.stages: List[Stage] = []
        self.assembler = None
        self.source_epoch = source_epoch

    @property
    def id(self):
        """
        Pipeline id: corresponds to the `id` of the last stage

        In contrast to `name` this identifies the pipeline via
        the tree, i.e. the content, it produces. Therefore two
        pipelines that produce the same `tree`, i.e. have the
        same exact stages and build pipeline, will have the
        same `id`; thus the `id`, in contrast to `name` does
        not uniquely identify a pipeline.
        In case a Pipeline has no stages, its `id` is `None`.
        """
        return self.stages[-1].id if self.stages else None

    def add_stage(self, info, options, sources_options=None):
        stage = Stage(info, sources_options, self.build,
                      self.id, options or {}, self.source_epoch)
        self.stages.append(stage)
        if self.assembler:
            self.assembler.base = stage.id
        return stage

    def build_stages(self, object_store, monitor, libdir, stage_timeout=None):
        results = {"success": True}

        # If there are no stages, just return here
        if not self.stages:
            return results

        # Check if the tree that we are supposed to build does
        # already exist. If so, short-circuit here
        if object_store.contains(self.id):
            return results

        # We need a build tree for the stages below, which is either
        # another tree that needs to be built with the build pipeline
        # or the host file system if no build pipeline is specified
        # NB: the very last level of nested build pipelines is always
        # build on the host

        if not self.build:
            build_tree = object_store.host_tree
        else:
            build_tree = object_store.get(self.build)

        if not build_tree:
            raise AssertionError(f"build tree {self.build} not found")

        # Not in the store yet, need to actually build it, but maybe
        # an intermediate checkpoint exists: Find the last stage that
        # already exists in the store and use that as the base.
        tree = object_store.new(self.id)
        tree.source_epoch = self.source_epoch

        todo = collections.deque()
        for stage in reversed(self.stages):
            base = object_store.get(stage.id)
            if base:
                tree.init(base)
                break
            todo.append(stage)  # append right side of the deque

        # If two run() calls race each-other, two trees will get built
        # and it is nondeterministic which of them will end up
        # referenced by the `tree_id` in the content store if they are
        # both committed. However, after the call to commit all the
        # trees will be based on the winner.
        results["stages"] = []

        while todo:
            stage = todo.pop()

            monitor.stage(stage)

            r = stage.run(tree,
                          self.runner,
                          build_tree,
                          object_store,
                          monitor,
                          libdir,
                          stage_timeout)

            monitor.result(r)

            results["stages"].append(r)
            if not r.success:
                cleanup(build_tree, tree)
                results["success"] = False
                return results

            if stage.checkpoint:
                object_store.commit(tree, stage.id)

        tree.finalize()

        return results

    def run(self, store, monitor, libdir, stage_timeout=None):

        monitor.begin(self)

        results = self.build_stages(store,
                                    monitor,
                                    libdir,
                                    stage_timeout)

        monitor.finish(results)

        return results
