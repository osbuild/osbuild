# pylint: disable=unused-import

import warnings

from .service.mount import MountService  # noqa: re-export
from .service.mount import (FileSystemMountService, Mount,  # noqa: re-export
                            MountManager)

warnings.warn(
    "`osbuild.mounts` is deprecated, use `osbuild.service.mount`.",
    DeprecationWarning,
)
