# pylint: disable=unused-import

import warnings

from .service import (ProtocolError, RemoteError, Service,  # noqa: re-export
                      ServiceClient, ServiceManager, ServiceProtocol)

warnings.warn(
    "`osbuild.host` is deprecated, use `osbuild.service` and its submodules.",
    DeprecationWarning,
)
