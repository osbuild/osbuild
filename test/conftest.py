unsupported_filesystems = []
"""Globally accessible list of filesystems that are unsupported on the system when running test cases"""


def pytest_addoption(parser):
    parser.addoption(
        "--unsupported-fs",
        action="append",
        default=[],
        metavar="FS",
        help="List of filesystems to treat as unsupported on the system when running test cases." +
             "Can be specified multiple times.",
    )


def pytest_configure(config):
    # pylint: disable=global-statement
    global unsupported_filesystems
    unsupported_filesystems = config.getoption("--unsupported-fs")
