# pylint: disable=unused-import

import warnings

from .service.input import Input, InputManager, InputService  # noqa: re-export

warnings.warn(
    "`osbuild.inputs` is deprecated, use `osbuild.service.input`.",
    DeprecationWarning,
)
