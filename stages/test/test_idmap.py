#!/usr/bin/python3

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.idmap"


@pytest.mark.parametrize(
    "test_data",
    [
        {
            "items": {}
        },
        {
            "items": {
                "/var/test-1": [
                    "b:9999:0:10"
                ],
            }
        },
        {
            "items": {
                "/var/test-1": [
                    "u:9999:0:10"
                ],
            }
        },
        {
            "items": {
                "/var/test-1": [
                    "g:9999:0:10"
                ],
            }
        },
        {
            "items": {
                "/var/test-1": [
                    "9999:0:10"
                ],
            }
        },
        {
            "items": {
                "/var/test-1": [
                    "555:444:10"
                ],
            }
        },
        {
            "items": {
                "/var/test-1": [
                    "555:444:10", "g:9999:0:10", "u:8888:0:10"
                ],
            }
        },
    ],
)
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_good(stage_schema, test_data):
    test_input = {
        "name": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        # Missing slash as first character
        (
            {
                "items": {
                    "var/test-1": [],
                }
            },
            "does not match any of the regexes:",
        ),
        # Invalid idmap 1 - 9 instead of g
        (
            {
                "items": {
                    "/var/test-1": [
                        "9:9999:0:10"
                    ],
                }
            },
            "does not match '^(?:(?:u|g|b):)?[0-9]+:[0-9]+:[1-9][0-9]*$'",
        ),
        # Invalid idmap 3 - empty idmap
        (
            {
                "items": {
                    "/var/test-1": [
                        ""
                    ],
                }
            },
            "does not match '^(?:(?:u|g|b):)?[0-9]+:[0-9]+:[1-9][0-9]*$'",
        ),
        # Invalid idmap 4 - empty idmap
        (
            {
                "items": {
                    "/var/test-1": [
                        "blobb:1000:0:1"
                    ],
                }
            },
            "does not match '^(?:(?:u|g|b):)?[0-9]+:[0-9]+:[1-9][0-9]*$'",
        ),
        # Invalid idmap 5 - negative values
        (
            {
                "items": {
                    "/var/test-1": [
                        "blobb:1000:0:-1"
                    ],
                }
            },
            "does not match '^(?:(?:u|g|b):)?[0-9]+:[0-9]+:[1-9][0-9]*$'",
        )
    ],
)
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_bad(stage_schema, test_data, expected_err):
    test_input = {
        "name": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.parametrize(
    # The same order in idmap_inputs and expected_ is assumed by the test
    # which needs to be taken into account writing the test data
    "idmap_inputs,expected_uid_maps,expected_gid_maps", [
        ([], [], []),
        (["u:1000:0:10"], [(1000, 0, 10)], []),
        (["g:1000:0:10"], [], [(1000, 0, 10)]),
        (["b:1000:0:10"], [(1000, 0, 10)], [(1000, 0, 10)]),
        (["1000:0:10"], [(1000, 0, 10)], [(1000, 0, 10)]),
        (["b:1000:0:10", "u:1020:20:10"], [(1000, 0, 10), (1020, 20, 10)], [(1000, 0, 10)]),
    ]
)
def test_idmaps_from_list_good(stage_module, idmap_inputs, expected_uid_maps, expected_gid_maps):
    mappings = stage_module.IDMap.from_list(idmap_inputs)

    user_mappings = mappings[stage_module.IDType.USER]
    assert len(user_mappings) == len(expected_uid_maps)
    for i, umap in enumerate(user_mappings):
        expected = expected_uid_maps[i]

        assert umap.inside == expected[0], f"Inside value: Expected {expected[0]}, got {umap.inside}"
        assert umap.outside == expected[1], f"Outside value: Expected {expected[1]}, got {umap.outside}"
        assert umap.size == expected[2], f"Size value: Expected {expected[2]}, got {umap.size}"

    group_mappings = mappings[stage_module.IDType.GROUP]
    assert len(group_mappings) == len(expected_gid_maps)
    for i, gmap in enumerate(group_mappings):
        expected = expected_gid_maps[i]

        assert gmap.inside == expected[0], f"Inside value: Expected {expected[0]}, got {gmap.inside}"
        assert gmap.outside == expected[1], f"Outside value: Expected {expected[1]}, got {gmap.outside}"
        assert gmap.size == expected[2], f"Size value: Expected {expected[2]}, got {gmap.size}"


@pytest.mark.parametrize(
    "idmap_inputs", [
        ([""]),
        (["x:100:0:10"]),
        (["u:100:0:10", "u1000:0:10"]),
        (["u:-100:0:10"]),
    ]
)
def test_idmaps_from_list_bad(stage_module, idmap_inputs):
    with pytest.raises(ValueError):
        stage_module.IDMap.from_list(idmap_inputs)


@pytest.mark.parametrize(
    "fuid,fgid,idmap_inputs,expected", [
        (0, 0, ["u:1000:0:10"], (1000, 0)),
        (0, 0, ["g:1000:0:10"], (0, 1000)),
        (0, 0, ["b:1000:0:10"], (1000, 1000)),
        (0, 0, ["1000:0:10"], (1000, 1000)),
        (3, 3, ["b:1000:0:10"], (1003, 1003)),
        (11, 11, ["b:1000:0:10"], (65534, 65534)),
    ]
)
def test_determine_new_ids(stage_module, fuid, fgid, idmap_inputs, expected):
    idmaps = stage_module.IDMap.from_list(idmap_inputs)

    new_ids = stage_module.determine_new_ids(fuid, fgid, idmaps)
    assert new_ids == expected
