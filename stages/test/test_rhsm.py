#!/usr/bin/python3

import re

import pytest

from osbuild.testutil import (
    assert_jsonschema_error_contains,
)

STAGE_NAME = "org.osbuild.rhsm"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({
        "dnf-plugins": {
            "random": {
                "enabled": False,
            },
            "subscription-manager": {
                "enabled": False,
            },
        },
    }, r"Additional properties are not allowed \('random' was unexpected\)"),
    ({
        "dnf-plugins": {
            "product-id": {
                "enhanced": False,
            },
            "subscription-manager": {
                "enabled": False,
            },
        },
    }, r"Additional properties are not allowed \('enhanced' was unexpected\)"),
    ({
        "subscription-manager": {
            "rhsm": {
                "manage_repos": 45,
                "auto_enable_yum_plugins": False
            },
            "rhsmcertd": {
                "auto_registration": False,
            },
        }
    }, r"45 is not of type 'boolean'"),
    ({
        "subscription-manager": {
            "rhsm": {
                "random": False
            },
            "rhsmcertd": {
                "auto_registration": False,
            },
        }
    }, r"Additional properties are not allowed \('random' was unexpected\)"),
    ({
        "subscription-manager": {
            "random": {},
        }
    }, r"Additional properties are not allowed \('random' was unexpected\)"),
    ({
        "subscription-manager": {
            "rhsmcertd": {
                "random": False,
            },
        }
    }, r"Additional properties are not allowed \('random' was unexpected\)"),
    # good
    ({}, ""),
    ({
        "dnf-plugins": {},
        "yum-plugins": {},
        "subscription-manager": {},
    }, ""),
    ({
        "dnf-plugins": {
            "product-id": {
                "enabled": False,
            },
            "subscription-manager": {
                "enabled": False,
            },
        },
        "yum-plugins": {
            "product-id": {
                "enabled": False,
            },
            "subscription-manager": {
                "enabled": False,
            },
        },
        "subscription-manager": {
            "rhsm": {
                "manage_repos": False,
                "auto_enable_yum_plugins": False,
            },
            "rhsmcertd": {
                "auto_registration": False,
            },
        },
    }, ""),
    ({
        "dnf-plugins": {
            "product-id": {
                "enabled": True,
            },
            "subscription-manager": {
                "enabled": True,
            },
        },
        "yum-plugins": {
            "product-id": {
                "enabled": True,
            },
            "subscription-manager": {
                "enabled": True,
            },
        },
        "subscription-manager": {
            "rhsm": {
                "manage_repos": True,
                "auto_enable_yum_plugins": True,
            },
            "rhsmcertd": {
                "auto_registration": True,
            },
        },
    }, ""),
])
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        assert_jsonschema_error_contains(res, re.compile(expected_err), expected_num_errs=1)
