# pylint: disable=unused-import

import warnings

from .manifest import Pipeline  # noqa: re-export
from .manifest.runner import Runner  # noqa: re-export
from .manifest.stage import BuildResult, Stage  # noqa: re-export
from .util import cleanup  # noqa: re-export

warnings.warn(
    "`osbuild.pipeline` is deprecated, use `osbuild.manifest` and its submodules.",
    DeprecationWarning
)
