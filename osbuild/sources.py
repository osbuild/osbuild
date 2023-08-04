# pylint: disable=unused-import

import warnings

from .service.source import Source, SourceService  # noqa: re-export

warnings.warn(
    "`osbuild.sources` is deprecated, use `osbuild.service.source`.",
    DeprecationWarning,
)
