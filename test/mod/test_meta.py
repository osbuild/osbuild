import osbuild
import osbuild.meta


def test_schema():
    schema = osbuild.meta.Schema(None)
    assert not schema

    schema = osbuild.meta.Schema({"type": "bool"})  # should be 'boolean'
    assert not schema.check().valid
    assert not schema

    schema = osbuild.meta.Schema({"type": "array", "minItems": 3})
    assert schema.check().valid
    assert schema

    res = schema.validate([1, 2])
    assert not res
    res = schema.validate([1, 2, 3])
    assert res
