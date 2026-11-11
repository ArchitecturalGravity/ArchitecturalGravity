"""Presentation-only explicit actions for the desktop GUI.

These widgets execute only caller-supplied operations and consume explicit
caller-supplied availability. They never infer benchmark, lifecycle, evidence,
reporting, reconstruction, verification, or permission authority from labels
or local widget state.
"""

from __future__ import annotations

from collections.abc import Callable

from AgMark.gui.widgets.buttons import ActionButton, PYSIDE6_AVAILABLE


Operation = Callable[[], object]


def _require_operation(value: Operation, *, name: str) -> Operation:
    if not callable(value):
        raise ValueError(f"{name} must be callable")
    return value


def _require_available(value: bool, *, name: str = "available") -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QWidget

    class ArtifactActionButton(ActionButton):
        """Action button that invokes only a caller-supplied operation."""

        def __init__(
            self,
            label: str,
            operation: Operation,
            *,
            available: bool,
            role: str = "contextual",
            parent: QWidget | None = None,
            **button_kwargs,
        ) -> None:
            operation = _require_operation(operation, name="operation")
            available = _require_available(available)
            self._requested_role = role
            self._available = available
            self._operation = operation

            super().__init__(
                label,
                role if available else "unavailable",
                parent=parent,
                **button_kwargs,
            )
            requested = self._registry.resolve(role, theme=self._theme)
            if not requested.enabled:
                raise ValueError("role must identify an enabled semantic action role")
            self.setProperty("requestedSemanticRole", role)
            self.setProperty("callerAvailable", available)
            self.clicked.connect(self._invoke_operation)

        @property
        def available(self) -> bool:
            return self._available

        @property
        def requested_role(self) -> str:
            return self._requested_role

        @property
        def operation(self) -> Operation:
            return self._operation

        def set_available(self, available: bool) -> None:
            """Project explicit caller availability without deriving permission."""

            available = _require_available(available)
            self._available = available
            self.setProperty("callerAvailable", available)
            self.set_role(self._requested_role if available else "unavailable")

        def _invoke_operation(self, checked: bool = False) -> None:
            del checked
            if self._available:
                self._operation()


else:

    class ArtifactActionButton:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for ArtifactActionButton")


__all__ = [
    "ArtifactActionButton",
    "Operation",
    "PYSIDE6_AVAILABLE",
]
