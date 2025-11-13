"""Common fixtures and utilities"""


def assert_object_equal(obj1, obj2):
    """
    Assert that two objects are equal.

    If the objects are not equal, print the differences.
    """
    assert isinstance(obj1, type(obj2)), f"Objects are not of the same type: {type(obj1)} != {type(obj2)}"
    if obj1 != obj2:
        differences = []
        all_keys = set(vars(obj1).keys()) | set(vars(obj2).keys())
        for key in sorted(all_keys):
            val1 = vars(obj1).get(key)
            val2 = vars(obj2).get(key)
            if val1 != val2:
                differences.append(f"  {key}:")
                differences.append(f"    OBJ1: {val1!r}")
                differences.append(f"    OBJ2: {val2!r}")
        assert False, "Objects are not equal:\n" + "\n".join(differences)
