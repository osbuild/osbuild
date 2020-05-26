#
# Test Infrastructure
#

import contextlib
import errno
import json
import os
import subprocess
import sys
import tempfile

import osbuild
from osbuild.util import linux


class TestBase():
    """Base Class for Tests

    This class serves as base for our test infrastructure and provides access
    to common functionality.
    """

    @staticmethod
    def have_test_checkout() -> bool:
        """Check Test-Checkout Access

        Check whether the current test-run has access to a repository checkout
        of the project and tests. This is usually the guard around code that
        requires `locate_test_checkout()`.

        For now, we always require tests to be run from a checkout. Hence, this
        function will always return `True`. This might change in the future,
        though.
        """

        # Sanity test to verify we run from within a checkout.
        assert os.access("setup.py", os.R_OK)
        return True

    @staticmethod
    def locate_test_checkout() -> str:
        """Locate Test-Checkout Path

        This returns the path to the repository checkout we run against. This
        will fail if `have_test_checkout()` returns false.
        """

        assert TestBase.have_test_checkout()
        return os.getcwd()

    @staticmethod
    def have_test_data() -> bool:
        """Check Test-Data Access

        Check whether the current test-run has access to the test data. This
        data is required to run elaborate tests. If it is not available, those
        tests have to be skipped.

        Test data, unlike test code, is not shipped as part of the `test`
        python module, hence it needs to be located independently of the code.

        For now, we only support taking test-data from a checkout (see
        `locate_test_checkout()`). This might be extended in the future, though.
        """

        return TestBase.have_test_checkout()

    @staticmethod
    def locate_test_data() -> str:
        """Locate Test-Data Path

        This returns the path to the test-data directory. This will fail if
        `have_test_data()` returns false.
        """

        return os.path.join(TestBase.locate_test_checkout(), "test/data")

    @staticmethod
    def can_modify_immutable(path: str = "/var/tmp") -> bool:
        """Check Immutable-Flag Capability

        This checks whether the calling process is allowed to toggle the
        `FS_IMMUTABLE_FL` file flag. This is limited to `CAP_LINUX_IMMUTABLE`
        in the initial user-namespace. Therefore, only highly privileged
        processes can do this.

        There is no reliable way to check whether we can do this. The only
        possible check is to see whether we can temporarily toggle the flag
        or not. Since this is highly dependent on the file-system that file
        is on, you can optionally pass in the path where to test this. Since
        shmem/tmpfs on linux does not support this, the default is `/var/tmp`.
        """

        with tempfile.TemporaryFile(dir=path) as f:
            # First try whether `FS_IOC_GETFLAGS` is actually implemented
            # for the filesystem we test on. If it is not, lets assume we
            # cannot modify the flag and make callers skip their tests.
            try:
                b = linux.ioctl_get_immutable(f.fileno())
            except OSError as e:
                if e.errno in [errno.EACCES, errno.ENOTTY, errno.EPERM]:
                    return False
                raise

            # Verify temporary files are not marked immutable by default.
            assert not b

            # Try toggling the immutable flag. Make sure we always reset it
            # so the cleanup code can actually drop the temporary object.
            try:
                linux.ioctl_toggle_immutable(f.fileno(), True)
                linux.ioctl_toggle_immutable(f.fileno(), False)
            except OSError as e:
                if e.errno in [errno.EACCES, errno.EPERM]:
                    return False
                raise

        return True

    @staticmethod
    def have_rpm_ostree() -> bool:
        """Check rpm-ostree Availability

        This checks whether `rpm-ostree` is available in the current path and
        can be called by this process.
        """

        try:
            r = subprocess.run(["rpm-ostree", "--version"],
                               encoding="utf-8",
                               capture_output=True,
                               check=False)
        except FileNotFoundError:
            return False

        return r.returncode == 0 and "compose" in r.stdout

    @staticmethod
    def have_tree_diff() -> bool:
        """Check for tree-diff Tool

        Check whether the current test-run has access to the `tree-diff` tool.
        We currently use the one from a checkout, so it is available whenever
        a checkout is available.
        """

        return TestBase.have_test_checkout()

    @staticmethod
    def tree_diff(path1, path2):
        """Compare File-System Trees

        Run the `tree-diff` tool from the osbuild checkout. It produces a JSON
        output that describes the difference between 2 file-system trees.
        """

        checkout = TestBase.locate_test_checkout()
        output = subprocess.check_output([os.path.join(checkout, "tree-diff"), path1, path2])
        return json.loads(output)


