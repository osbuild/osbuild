#
# Tests for the 'osbuild.util.testutil' module.
#
import os.path

from osbuild.testutil import make_fake_input_tree


def test_make_fake_tree(tmp_path):  # pylint: disable=unused-argument
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/fake-file-one": "Some content",
        "/second/fake-file-two": "Second content",
    })
    assert os.path.isdir(fake_input_tree)
    assert os.path.exists(os.path.join(fake_input_tree, "fake-file-one"))
    assert open(os.path.join(fake_input_tree, "fake-file-one"), encoding="utf8").read() == "Some content"
    assert os.path.exists(os.path.join(fake_input_tree, "second/fake-file-two"))
    assert open(os.path.join(fake_input_tree, "second/fake-file-two"), encoding="utf").read() == "Second content"
