#!/usr/bin/python3

import os
import re

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.chrony"


default_config = """\
pool 2.fedora.pool.ntp.org iburst
sourcedir /run/chrony-dhcp
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
ntsdumpdir /var/lib/chrony
leapseclist /usr/share/zoneinfo/leap-seconds.list
logdir /var/log/chrony
leapsectz right/UTC"""


# stage options where all properties are used
all_options = {
    "timeservers": [
        "ntp1.example.com",
        "ntp2.example.com"
    ],
    "servers": [
        {
            "hostname": "ntp3.example.com",
            "prefer": True,
            "minpoll": 4,
            "maxpoll": 4
        },
        {
            "hostname": "ntp4.example.com",
            "iburst": False,
            "minpoll": 5,
            "maxpoll": 5
        }
    ],
    "leapsectz": "",
    "refclocks": [
        {
            "driver": {
                "name": "PPS",
                "device": "/dev/pps42",
                "clear": True
            },
            "poll": 1,
            "dpoll": 2,
            "offset": 0.3
        },
        {
            "driver": {
                "name": "SHM",
                "segment": 42,
                "perm": "0660"
            },
            "poll": 3,
            "dpoll": 4,
            "offset": 0.4
        },
        {
            "driver": {
                "name": "SOCK",
                "path": "/run/time/thingie.socket"
            },
            "poll": 5,
            "dpoll": 7,
            "offset": 0.1
        },
        {
            "driver": {
                "name": "PHC",
                "path": "/dev/ptp11",
                "nocrossts": True,
                "extpps": True,
                "pin": 3,
                "channel": 4,
                "clear": True
            },
            "poll": 9,
            "dpoll": 10,
            "offset": 0.2
        }
    ]
}

all_options_conf = {  # we don't really care about the order of the lines
    # timeservers
    "server ntp1.example.com iburst",
    "server ntp2.example.com iburst",

    # servers
    "server ntp3.example.com prefer iburst minpoll 4 maxpoll 4",
    "server ntp4.example.com minpoll 5 maxpoll 5",

    "refclock PPS /dev/pps42:clear poll 1 dpoll 2 offset 0.3",
    # refclocks
    "refclock SHM 42:perm=0660 poll 3 dpoll 4 offset 0.4",
    "refclock SOCK /run/time/thingie.socket poll 5 dpoll 7 offset 0.1",
    "refclock PHC /dev/ptp11:nocrossts,extpps,pin=3,channel=4,clear poll 9 dpoll 10 offset 0.2",

    # the original config lines that weren't overwritten or removed
    # note that leapsectz is removed
    "sourcedir /run/chrony-dhcp",
    "driftfile /var/lib/chrony/drift",
    "makestep 1.0 3",
    "rtcsync",
    "ntsdumpdir /var/lib/chrony",
    "leapseclist /usr/share/zoneinfo/leap-seconds.list",
    "logdir /var/log/chrony",
}


timeservers = {
    "timeservers": [
        "ntp1.example.com",
        "ntp2.example.com"
    ],
}


servers_and_leap = {
    "servers": [
        {
            "hostname": "ntp3.example.com",
            "prefer": True,
            "minpoll": 4,
            "maxpoll": 4
        },
        {
            "hostname": "ntp4.example.com",
            "iburst": False,
            "minpoll": 5,
            "maxpoll": 6
        }
    ],
    "leapsectz": ""
}


@pytest.mark.parametrize("test_data,expected_errs", [
    # everything
    (
        all_options,
        "",
    ),

    # only timeservers
    (
        timeservers,
        "",
    ),

    # servers + leapsectz
    (
        servers_and_leap,
        ""
    ),

    # bad refclock driver
    (
        {
            "refclocks": [
                {
                    "driver": {
                        "name": "invalid",
                        "device": "/dev/pps42",
                        "clear": True
                    },
                    "poll": 1,
                    "dpoll": 2,
                    "offset": 0.3
                },
            ],
        },
        ["is not valid under any of the given schemas"]
    ),

    # nothing (bad)
    (
        {},
        # under py3.6 the message is
        #   {} does not have enough properties
        # under other versions the message is
        #   {} should be non-empty
        [re.compile(r"{} should be non-empty|{} does not have enough properties")]
    ),

    # pattern violations
    (
        {
            "refclocks": [
                {
                    "driver": {
                        "name": "PPS",
                        "device": "not-a-path",
                    },
                },
                {
                    "driver": {
                        "name": "SHM",
                        "segment": 41,
                        "perm": "a660"
                    },
                },
                {
                    "driver": {
                        "name": "SOCK",
                        "path": "/../bad"
                    },
                },
                {
                    "driver": {
                        "name": "PHC",
                        "path": "/dots/../root",
                    },
                }
            ]
        },
        [
            "{'name': 'PPS', 'device': 'not-a-path'} is not valid under any of the given schemas",
            "{'name': 'SHM', 'segment': 41, 'perm': 'a660'} is not valid under any of the given schemas",
            "{'name': 'SOCK', 'path': '/../bad'} is not valid under any of the given schemas",
            "{'name': 'PHC', 'path': '/dots/../root'} is not valid under any of the given schemas",
        ]
    )
])
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation(stage_schema, test_data, expected_errs):
    test_input = {
        "name": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    for expected_err in expected_errs:
        if expected_err == "":
            assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
        else:
            assert res.valid is False
            testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=len(expected_errs))


@pytest.mark.parametrize("options,expected_contents", [
    (all_options, all_options_conf),
    (
        timeservers,
        {
            "server ntp1.example.com iburst",
            "server ntp2.example.com iburst",

            # the original config lines that weren't overwritten or removed
            "sourcedir /run/chrony-dhcp",
            "driftfile /var/lib/chrony/drift",
            "makestep 1.0 3",
            "rtcsync",
            "ntsdumpdir /var/lib/chrony",
            "leapsectz right/UTC",
            "leapseclist /usr/share/zoneinfo/leap-seconds.list",
            "logdir /var/log/chrony",
        },
    ),
    (
        servers_and_leap,
        {
            "server ntp3.example.com prefer iburst minpoll 4 maxpoll 4",
            "server ntp4.example.com minpoll 5 maxpoll 6",

            # the original config lines that weren't overwritten or removed
            "sourcedir /run/chrony-dhcp",
            "driftfile /var/lib/chrony/drift",
            "makestep 1.0 3",
            "rtcsync",
            "ntsdumpdir /var/lib/chrony",
            "leapseclist /usr/share/zoneinfo/leap-seconds.list",
            "logdir /var/log/chrony",
        },
    ),
])
def test_chrony_conf_contents(tmp_path, stage_module, options, expected_contents):
    chrony_conf_path = "etc/chrony.conf"
    testutil.make_fake_tree(tmp_path, {
        chrony_conf_path: default_config,
    })

    stage_module.main(tmp_path, options)
    with open(os.path.join(tmp_path, chrony_conf_path), encoding="utf-8") as chrony_conf:
        assert set(chrony_conf.read().split("\n")) == expected_contents
