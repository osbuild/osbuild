#
# Tests for the 'osbuild.util.testutil' module.
#
import os.path

from osbuild.testutil import make_fake_input_tree, make_fake_tree

TEST_INPUT_TREE = {
    "/fake-file-one": "Some content",
    "/second/fake-file-two": "Second content",
}


def validate_test_input_tree(fake_input_tree):
    assert os.path.isdir(fake_input_tree)
    assert os.path.exists(os.path.join(fake_input_tree, "fake-file-one"))
    assert open(os.path.join(fake_input_tree, "fake-file-one"), encoding="utf8").read() == "Some content"
    assert os.path.exists(os.path.join(fake_input_tree, "second/fake-file-two"))
    assert open(os.path.join(fake_input_tree, "second/fake-file-two"), encoding="utf8").read() == "Second content"


def test_make_fake_tree(tmp_path):
    make_fake_tree(tmp_path, TEST_INPUT_TREE)
    validate_test_input_tree(tmp_path)


def test_make_fake_input_tree(tmp_path):
    # make_fake_input_tree is a convinience wrapper around make_fake_tree
    # for the osbuild input trees
    fake_input_tree = make_fake_input_tree(tmp_path, TEST_INPUT_TREE)
    assert fake_input_tree.endswith("/tree")
    validate_test_input_tree(fake_input_tree)
