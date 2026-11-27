import pytest

STAGE_NAME = "org.osbuild.concat"


@pytest.mark.parametrize("options, expected_error_paths", [
    ({"filename": "combined", "files": ["input://first/archive", "input://second/archive"]}, []),
    ({"filename": "combined", "files": ["input://first/archive"], "alignment": 4}, []),
    ({"filename": "combined", "files": ["input://first/archive"], "alignment": 0}, [".options.alignment"]),
    ({"filename": "combined", "files": []}, [".options.files"]),
    ({"filename": "combined", "files": ["tree:///archive"]}, [".options.files[0]"]),
    ({"filename": "combined"}, [".options"]),
])
def test_concat_schema(stage_schema, options, expected_error_paths):
    result = stage_schema.validate({"type": STAGE_NAME, "options": options})
    assert [error.id for error in result] == expected_error_paths, result.as_dict()


@pytest.mark.parametrize("alignment, second_data, expected", [
    (None, b"B\x80", b"\xff\x00AB\x80"),
    (4, b"B\x80", b"\xff\x00A\x00B\x80"),
    (4, b"", b"\xff\x00A\x00"),
])
def test_concat(tmp_path, stage_module, alignment, second_data, expected):
    tree = tmp_path / "tree"
    first = tmp_path / "first"
    second = tmp_path / "second"
    for directory in (tree, first, second):
        directory.mkdir()

    (first / "archive").write_bytes(b"\xff\x00A")
    (second / "archive").write_bytes(second_data)
    options = {
        "filename": "/combined",
        "files": ["input://first/archive", "input://second/archive"],
    }
    if alignment is not None:
        options["alignment"] = alignment

    args = {
        "tree": tree,
        "inputs": {"second": {"path": second}, "first": {"path": first}},
        "options": options,
    }
    assert stage_module.main(args) == 0
    assert (tree / "combined").read_bytes() == expected
