import os
from typing import Optional


class Runner:
    def __init__(self, info, name: Optional[str] = None) -> None:
        self.info = info  # `meta.RunnerInfo`
        self.name = name or os.path.basename(info.path)

    @property
    def path(self):
        return self.info.path

    @property
    def exec(self):
        return os.path.basename(self.info.path)
