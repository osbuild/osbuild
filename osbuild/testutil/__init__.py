"""
Test related utilities
"""
import shutil


def has_executable(executable: str) -> bool:
    return shutil.which(executable) is not None
