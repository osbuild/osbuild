import json
import unittest
import subprocess

from osbuild.util import ostree


def run(*args, check=True, encoding="utf-8", **kwargs):
    res = subprocess.run(*args,
                         encoding=encoding,
                         check=check,
                         **kwargs)
    return res


def have_rpm_ostree():
    try:
        r = run(["rpm-ostree", "--version"],
                capture_output=True, check=False)
    except FileNotFoundError:
        return False
    return r.returncode == 0 and "compose" in r.stdout


class TestObjectStore(unittest.TestCase):

    # pylint: disable=no-self-use
    @unittest.skipIf(not have_rpm_ostree(), "rpm-ostree missing")
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
            with open(path, "r") as f:
                js = json.load(f)
                self.assertEqual(js["ref"], test_ref)
                self.assertEqual(tf["ref"], test_ref)

    @unittest.skipIf(not have_rpm_ostree(), "rpm-ostree missing")
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
                    capture_output=True)
            self.assertEqual(r.returncode, 0)
            js = json.loads(r.stdout)

        for p, v in params.items():
            self.assertEqual(v, js[p])


if __name__ == "__main__":
    unittest.main()
