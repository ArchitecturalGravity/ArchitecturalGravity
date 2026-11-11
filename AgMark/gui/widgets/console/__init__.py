"""Bottom-console state and optional PySide6 presentation components."""

from .state import (
    BottomConsoleState,
    CONSOLE_TABS,
    ConsoleSnapshot,
    LAST_EXPANDED_HEIGHT_KEY,
    RAW_RESPONSE_UNAVAILABLE,
)
from .text_view import ConsoleTextView
from .widget import BottomConsoleWidget, PYSIDE6_AVAILABLE

__all__ = [
    "BottomConsoleState",
    "BottomConsoleWidget",
    "CONSOLE_TABS",
    "ConsoleSnapshot",
    "ConsoleTextView",
    "LAST_EXPANDED_HEIGHT_KEY",
    "PYSIDE6_AVAILABLE",
    "RAW_RESPONSE_UNAVAILABLE",
]
