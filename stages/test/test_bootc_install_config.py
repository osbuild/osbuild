import os.path
import re

import pytest

from osbuild import testutil
from osbuild.util import toml

STAGE_NAME = "org.osbuild.bootc.install.config"


@pytest.mark.parametrize(
    "options,expected_config",
    [
        (
            {
                "filename": "10-ten.conf",
                "config": {
                    "install": {
                        "filesystem": {
                            "root": {
                                "type": "xfs",
                            }
                        }
                    }
                }
            },
            {
                "install": {
                    "filesystem": {
                        "root": {
                            "type": "xfs"
                        }
                    }
                }
            },
        ),
        (
            {
                "filename": "20-twenty.conf",
                "config": {
                    "install": {
                        "kargs": [
                            "ro",
                            "biosdevname=0",
                            "net.ifnames=0",
                        ]
                    }
                }
            },
            {
                "install": {
                    "kargs": ["ro", "biosdevname=0", "net.ifnames=0"],
                }
            },
        ),
        (
            {
                "filename": "error.conf",
                "config": {
                    "install": {
                        "block": [
                            "tmp2-luks",
                        ],
                    }
                },
            },
            {
                "install": {
                    "block": ["tmp2-luks"]
                }
            }
        )
    ]
)
def test_bootc_install_config(tmp_path, stage_module, options, expected_config):
    stage_module.main(tmp_path, options)
    # different toml libraries write out arrays in different ways (one line vs many), so we need to parse the result
    # to compare
    config_data = toml.load_from_file(os.path.join(tmp_path, "usr/lib/bootc/install", options["filename"]))
    assert config_data == expected_config


@pytest.mark.parametrize(
    "options,expected_errors",
    [
        (
            {},
            ["'config' is a required property", "'filename' is a required property"]
        ),
        (
            {
                "filename": "error.conf",
            },
            ["'config' is a required property"]
        ),
        (
            {
                "filename": "error.conf",
                "config": {},
            },
            # under py3.6 the message is
            #   {} does not have enough properties
            # under other versions the message is
            #   {} should be non-empty
            [re.compile(r"{} should be non-empty|{} does not have enough properties")]
        ),
        (
            {
                "filename": "error.conf",
                "config": {
                    "install": {}
                },
            },
            [re.compile(r"{} should be non-empty|{} does not have enough properties")]
        ),
        (
            {
                "filename": "error.conf",
                "config": {
                    "install": {
                        "filesystem": {}
                    }
                },
            },
            ["'root' is a required property"]
        ),
        (
            {
                "filename": "error.conf",
                "config": {
                    "install": {
                        "filesystem": {
                            "root": {}
                        }
                    }
                },
            },
            ["'type' is a required property"]
        ),
        (
            {
                "filename": "error.conf",
                "config": {
                    "install": {
                        "block": [
                            "whatever",
                        ],
                    }
                },
            },
            ["'whatever' is not one of ['direct', 'tmp2-luks']"]
        ),
    ]
)
def test_schema_bootc_install_config(stage_schema, options, expected_errors):
    test_input = {
        "type": STAGE_NAME,
        "options": options,
    }
    res = stage_schema.validate(test_input)
    assert res.valid is False
    for err in expected_errors:
        testutil.assert_jsonschema_error_contains(res, err)
