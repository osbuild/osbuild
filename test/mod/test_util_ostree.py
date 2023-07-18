#
# Tests for the 'osbuild.util.ostree' module.
#

import io
import json
import os
import subprocess
import tempfile
import unittest

import pytest

from osbuild.util import ostree

from .. import test


def run(*args, check=True, encoding="utf8", **kwargs):
    res = subprocess.run(*args,
                         encoding=encoding,
                         check=check,
                         **kwargs)
    return res


class TestObjectStore(test.TestBase):

    # pylint: disable=no-self-use
    @unittest.skipUnless(test.TestBase.have_rpm_ostree(), "rpm-ostree missing")
    def test_treefile_empty(self):
        # check we produce a valid treefile from an empty object
        tf = ostree.Treefile()

        with tf.as_tmp_file() as f:
            run(["rpm-ostree", "compose", "tree", "--print-only", f])

    def test_treefile_types(self):
        tf = ostree.Treefile()

        tf["repos"] = ["a", "b", "c"]    # valid list of strings
        tf["selinux"] = True             # valid boolean
        tf["ref"] = "ref/sample/tip"     # valid string

        with self.assertRaises(ValueError):
            tf["repos"] = "not a list"   # not a list

        with self.assertRaises(ValueError):
            tf["repos"] = [1, 2, 3]       # not a string list

        with self.assertRaises(ValueError):
            tf["selinux"] = "not a bool"  # not a boolean

    def test_treefile_dump(self):
        tf = ostree.Treefile()
        test_ref = "a/sample/ref"
        tf["ref"] = test_ref

        with tf.as_tmp_file() as path:
            with open(path, "r", encoding="utf8") as f:
                js = json.load(f)
                self.assertEqual(js["ref"], test_ref)
                self.assertEqual(tf["ref"], test_ref)

    @unittest.skipUnless(test.TestBase.have_rpm_ostree(), "rpm-ostree missing")
    def test_treefile_full(self):
        params = {
            "ref": "osbuild/ostree/devel",
            "repos": ["fedora", "osbuild"],
            "selinux": True,
            "boot-location": "new",
            "etc-group-members": ["wheel"],
            "machineid-compat": True
        }

        tf = ostree.Treefile()
        for p, v in params.items():
            tf[p] = v

        with tf.as_tmp_file() as path:
            r = run(["rpm-ostree",
                     "compose",
                     "tree",
                     "--print-only",
                     path],
                    stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)
            js = json.loads(r.stdout)

        for p, v in params.items():
            self.assertEqual(v, js[p])

    @unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
    @unittest.skipUnless(test.TestBase.have_rpm_ostree(), "rpm-ostree missing")
    def test_show_commit(self):
        repo_path = os.path.join(self.locate_test_data(), "sources/org.osbuild.ostree/data/repo")
        ostree.show(repo_path, "d6243b0d0ca3dc2aaef2e0eb3e9f1f4836512c2921007f124b285f7c466464d8")
        with pytest.raises(RuntimeError):
            ostree.show(repo_path, "f000000000000000000000000DEADBEEF000000000000000000000000000000f")


class TestPasswdLike(unittest.TestCase):

    def test_merge_passwd(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            primary_file_lines = [
                "root:x:0:0:root:/root:/bin/bash\n",
                "bin:x:1:1:bin:/bin:/sbin/nologin\n",
                "daemon:x:2:2:daemon:/sbin:/sbin/nologin\n"
            ]
            secondary_file_lines = [
                "daemon:x:9:9:daemon:/sbin:/sbin/nologin\n"
                "lp:x:4:7:lp:/var/spool/lpd:/sbin/nologin\n",
                "sync:x:5:0:sync:/sbin:/bin/sync\n"
            ]
            result_file_lines = [
                "root:x:0:0:root:/root:/bin/bash\n",
                "bin:x:1:1:bin:/bin:/sbin/nologin\n",
                "daemon:x:2:2:daemon:/sbin:/sbin/nologin\n",
                "lp:x:4:7:lp:/var/spool/lpd:/sbin/nologin\n",
                "sync:x:5:0:sync:/sbin:/bin/sync\n"
            ]
            with open(os.path.join(tmpdir, "primary"), "w", encoding="utf8") as f:
                f.writelines(primary_file_lines)
            with open(os.path.join(tmpdir, "secondary"), "w", encoding="utf8") as f:
                f.writelines(secondary_file_lines)

            passwd = ostree.PasswdLike.from_file(os.path.join(tmpdir, "primary"))
            passwd.merge_with_file(os.path.join(tmpdir, "secondary"))
            passwd.dump_to_file(os.path.join(tmpdir, "result"))

            with open(os.path.join(tmpdir, "result"), "r", encoding="utf8") as f:
                self.assertEqual(sorted(f.readlines()), sorted(result_file_lines))

    def test_merge_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            primary_file_lines = [
                "root:x:0:\n",
                "bin:x:1:\n"
            ]
            secondary_file_lines = [
                "bin:x:4:\n",
                "daemon:x:2:\n"
            ]
            result_file_lines = [
                "root:x:0:\n",
                "bin:x:1:\n",
                "daemon:x:2:\n"
            ]
            with open(os.path.join(tmpdir, "primary"), "w", encoding="utf8") as f:
                f.writelines(primary_file_lines)
            with open(os.path.join(tmpdir, "secondary"), "w", encoding="utf8") as f:
                f.writelines(secondary_file_lines)

            passwd = ostree.PasswdLike.from_file(os.path.join(tmpdir, "primary"))
            passwd.merge_with_file(os.path.join(tmpdir, "secondary"))
            passwd.dump_to_file(os.path.join(tmpdir, "result"))

            with open(os.path.join(tmpdir, "result"), "r", encoding="utf8") as f:
                self.assertEqual(sorted(f.readlines()), sorted(result_file_lines))

    #pylint: disable=no-self-use
    def test_subids_cfg(self):
        with tempfile.TemporaryDirectory() as tmpdir:

            first = [
                "gicmo:100000:65536",
                "achilles:100000:65536",
                "ondrej:100000:65536"
            ]

            txt = io.StringIO("\n".join(first))

            subids = ostree.SubIdsDB()
            subids.read(txt)

            assert len(subids.db) == 3

            for name in ("gicmo", "achilles", "ondrej"):
                assert name in subids.db
                uid, count = subids.db[name]
                assert uid == "100000"
                assert count == "65536"

            second = [
                "gicmo:200000:1000",
                "tom:200000:1000",
                "lars:200000:1000"
            ]

            txt = io.StringIO("\n".join(second))
            subids.read(txt)

            assert len(subids.db) == 5

            for name in ("gicmo", "achilles", "tom", "lars"):
                assert name in subids.db

            for name in ("gicmo", "tom", "lars"):
                uid, count = subids.db[name]
                assert uid == "200000"
                assert count == "1000"

            file = os.path.join(tmpdir, "subuid")
            subids.write_to(file)

            check = ostree.SubIdsDB()
            check.read_from(file)

            assert subids.db == check.db
