import collections
from typing import Dict, Iterable, Iterator, List, Optional

from .. import host
from ..objectstore import ObjectStore
from ..sources import Source
from .pipeline import Pipeline
from .runner import Runner
from .stage import BuildResult, Stage  # noqa: these are re-exported


class Manifest:
    """Representation of a pipeline and its sources"""

    def __init__(self):
        self.pipelines = collections.OrderedDict()
        self.sources = []

    def add_pipeline(
        self,
        name: str,
        runner: Runner,
        build: Optional[str] = None,
        source_epoch: Optional[int] = None
    ) -> Pipeline:
        pipeline = Pipeline(name, runner, build, source_epoch)
        if name in self.pipelines:
            raise ValueError(f"Name {name} already exists")
        self.pipelines[name] = pipeline
        return pipeline

    def add_source(self, info, items: List, options: Dict) -> Source:
        source = Source(info, items, options)
        self.sources.append(source)
        return source

    def download(self, store, monitor, libdir):
        with host.ServiceManager(monitor=monitor) as mgr:
            for source in self.sources:
                source.download(mgr, store, libdir)

    def depsolve(self, store: ObjectStore, targets: Iterable[str]) -> List[str]:
        """Return the list of pipelines that need to be built

        Given a list of target pipelines, return the names
        of all pipelines and their dependencies that are not
        already present in the store.
        """

        # A stack of pipelines to check if they need to be built
        check = list(map(self.get, targets))

        # The ordered result "set", will be reversed at the end
        build = collections.OrderedDict()

        while check:
            pl = check.pop()  # get the last(!) item

            if not pl:
                raise RuntimeError("Could not find pipeline.")

            if store.contains(pl.id):
                continue

            # The store does not have this pipeline, it needs to
            # be built, add it to the ordered result set and
            # ensure it is at the end, i.e. built before previously
            # checked items. NB: the result set is reversed before
            # it gets returned. This ensures that a dependency that
            # gets checked multiple times, like a build pipeline,
            # always gets built before its dependent pipeline.
            build[pl.id] = pl
            build.move_to_end(pl.id)

            # Add all dependencies to the stack of things to check,
            # starting with the build pipeline, if there is one
            if pl.build:
                check.append(self.get(pl.build))

            # Stages depend on other pipeline via pipeline inputs.
            # We check in reversed order until we hit a checkpoint
            for stage in reversed(pl.stages):

                # we stop if we have a checkpoint, i.e. we don't
                # need to build any stages after that checkpoint
                if store.contains(stage.id):
                    break

                pls = map(self.get, stage.dependencies)
                check.extend(pls)

        return list(map(lambda x: x.name, reversed(build.values())))

    def build(self, store, pipelines, monitor, libdir, stage_timeout=None):
        results = {"success": True}

        for pl in map(self.get, pipelines):
            res = pl.run(store, monitor, libdir, stage_timeout)
            results[pl.id] = res
            if not res["success"]:
                results["success"] = False
                return results

        return results

    def mark_checkpoints(self, checkpoints):
        points = set(checkpoints)

        def mark_stage(stage):
            c = stage.id
            if c in points:
                stage.checkpoint = True
                points.remove(c)

        def mark_pipeline(pl):
            if pl.name in points and pl.stages:
                pl.stages[-1].checkpoint = True
                points.remove(pl.name)

            for stage in pl.stages:
                mark_stage(stage)

        for pl in self.pipelines.values():
            mark_pipeline(pl)

        return points

    def get(self, name_or_id: str) -> Optional[Pipeline]:
        pl = self.pipelines.get(name_or_id)
        if pl:
            return pl
        for pl in self.pipelines.values():
            if pl.id == name_or_id:
                return pl
        return None

    def __contains__(self, name_or_id: str) -> bool:
        return self.get(name_or_id) is not None

    def __getitem__(self, name_or_id: str) -> Pipeline:
        pl = self.get(name_or_id)
        if pl:
            return pl
        raise KeyError(f"'{name_or_id}' not found")

    def __iter__(self) -> Iterator[Pipeline]:
        return iter(self.pipelines.values())
