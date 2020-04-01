#
# Tests for the `osbuild.util.pathfd` module.
#


import os
import tempfile
import unittest

import osbuild.util.pathfd as pathfd


class TestUtilPathFd(unittest.TestCase):
    def setUp(self):
        #
        # Generic Test Setup
        #
        # We create a temporary directory tree for all tests. Each entry is
        # named after its own path (e.g., the file `2_2_0` is located at
        # `2/2_2/2_2_0`). This allows easy assertions on file-location and
        # availability.
        #
        # The tree we create looks like this:
        #
        #     0
        #     1
        #     2/
        #         2_0
        #         2_1
        #         2_2/
        #             2_2_0
        #             2_2_1
        #         2_3/
        #             2_3_0
        #             2_3_1
        #     3/
        #         3_0
        #         3_1
        #         3_2
        #         3_3
        #     4 -> "2"
        #     5 -> "2/2_3"
        #     6 -> "<invalid>"
        #

        self.dir = tempfile.TemporaryDirectory()
        self.dirfd = pathfd.PathFd.from_path(self.dir.name)

        flags = os.O_RDWR | os.O_CLOEXEC | os.O_CREAT | os.O_EXCL

        os.close(os.open("0", flags, dir_fd = int(self.dirfd)))
        os.close(os.open("1", flags, dir_fd = int(self.dirfd)))

        os.mkdir("2", dir_fd = int(self.dirfd))
        os.close(os.open("2/2_0", flags, dir_fd = int(self.dirfd)))
        os.close(os.open("2/2_1", flags, dir_fd = int(self.dirfd)))
        os.mkdir("2/2_2", dir_fd = int(self.dirfd))
        os.close(os.open("2/2_2/2_2_0", flags, dir_fd = int(self.dirfd)))
        os.close(os.open("2/2_2/2_2_1", flags, dir_fd = int(self.dirfd)))
        os.mkdir("2/2_3", dir_fd = int(self.dirfd))
        os.close(os.open("2/2_3/2_3_0", flags, dir_fd = int(self.dirfd)))
        os.close(os.open("2/2_3/2_3_1", flags, dir_fd = int(self.dirfd)))

        os.mkdir("3", dir_fd = int(self.dirfd))
        os.close(os.open("3/3_0", flags, dir_fd = int(self.dirfd)))
        os.close(os.open("3/3_1", flags, dir_fd = int(self.dirfd)))
        os.close(os.open("3/3_2", flags, dir_fd = int(self.dirfd)))
        os.close(os.open("3/3_3", flags, dir_fd = int(self.dirfd)))

        os.symlink("2", "4", dir_fd = int(self.dirfd))
        os.symlink("2/2_3", "5", dir_fd = int(self.dirfd))
        os.symlink("<invalid>", "6", dir_fd = int(self.dirfd))

    def tearDown(self):
        self.dirfd.close()
        self.dir.cleanup()

    def test_basic(self):
        #
        # Basic Tests
        #
        # This contains a bunch of hard-coded basic tests for the PathFd
        # module. Anything non-automated and small enough that it needs no
        # complex setup is bundled here.
        #

        # Verify basic constructors calls.
        _ = pathfd.PathFd()
        _ = pathfd.PathFd.from_path(self.dir.name)
        _ = self.dirfd.clone()

        # Verify int-conversion produces an accessible file-descriptor.
        fd = int(self.dirfd)
        assert fd >= 0
        dup = os.dup(fd)
        assert dup >= 0
        os.close(dup)

        # Verify context-manager operation.
        p = self.dirfd.clone()
        with p as v:
            assert int(p) == int(v)
        assert not p.is_open()

        # Verify close() does its job.
        p = self.dirfd.clone()
        assert int(p) >= 0
        p.close()
        try:
            assert int(p) >= 0
            raise SystemError
        except AssertionError:
            pass

        # Verify is_open() behavior.
        assert not pathfd.PathFd().is_open()
        p = self.dirfd.clone()
        assert p.is_open()
        p.close()
        assert not p.is_open()

        # Verify clones have their own private file-descriptor.
        p = self.dirfd.clone()
        assert int(p) != int(self.dirfd)

        # Verify stat() works just like `os.stat()`.
        assert self.dirfd.stat() == os.stat(self.dir.name)

        # Verify is_directory() works as intended.
        assert self.dirfd.descend(".").is_directory()
        assert not self.dirfd.descend("0").is_directory()
        assert not self.dirfd.descend("1").is_directory()
        assert self.dirfd.descend("2").is_directory()
        assert not self.dirfd.descend("2/2_0").is_directory()

        # Verify is_symlink() works as intended.
        assert not self.dirfd.descend(".").is_symlink()
        assert not self.dirfd.descend("0").is_symlink()
        assert not self.dirfd.descend("1").is_symlink()
        assert self.dirfd.descend("4").is_symlink()
        assert self.dirfd.descend("5").is_symlink()
        assert self.dirfd.descend("6").is_symlink()

        # Check for basic `open_relative()` behavior.
        _ = self.dirfd.open_relative("2/2_0", os.O_RDONLY)
        try:
            # '6' is a symlink to a non-existant file, so it cannot resolve
            _ = self.dirfd.open_relative("6", os.O_RDONLY)
            raise SystemError
        except OSError:
            pass
        try:
            # cannot open symlinks (which `O_NOFOLLOW` would try here)
            _ = self.dirfd.open_relative("4", os.O_RDONLY | os.O_NOFOLLOW)
            raise SystemError
        except OSError:
            pass
        _ = self.dirfd.open_relative("4", os.O_RDONLY)

        # Check for basic `open_self()` behavior.
        _ = self.dirfd.open_self(os.O_RDONLY)
        try:
            # `open_self()` rejects `O_NOFOLLOW`
            _ = self.dirfd.descend("4").open_self(os.O_RDONLY | os.O_NOFOLLOW)
            raise SystemError
        except AssertionError:
            pass

        # Check for basic `descend()` behavior.
        _ = self.dirfd.descend("0")
        _ = self.dirfd.descend("2")
        _ = self.dirfd.descend("2/2_0")
        _ = self.dirfd.descend("2/../2/./2_0")
        _ = self.dirfd.descend("2").descend("2_0")
        _ = self.dirfd.descend("4")
        _ = self.dirfd.descend("5", follow_symlink = True)
        try:
            _ = self.dirfd.descend("6", follow_symlink = True)
            raise SystemError
        except OSError:
            pass

    def test_enumerate(self):
        #
        # Directory Enumeration
        #
        # This contains tests for the `enumerate()` method of pathfd objects.
        # It defines an array of mappings from pathfd to the directory
        # listing. It then iterates over the mapping and verifies each
        # enumeration produces the expected listing.
        #

        mappings = []

        dirfd = self.dirfd.clone()
        expected = ["0", "1", "2", "3", "4", "5", "6"]
        mappings.append((dirfd, expected))

        dirfd = self.dirfd.descend("2/2_2")
        expected = ["2_2_0", "2_2_1"]
        mappings.append((dirfd, expected))

        dirfd = self.dirfd.descend("3")
        expected = ["3_0", "3_1", "3_2", "3_3"]
        mappings.append((dirfd, expected))

        for (dirfd, expected) in mappings:
            result = list(map(lambda x: x[1].name, dirfd.enumerate()))
            result.sort()
            expected.sort()
            assert result == expected

    def test_enumerate_unlink_race(self):
        #
        # Directory Enumeration vs Unlink
        #
        # This runs a directory enumeration, but unlinks an entry during the
        # enumeration. It verifies that the enumeration will not fall over, but
        # proceeds gracefully.
        #
        # We cannot affect the batch-size the `os.scandir()` call uses
        # internally. Therefore, we cannot really predict which path is taken.
        # All we can do is verify no exception is thrown.
        #

        with tempfile.TemporaryDirectory() as t_dir:
            t_dirfd = pathfd.PathFd.from_path(t_dir)
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_CREAT | os.O_EXCL
            os.close(os.open("0", flags, dir_fd = int(t_dirfd)))
            os.close(os.open("1", flags, dir_fd = int(t_dirfd)))
            os.close(os.open("2", flags, dir_fd = int(t_dirfd)))
            os.close(os.open("3", flags, dir_fd = int(t_dirfd)))
            os.close(os.open("4", flags, dir_fd = int(t_dirfd)))
            os.close(os.open("5", flags, dir_fd = int(t_dirfd)))
            os.close(os.open("6", flags, dir_fd = int(t_dirfd)))
            os.close(os.open("7", flags, dir_fd = int(t_dirfd)))

            t_entries = []
            t_enum = t_dirfd.enumerate()

            # Unlink '3' and '4'. This means they must not be returned from the
            # `next()` calls, but might be internally seen by `os.scandir()`.
            os.unlink("3", dir_fd = int(t_dirfd))
            os.unlink("4", dir_fd = int(t_dirfd))

            # Fetch the first entry, triggering a batched `os.scandir()`.
            t_entries.append(next(t_enum)[1].name)

            # Unlink more entries. Because ordering is random, one of these
            # might have been returned by the previous call, but we cannot
            # know. However, this can only apply to one of them. The other must
            # never be returned.
            os.unlink("0", dir_fd = int(t_dirfd))
            os.unlink("7", dir_fd = int(t_dirfd))

            t_entries += list(map(lambda x: x[1].name, t_enum))
            t_entries.sort()

            expected0 = ["0", "1", "2", "5", "6",    ]
            expected0.sort()
            expected1 = [     "1", "2", "5", "6", "7"]
            expected1.sort()
            expected2 = [     "1", "2", "5", "6",    ]
            expected2.sort()

            assert t_entries == expected0 or t_entries == expected1 or t_entries == expected2

    def test_traverse(self):
        #
        # Path Traversal
        #
        # This tests the recursive enumeration of a directory tree. It defines
        # a mapping from pathfd to the expected directory listing. It then
        # iterates the array and verifies each enumeration produces the
        # expected result.
        #
        # Note that the origin of a traversal is not itself yielded by the
        # traversal.
        #

        mappings = []

        dirfd = self.dirfd.clone()
        expected = []
        expected += ["0", "1"]
        expected += ["2", "2_0", "2_1"]
        expected += ["2_2", "2_2_0", "2_2_1"]
        expected += ["2_3", "2_3_0", "2_3_1"]
        expected += ["3", "3_0", "3_1", "3_2", "3_3"]
        expected += ["4", "5", "6"]
        mappings.append((dirfd, expected))

        dirfd = self.dirfd.descend("2")
        expected = []
        expected += ["2_0", "2_1"]
        expected += ["2_2", "2_2_0", "2_2_1"]
        expected += ["2_3", "2_3_0", "2_3_1"]
        mappings.append((dirfd, expected))

        dirfd = self.dirfd.descend("3")
        expected = ["3_0", "3_1", "3_2", "3_3"]
        mappings.append((dirfd, expected))

        for (dirfd, expected) in mappings:
            result = list(map(lambda x: x[1].name, dirfd.traverse()))
            result.sort()
            expected.sort()
            assert result == expected


if __name__ == "__main__":
    unittest.main()
