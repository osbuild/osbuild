#!/usr/bin/python3

STAGE_NAME = "org.osbuild.insights-client.config"

CONF_FILE = """[insights-client]
# Example options in this file are the defaults

# Change log level, valid options DEBUG, INFO, WARNING, ERROR, CRITICAL. Default DEBUG
#loglevel=DEBUG

# Attempt to auto configure with Satellite server
#auto_config=True

# URL for your proxy.  Example: http://user:pass@192.168.100.50:8080
#proxy=
"""


def test_insights_client_conf(tmp_path, stage_module):
    tree = tmp_path / "tree"
    path = tree / "etc/insights-client/"
    path.mkdir(parents=True)

    options = {
        "config": {
            "proxy": "test-proxy"
        }
    }
    stage_module.main(tree, options)

    with open(path / "insights-client.conf", 'r', encoding="utf8") as f:
        proxy = f.readline()
        expected_proxy = options["config"]["proxy"]
        expected = f"proxy={expected_proxy}\n"
        assert proxy == expected


def test_insights_client_conf_already_exists(tmp_path, stage_module):
    tree = tmp_path / "tree"
    path = tree / "etc/insights-client/"
    path.mkdir(parents=True)

    with open(path / "insights-client.conf", "w", encoding="utf8") as f:
        f.write(CONF_FILE)

    options = {
        "config": {
            "proxy": "test-proxy"
        }
    }
    stage_module.main(tree, options)

    with open(path / "insights-client.conf", 'r', encoding="utf8") as f:
        expected_proxy = options["config"]["proxy"]
        expected = f"proxy={expected_proxy}\n"
        assert expected in f.read()
