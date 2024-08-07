import os
from unittest.mock import call, patch

from osbuild import inputs


class FakeInputService(inputs.InputService):
    def __init__(self, args):  # pylint: disable=super-init-not-called
        # do not call "super().__init__()" here to make it testable
        self.map_calls = []

    def map(self, store, origin, refs, target, options):
        self.map_calls.append([origin, refs, target, options])
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
    with patch.object(inputs, "StoreClient") as mocked_store_client_klass:
        r = fake_service.dispatch("map", args, None)
    assert mocked_store_client_klass.call_args_list == [
        call(connect_to=os.fspath(store_api_path)),
    ]
    assert fake_service.map_calls == [
        ["some-origin", "some-refs", "some-target", "some-options"],
    ]
    assert r == (("complex", 2, "reply"), None)
