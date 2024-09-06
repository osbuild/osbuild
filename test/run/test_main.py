import json

import pytest

from .. import test

jsondata = json.dumps({
    "version": "2",
    "pipelines": [
        {
            "name": "noop",
        },
        {
            "name": "noop2",
        },
    ],
})


def test_exports_are_shown_on_missing_exports(capsys):
    with pytest.raises(AssertionError):
        with test.OSBuild() as osb:
            osb.compile(jsondata, exports=["not-existing"])
    assert "Export not-existing not found in ['noop', 'noop2']\n" in capsys.readouterr().out
