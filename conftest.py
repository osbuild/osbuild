import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    res = outcome.get_result()
    if res.skipped:
        error_on_skip = item.config.getoption('--error-on-skip')

        reason = str(call.excinfo.value)
        if error_on_skip:
            res.outcome = "failed"
            res.longrepr = f"skipping not allowed: {res.longrepr}"


def pytest_addoption(parser):
    parser.addoption(
        '--error-on-skip', action="store_true",
    )
