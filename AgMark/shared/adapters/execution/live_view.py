"""Thread-safe presentation capture switch, independent of retained evidence."""
from threading import Lock


class LiveViewControl:
    def __init__(self, enabled=False):
        if type(enabled) is not bool:
            raise TypeError("enabled must be boolean")
        self._lock = Lock()
        self._enabled = enabled
        self._revision = 0

    def snapshot(self):
        with self._lock:
            return self._enabled, self._revision

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise TypeError("enabled must be boolean")
        with self._lock:
            if enabled != self._enabled:
                self._enabled = enabled
                self._revision += 1
