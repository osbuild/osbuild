import json
import os
from unittest.mock import patch

from osbuild import inputs
from osbuild.util.jsoncomm import FdSet


class FakeInputService(inputs.InputService):
    def __init__(self, args):  # pylint: disable=super-init-not-called
        # do not call "super().__init__()" here to make it testable
        self.map_calls = []

    def map(self, _store, origin, refs, target, options):
        self.map_calls.append([origin, refs, target, options])
        return "complex", 2, "reply"


def test_inputs_dispatches_map(tmp_path):
    store_api_path = tmp_path / "api-store"
    store_api_path.write_text("")

    args_path = tmp_path / "args"
    reply_path = tmp_path / "reply"
    args = {
        "api": {
            "store": os.fspath(store_api_path),
        },
        "origin": "some-origin",
        "refs": "some-refs",
        "target": "some-target",
        "options": "some-options",
    }
    args_path.write_text(json.dumps(args))
    reply_path.write_text("")

    with args_path.open() as f_args, reply_path.open("w") as f_reply:
        fd_args, fd_reply = os.dup(f_args.fileno()), os.dup(f_reply.fileno())
        fds = FdSet.from_list([fd_args, fd_reply])
        fake_service = FakeInputService(args="some")
        with patch.object(inputs, "StoreClient"):
            r = fake_service.dispatch("map", None, fds)
            assert r == ('{}', None)
        assert fake_service.map_calls == [
            ["some-origin", "some-refs", "some-target", "some-options"],
        ]
    assert reply_path.read_text() == '["complex", 2, "reply"]'
