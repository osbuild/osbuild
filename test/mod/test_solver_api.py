from unittest.mock import patch

import pytest

from osbuild.solver.api import parse_request
from osbuild.solver.exceptions import InvalidAPIVersionError


def test_parse_request_invalid_api_version_value():
    """Test parse_request function with invalid api_version value"""
    request_dict = {
        "api_version": "foo",
    }
    expected_error = "Invalid API version: 'foo' is not a valid SolverAPIVersion"
    with pytest.raises(InvalidAPIVersionError, match=expected_error):
        parse_request(request_dict)


def test_parse_request_failed_to_import_api_module():
    """Test parse_request function with failed to import api module"""
    request_dict = {
        "api_version": 1,
    }
    expected_error = "Failed to import solver API module for version: 1"

    with patch("importlib.import_module", side_effect=ModuleNotFoundError("No module named 'osbuild.solver.api.v1'")):
        with pytest.raises(InvalidAPIVersionError, match=expected_error):
            parse_request(request_dict)
