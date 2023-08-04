# pylint: disable=unused-import

import warnings

from .service.device import (Device, DeviceManager,  # noqa: re-export
                             DeviceService)

warnings.warn(
    "`osbuild.devices` is deprecated, use `osbuild.service.device`.",
    DeprecationWarning,
)
