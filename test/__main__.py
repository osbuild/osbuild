import argparse
import logging
import subprocess

from test.integration_tests import print_results_again
from test.integration_tests.test_case import IntegrationTestCase, IntegrationTestType
from test.integration_tests.config import *

logging.basicConfig(level=logging.getLevelName(os.environ.get("TESTS_LOGLEVEL", "INFO")))


def test_web_server_with_curl():
    cmd = ["curl", "-s", "http://127.0.0.1:8888/index"]
    logging.info(f"Running curl: {cmd}")
    curl = subprocess.run(cmd, capture_output=True)
    logging.info(f"Curl returned: code={curl.returncode}, stdout={curl.stdout.decode()}, stderr={curl.stderr.decode()}")
    assert curl.returncode == 0
    assert curl.stdout.decode("utf-8").strip() == "hello, world!"


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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run integration tests')
    parser.add_argument('--list', dest='list', action='store_true', help='list test cases')
    parser.add_argument('--build-pipeline', dest='build_pipeline', metavar='PIPELINE',
                        type=os.path.abspath, help='the build pipeline to run tests in')
    parser.add_argument('--case', dest='specific_case', metavar='TEST_CASE', help='run single test case')
    args = parser.parse_args()

    f30_boot = IntegrationTestCase(
        name="f30-boot",
        pipeline="f30-boot.json",
        build_pipeline=args.build_pipeline,
        output_image="f30-boot.qcow2",
        test_cases=[test_is_system_running],
        type=IntegrationTestType.BOOT_AND_CAPTURE_OUTPUT
    )
    web_server = IntegrationTestCase(
        name="web-server",
        pipeline="web-server.json",
        build_pipeline=args.build_pipeline,
        output_image="web-server.qcow2",
        test_cases=[test_web_server_with_curl],
        type=IntegrationTestType.BOOT_AND_WAIT
    )
    timezone = IntegrationTestCase(
        name="timezone",
        pipeline="timezone.json",
        build_pipeline=args.build_pipeline,
        output_image="timezone.tar.xz",
        test_cases=[test_timezone],
        type=IntegrationTestType.EXTRACT
    )
    firewall = IntegrationTestCase(
        name="firewall",
        pipeline="firewall.json",
        build_pipeline=args.build_pipeline,
        output_image="firewall.tar.xz",
        test_cases=[test_firewall],
        type=IntegrationTestType.EXTRACT
    )

    cases = [f30_boot, web_server, timezone, firewall]

    if args.list:
        print("Available test cases:")
        for case in cases:
            print(f" - {case.name}")
    else:
        logging.info(f"Using {OBJECTS} for objects storage.")
        logging.info(f"Using {OUTPUT_DIR} for output images storage.")
        logging.info(f"Using {OSBUILD} for building images.")

        if not args.specific_case:
            for case in cases:
                case.run()

            print_results_again()
        else:
            for case in cases:
                if case.name == args.specific_case:
                    case.run()