class OSBuild(contextlib.AbstractContextManager):
    """OSBuild Executor

    This class represents a context to execute osbuild. It provides a context
    manager, which while entered maintains a cache and output directory. This
    allows running pipelines against a common setup and tear everything down
    when exiting.
    """

    _unittest = None
    _cache_from = None

    _exitstack = None
    _cachedir = None
    _outputdir = None

    def __init__(self, unit_test, cache_from=None):
        self._unittest = unit_test
        self._cache_from = cache_from

    def __enter__(self):
        self._exitstack = contextlib.ExitStack()
        with self._exitstack:
            # Create a temporary cache-directory. Optionally initialize it from
            # the cache specified by the caller.
            # Support for `cache_from` should be dropped once our cache allows
            # parallel writes. For now, this allows initializing test-runs with
            # a prepopulated cache for faster testing.
            cache = tempfile.TemporaryDirectory(dir="/var/tmp")
            self._cachedir = self._exitstack.enter_context(cache)
            if self._cache_from is not None:
                subprocess.run(["cp", "--reflink=auto", "-a",
                                os.path.join(self._cache_from, "."),
                                self._cachedir],
                               check=True)

            # Create a temporary output-directors for assembled artifacts.
            output = tempfile.TemporaryDirectory(dir="/var/tmp")
            self._outputdir = self._exitstack.enter_context(output)

            # Keep our ExitStack for `__exit__()`.
            self._exitstack = self._exitstack.pop_all()

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        # Clean up our ExitStack.
        with self._exitstack:
            pass

        self._outputdir = None
        self._cachedir = None
        self._exitstack = None

    def _print_result(self, code, data_stdout, data_stderr):
        print(f"osbuild failed with: {code}")
        try:
            json_stdout = json.loads(data_stdout)
            print("-- STDOUT (json) -----------------------")
            json.dump(json_stdout, sys.stdout, indent=2)
        except json.JSONDecodeError:
            print("-- STDOUT (raw) ------------------------")
            print(data_stdout)
        print("-- STDERR ------------------------------")
        print(data_stderr)
        print("-- END ---------------------------------")

    def compile(self, data_stdin, checkpoints=None):
        """Compile an Artifact

        This takes a manifest as `data_stdin`, executes the pipeline, and
        assembles the artifact. No intermediate steps are kept, unless you
        provide suitable checkpoints.

        The produced artifact (if any) is stored in the output directory. Use
        `map_output()` to temporarily map the file and get access. Note that
        the output directory becomes invalid when you leave the context-manager
        of this class.
        """

        cmd_args = []

        cmd_args += ["--json"]
        cmd_args += ["--libdir", "."]
        cmd_args += ["--output-directory", self._outputdir]
        cmd_args += ["--store", self._cachedir]

        for c in (checkpoints or []):
            cmd_args += ["--checkpoint", c]

        # Spawn the `osbuild` executable, feed it the specified data on
        # `STDIN` and wait for completion. If we are interrupted, we always
        # wait for `osbuild` to shut down, so we can clean up its file-system
        # trees (they would trigger `EBUSY` if we didn't wait).
        try:
            p = subprocess.Popen(
                    ["python3", "-m", "osbuild"] + cmd_args + ["-"],
                    encoding="utf-8",
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
            )
            data_stdout, data_stderr = p.communicate(data_stdin)
        except KeyboardInterrupt:
            p.wait()
            raise

        # If execution failed, print results to `STDOUT`.
        if p.returncode != 0:
            self._print_result(p.returncode, data_stdout, data_stderr)
            self._unittest.assertEqual(p.returncode, 0)

    def compile_file(self, file_stdin, checkpoints=None):
        """Compile an Artifact

        This is similar to `compile()` but takes a file-path instead of raw
        data. This will read the specified file into memory and then pass it
        to `compile()`.
        """

        with open(file_stdin, "r") as f:
            data_stdin = f.read()
            return self.compile(data_stdin, checkpoints=checkpoints)

    def treeid_from_manifest(self, manifest_data):
        """Calculate Tree ID

        This takes an in-memory manifest, inspects it, and returns the ID of
        the final tree of the stage-array. This returns `None` if no stages
        are defined.
        """

        manifest_json = json.loads(manifest_data)
        manifest_pipeline = manifest_json.get("pipeline", {})
        manifest_sources = manifest_json.get("sources", {})

        manifest_parsed = osbuild.load(manifest_pipeline, manifest_sources)
        return manifest_parsed.tree_id

    @contextlib.contextmanager
    def map_object(self, obj):
        """Temporarily Map an Intermediate Object

        This takes a cache-reference as input, looks it up in the current cache
        and provides the file-path to this object back to the caller.
        """

        path = os.path.join(self._cachedir, "refs", obj)
        assert os.access(path, os.R_OK)

        # Yield the path to the cache-entry to the caller. This is implemented
        # as a context-manager so the caller does not retain the path for
        # later access.
        yield path

    @contextlib.contextmanager
    def map_output(self, filename):
        """Temporarily Map an Output Object

        This takes a filename (or relative path) and looks it up in the output
        directory. It then provides the absolute path to that file back to the
        caller.
        """

        path = os.path.join(self._outputdir, filename)
        assert os.access(path, os.R_OK)

        # Similar to `map_object()` we provide the path through a
        # context-manager so the caller does not retain the path.
        yield path
