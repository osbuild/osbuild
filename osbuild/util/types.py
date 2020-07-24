#
# Define some useful typing abbreviations
#

import os

from typing import Union


#: Represents a file system path. See also `os.fspath`.
PathLike = Union[str, bytes, os.PathLike]
