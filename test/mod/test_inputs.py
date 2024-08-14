import os
from unittest.mock import patch

from osbuild import host, inputs


class FakeInputService(inputs.InputService):
    def __init__(self, args):
        # do not call "super().__init__()" here to make it testable
        self._map_calls = []

    @host.callable_with_store
    def map(self, store, origin, refs, target, options):
        self._map_calls.append([origin, refs, target, options])
        return "complex", 2, "reply"


def test_inputs_dispatches_map(tmp_path):
    store_api_path = tmp_path / "api-store"
    store_api_path.write_text("")

    args = {
        "api": {
            "store": os.fspath(store_api_path),
        },
        "origin": "some-origin",
        "refs": "some-refs",
        "target": "some-target",
        "options": "some-options",
    }

    fake_service = FakeInputService(args="some")
    with patch.object(host, "StoreClient"):
        r = fake_service.dispatch("map", args, None)
    assert fake_service._map_calls == [
        ["some-origin", "some-refs", "some-target", "some-options"],
    ]
    assert r == (("complex", 2, "reply"), None)
