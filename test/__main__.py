import argparse
import logging
import subprocess
import os

from test.integration_tests.test_case import IntegrationTestCase, IntegrationTestType
from test.integration_tests.config import *

logging.basicConfig(level=logging.getLevelName(os.environ.get("TESTS_LOGLEVEL", "INFO")))


def test_is_system_running(result):
    assert result.strip() == "running"


def test_timezone(extract_dir):
    link = os.readlink(f"{extract_dir}/etc/localtime")
    assert "Europe/Prague" in link


def test_firewall(extract_dir):
    with open(f"{extract_dir}/etc/firewalld/zones/public.xml") as f:
        content = f.read()
        assert 'service name="http"' in content
        assert 'service name="ftp"' in content
        assert 'service name="telnet"' not in content
        assert 'port port="53" protocol="tcp"' in content
        assert 'port port="88" protocol="udp"' in content


def test_locale(extract_dir):
    with open(f"{extract_dir}/etc/locale.conf") as f:
        content = f.read()
        assert 'LANG=nn_NO.utf8' in content


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run integration tests')
    parser.add_argument('--list', dest='list', action='store_true', help='list test cases')
    parser.add_argument('--build-pipeline', dest='build_pipeline', metavar='PIPELINE',
                        type=os.path.abspath, help='the build pipeline to run tests in')
    parser.add_argument('--case', dest='specific_case', metavar='TEST_CASE', help='run single test case')
    args = parser.parse_args()

    logging.info(f"Using {OBJECTS} for objects storage.")
    logging.info(f"Using {OSBUILD} for building images.")

    timezone = IntegrationTestCase(
        name="timezone",
        pipeline="timezone.json",
        build_pipeline=args.build_pipeline,
        output_image="timezone.tar",
        test_cases=[test_timezone],
        type=IntegrationTestType.EXTRACT
    )
    firewall = IntegrationTestCase(
        name="firewall",
        pipeline="firewall.json",
        build_pipeline=args.build_pipeline,
        output_image="firewall.tar",
        test_cases=[test_firewall],
        type=IntegrationTestType.EXTRACT
    )
    locale = IntegrationTestCase(
        name="locale",
        pipeline="locale.json",
        build_pipeline=args.build_pipeline,
        output_image="locale.tar",
        test_cases=[test_locale],
        type=IntegrationTestType.EXTRACT
    )

    cases = [timezone, firewall, locale]

    if args.list:
        print("Available test cases:")
        for case in cases:
            print(f" - {case.name}")
    else:
        if not args.specific_case:
            for case in cases:
                case.run()
        else:
            for case in cases:
                if case.name == args.specific_case:
                    case.run()
