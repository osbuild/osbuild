#!/usr/bin/python3
"""
thread/atomic related utilities
"""
import threading


class AtomicCounter:
    """ A thread-safe counter """

    def __init__(self, count: int = 0) -> None:
        self._count = count
        self._lock = threading.Lock()

    def inc(self) -> None:
        """ increase the count """
        with self._lock:
            self._count += 1

    def dec(self) -> None:
        """ decrease the count """
        with self._lock:
            self._count -= 1

    @property
    def count(self) -> int:
        """ get the current count """
        with self._lock:
            return self._count
