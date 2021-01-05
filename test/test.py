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
import unittest

import osbuild.meta
from osbuild.formats import v1 as fmt
from osbuild.util import linux


class TestBase(unittest.TestCase):
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
    def can_bind_mount() -> bool:
        """Check Bind-Mount Capability

        Test whether we can bind-mount file-system objects. If yes, return
        `True`, otherwise return `False`.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            original = os.path.join(tmpdir, "original")
            mnt = os.path.join(tmpdir, "mnt")

            with open(original, "w") as f:
                f.write("foo")
            with open(mnt, "w") as f:
                f.write("bar")

            try:
                subprocess.run(
                    [
                        "mount",
                        "--make-private",
                        "-o",
                        "bind,ro",
                        original,
                        mnt,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                with open(mnt, "r") as f:
                    assert f.read() == "foo"
                return True
            except subprocess.CalledProcessError:
                return False
            finally:
                subprocess.run(
                    ["umount", mnt],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )

    @staticmethod
    def have_rpm_ostree() -> bool:
        """Check rpm-ostree Availability

        This checks whether `rpm-ostree` is available in the current path and
        can be called by this process.
        """

        try:
            r = subprocess.run(["rpm-ostree", "--version"],
                               encoding="utf-8",
                               stdout=subprocess.PIPE,
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
        output = subprocess.check_output([os.path.join(checkout, "tools/tree-diff"), path1, path2])
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

            # Keep our ExitStack for `__exit__()`.
            self._exitstack = self._exitstack.pop_all()

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        # Clean up our ExitStack.
        with self._exitstack:
            pass

        self._cachedir = None
        self._exitstack = None

    @staticmethod
    def _print_result(code, data_stdout, data_stderr):
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

    def compile(self, data_stdin, output_dir=None, checkpoints=None, check=False):
        """Compile an Artifact

        This takes a manifest as `data_stdin`, executes the pipeline, and
        assembles the artifact. No intermediate steps are kept, unless you
        provide suitable checkpoints.

        The produced artifact (if any) is stored in the directory passed via
        the output_dir parameter. If it's set to None, a temporary directory
        is used and thus the caller cannot access the built artifact.

        `check` determines what happens when running osbuild fails. If it is
        true, subprocess.CalledProcessError is raised. Otherwise, osbuild's
        output is printed to stdout and a test assertion is raised.

        Returns the build result as dictionary.
        """

        if output_dir is None:
            output_dir_context = tempfile.TemporaryDirectory(dir="/var/tmp")
        else:
            output_dir_context = contextlib.nullcontext(output_dir)

        with output_dir_context as osbuild_output_dir:
            cmd_args = ["python3", "-m", "osbuild"]

            cmd_args += ["--json"]
            cmd_args += ["--libdir", "."]
            cmd_args += ["--output-directory", osbuild_output_dir]
            cmd_args += ["--store", self._cachedir]

            for c in (checkpoints or []):
                cmd_args += ["--checkpoint", c]

            cmd_args += ["-"]

            # Spawn the `osbuild` executable, feed it the specified data on
            # `STDIN` and wait for completion. If we are interrupted, we always
            # wait for `osbuild` to shut down, so we can clean up its file-system
            # trees (they would trigger `EBUSY` if we didn't wait).
            try:
                p = subprocess.Popen(
                    cmd_args,
                    encoding="utf-8",
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                data_stdout, data_stderr = p.communicate(data_stdin)
            except KeyboardInterrupt:
                p.wait()
                raise

        # If execution failed, raise exception or print results to `STDOUT`.
        if p.returncode != 0:
            if check:
                raise subprocess.CalledProcessError(p.returncode, cmd_args, data_stdout, data_stderr)
            self._print_result(p.returncode, data_stdout, data_stderr)
            self._unittest.assertEqual(p.returncode, 0)

        return json.loads(data_stdout)

    def compile_file(self, file_stdin, output_dir=None, checkpoints=None):
        """Compile an Artifact

        This is similar to `compile()` but takes a file-path instead of raw
        data. This will read the specified file into memory and then pass it
        to `compile()`.
        """

        with open(file_stdin, "r") as f:
            data_stdin = f.read()
            return self.compile(data_stdin, output_dir, checkpoints=checkpoints)

    @staticmethod
    def treeid_from_manifest(manifest_data):
        """Calculate Tree ID

        This takes an in-memory manifest, inspects it, and returns the ID of
        the final tree of the stage-array. This returns `None` if no stages
        are defined.
        """

        index = osbuild.meta.Index(os.curdir)

        manifest_json = json.loads(manifest_data)

        manifest = fmt.load(manifest_json, index)
        tree_id, _ = fmt.get_ids(manifest)
        return tree_id

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

    def copy_source_data(self, target, source):
        """Copy the cached sources for a `source` to `target`

        This will copy all the downloaded data for a specified source
        to the `target` directory, with a folder structure in a way so
        it can be used to initialize the cache, via the constructor's
        `cache_from` argument. Does nothing if there is no downloaded
        data for the specified `source`.
        """
        from_path = os.path.join(self._cachedir, "sources", source)

        if not os.path.isdir(from_path):
            return

        to_path = os.path.join(target, "sources", source)
        os.makedirs(to_path, exist_ok=True)

        subprocess.run(["cp", "--reflink=auto", "-a",
                        os.path.join(from_path, "."),
                        to_path],
                       check=True)
