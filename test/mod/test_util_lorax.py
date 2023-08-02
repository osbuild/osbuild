#
# Basic checks for the lorax utility
#

import os
import subprocess
import tempfile

import osbuild.util.lorax as lorax

from .. import test

BASIC_TEMPLATE = """
# This is a comment
<%page args="tree, name"/>
mkdir dir-{a,b,c}
append test/check success
append a.txt "This is a text"
move a.txt dir-a
install /hello.txt dir-b
symlink dir-b/hello.txt hello-world.txt
runcmd touch ${tree}/foo.txt
append a.txt "@NAME@"
append b.txt "@NAME@"
replace @NAME@ ${name} *.txt
"""


class TestUtilLorax(test.TestBase):
    def assertExists(self, root, *paths):
        for path in paths:
            target = os.path.join(root, path.lstrip("/"))
            if not os.path.exists(target):
                self.fail(f"Path {target} does not exists")

    def test_script(self):
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            root = os.path.join(tmp, "root")
            tree = os.path.join(tmp, "tree")
            os.makedirs(root)
            os.makedirs(tree)

            with open(os.path.join(root, "hello.txt"), "w", encoding="utf8") as f:
                f.write("Hello World\n")

            self.assertExists(root, "hello.txt")

            template = os.path.join(tmp, "template.tmpl")
            with open(os.path.join(tmp, template), "w", encoding="utf8") as f:
                f.write(BASIC_TEMPLATE)

            # parse the template and render it
            args = {"tree": tree, "name": "osbuild-42"}

            tmpl = lorax.render_template(template, args)
            self.assertIsNotNone(tmpl)

            # run the script
            script = lorax.Script(tmpl, root, tree)
            script()

            # for debugging purposes

            subprocess.run(["ls", "-la", tree], check=True)
            # check the outcome
            self.assertExists(tree, "dir-a", "dir-b", "dir-c")
            self.assertExists(tree, "test/check")
            self.assertExists(tree, "dir-a/a.txt")
            self.assertExists(tree, "dir-b/hello.txt")
            self.assertExists(tree, "hello-world.txt")
            self.assertExists(tree, "foo.txt")

            for fn in ["a.txt", "b.txt"]:
                with open(os.path.join(tree, fn), "r", encoding="utf8") as f:
                    data = f.read().strip()
                    self.assertEqual(data, "osbuild-42")

    def test_script_errors(self):
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            root = os.path.join(tmp, "root")
            tree = os.path.join(tmp, "tree")
            os.makedirs(root)
            os.makedirs(tree)

            # file not found during `replace`
            tmpl = [["replace", "a", "b", "nonexist-file"]]
            script = lorax.Script(tmpl, root, tree)

            with self.assertRaises(AssertionError):
                script()

            # file not found during `install`
            tmpl = [["install", "nonexist-file", "foo"]]
            script = lorax.Script(tmpl, root, tree)

            with self.assertRaises(IOError):
                script()
