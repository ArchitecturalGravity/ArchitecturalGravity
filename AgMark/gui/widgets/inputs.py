"""Reusable semantic input widgets for the ArcGrav desktop GUI.

The widgets consume caller-supplied values, validation text, accessory text, and
selection state. They are presentation-only and do not infer benchmark,
lifecycle, evidence, scoring, report, reconstruction, or verification authority
from visible values.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import inf, isfinite, nextafter

from AgMark.gui.design_system.inputs import (
    DEFAULT_INPUT_STYLES,
    InputRegistry,
    ResolvedInputStyle,
)
from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    LayoutMetrics,
)
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme, semantic_icon
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)


def _require_visible_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


def _optional_visible_text(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_visible_text(value, name=name)


def _select_options(options: Sequence[str]) -> tuple[str, ...]:
    if isinstance(options, (str, bytes)):
        raise ValueError("options must be a sequence of visible strings")

    normalized = tuple(
        _require_visible_text(option, name="option") for option in options
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError("options must contain unique visible strings")
    return normalized


try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPainter
    from PySide6.QtWidgets import (
        QComboBox,
        QDoubleSpinBox,
        QSpinBox,
        QStyle,
        QStyleOptionSpinBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QSizePolicy,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:

    def _font(typography: Typography, role: str = "body") -> QFont:
        text_style = typography.style(role)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(text_style.size_px)
        font.setWeight(QFont.Weight(text_style.weight))
        return font


    def _control_stylesheet(
        selector: str,
        resolved: ResolvedInputStyle,
        *,
        metrics: LayoutMetrics,
    ) -> str:
        border_width = metrics.metric("border-width")
        radius = metrics.metric("panel-radius")
        horizontal_padding = metrics.metric("space-sm")
        return (
            f"{selector} {{"
            f"background-color: {resolved.background};"
            f"border: {border_width}px solid {resolved.border};"
            f"border-radius: {radius}px;"
            f"color: {resolved.text};"
            f"padding-left: {horizontal_padding}px;"
            f"padding-right: {horizontal_padding}px;"
            "}"
            f"{selector}:hover:enabled:!focus {{"
            f"border-color: {resolved.focus_border};"
            "}"
            f"{selector}:focus {{"
            f"border: {border_width}px solid {resolved.focus_border};"
            "}"
            f"{selector}:disabled {{color: {resolved.placeholder};}}"
            f'{selector}[validationState="invalid"], {selector}[validationState="invalid"]:hover:enabled {{'
            f"border: {border_width}px solid {resolved.validation_border};"
            "}"
        )


    def _auxiliary_button_stylesheet(
        selector: str,
        resolved: ResolvedInputStyle,
        *,
        metrics: LayoutMetrics,
    ) -> str:
        border_width = metrics.metric("border-width")
        radius = metrics.metric("panel-radius")
        horizontal_padding = metrics.metric("space-sm")
        return (
            f"{selector} {{"
            f"background-color: {resolved.background};"
            f"border: {border_width}px solid {resolved.border};"
            f"border-radius: {radius}px;"
            f"color: {resolved.text};"
            f"padding-left: {horizontal_padding}px;"
            f"padding-right: {horizontal_padding}px;"
            "}"
            f"{selector}:hover:enabled:!focus {{"
            f"border-color: {resolved.focus_border};"
            "}"
            f"{selector}:focus {{"
            f"border: {border_width}px solid {resolved.focus_border};"
            "}"
            f"{selector}:pressed {{"
            f"border: {border_width}px solid {resolved.focus_border};"
            "}"
        )


    class _LabeledInput(QWidget):
        """Shared presentation shell for explicit caller-supplied input state."""

        _CONTROL_SELECTOR = ""

        def __init__(
            self,
            label: str,
            role: str,
            *,
            accessory_text: str | None,
            validation_message: str | None,
            show_label: bool,
            registry: InputRegistry,
            theme: Theme,
            typography: Typography,
            metrics: LayoutMetrics,
            parent: QWidget | None,
        ) -> None:
            label = _require_visible_text(label, name="label")
            accessory_text = _optional_visible_text(
                accessory_text, name="accessory_text"
            )
            validation_message = _optional_visible_text(
                validation_message, name="validation_message"
            )
            if not isinstance(show_label, bool):
                raise ValueError("show_label must be a boolean")
            super().__init__(parent)

            self._role = role
            self._registry = registry
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._presentation = registry.resolve(
                role,
                theme=theme,
                metrics=metrics,
            )

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(metrics.metric("space-xs"))

            self._label = QLabel(label, self)
            self._label.setFont(_font(typography))
            self._label.setStyleSheet(f"color: {self._presentation.text};")
            self._label.setVisible(show_label)
            self._label_visible = show_label
            root.addWidget(self._label)

            self._control_row = QHBoxLayout()
            self._control_row.setContentsMargins(0, 0, 0, 0)
            self._control_row.setSpacing(metrics.metric("space-sm"))
            root.addLayout(self._control_row)

            self._accessory = QLabel(self)
            self._accessory.setFont(_font(typography, "metadata"))
            self._accessory.setStyleSheet(
                f"color: {self._presentation.placeholder};"
            )
            self._control_row.addWidget(self._accessory)

            self._validation = QLabel(self)
            self._validation.setFont(_font(typography, "metadata"))
            self._validation.setStyleSheet(
                f"color: {self._presentation.validation_border};"
            )
            root.addWidget(self._validation)

            self.setAccessibleName(label)
            self.set_accessory_text(accessory_text)
            self.set_validation_message(validation_message)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def role(self) -> str:
            return self._role

        @property
        def label(self) -> str:
            return self._label.text()

        @property
        def label_visible(self) -> bool:
            return self._label_visible

        @property
        def presentation(self) -> ResolvedInputStyle:
            return self._presentation

        @property
        def accessory_text(self) -> str | None:
            return self._accessory_text

        @property
        def validation_message(self) -> str | None:
            return self._validation_message

        @property
        def is_valid(self) -> bool:
            return self.validation_message is None

        def _attach_control(self, control: QWidget) -> None:
            self._control = control
            self._control_row.insertWidget(0, control, 1)
            control.setAccessibleName(self.label)
            control.setFont(_font(self._typography))
            control.setMinimumHeight(self._presentation.control_height_px)
            control.setProperty("arcgravSemanticComponent", "input-control")
            control.setProperty("semanticRole", self._role)
            control.setProperty("validationState", "valid")
            control.setStyleSheet(
                _control_stylesheet(
                    self._CONTROL_SELECTOR,
                    self._presentation,
                    metrics=self._metrics,
                )
            )
            self._refresh_validation_property()

        def _refresh_validation_property(self) -> None:
            if not hasattr(self, "_control"):
                return
            self._control.setProperty(
                "validationState",
                "valid" if self.is_valid else "invalid",
            )
            style = self._control.style()
            style.unpolish(self._control)
            style.polish(self._control)
            self._control.update()

        def set_accessory_text(self, text: str | None) -> None:
            """Project optional caller-supplied accessory text exactly."""

            text = _optional_visible_text(text, name="accessory_text")
            self._accessory_text = text
            self._accessory.setText(text or "")
            self._accessory.setVisible(text is not None)

        def set_validation_message(self, message: str | None) -> None:
            """Project caller-supplied validation state without deriving semantics."""

            message = _optional_visible_text(
                message, name="validation_message"
            )
            self._validation_message = message
            self._validation.setText(message or "")
            self._validation.setVisible(message is not None)
            self.setAccessibleDescription(message or "")
            self._refresh_validation_property()


    class SelectInput(_LabeledInput):
        """Non-editable selection control with explicit options and selection."""

        _CONTROL_SELECTOR = 'QComboBox[arcgravSemanticComponent="input-control"]'

        def __init__(
            self,
            label: str,
            options: Sequence[str],
            value: str | None = None,
            *,
            option_labels: Sequence[str] | None = None,
            placeholder: str | None = None,
            accessory_text: str | None = None,
            validation_message: str | None = None,
            show_label: bool = True,
            registry: InputRegistry = DEFAULT_INPUT_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            self._options = _select_options(options)
            labels = self._options if option_labels is None else _select_options(option_labels)
            if len(labels) != len(self._options):
                raise ValueError("option labels must match supplied options")
            placeholder = _optional_visible_text(
                placeholder, name="placeholder"
            )
            super().__init__(
                label,
                "text",
                accessory_text=accessory_text,
                validation_message=validation_message,
                show_label=show_label,
                registry=registry,
                theme=theme,
                typography=typography,
                metrics=metrics,
                parent=parent,
            )

            self.combo_box = QComboBox(self)
            self.combo_box.setObjectName("semanticSelectInput")
            self.combo_box.setEditable(False)
            self.combo_box.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            self.combo_box.setMinimumContentsLength(12)
            self.combo_box.setMinimumWidth(0)
            size_policy = self.combo_box.sizePolicy()
            size_policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
            self.combo_box.setSizePolicy(size_policy)
            for option, label in zip(self._options, labels):
                self.combo_box.addItem(label, option)
            if placeholder is not None:
                self.combo_box.setPlaceholderText(placeholder)
            self._attach_control(self.combo_box)
            self.set_value(value)

        @property
        def options(self) -> tuple[str, ...]:
            return self._options

        def set_options(
            self, options: Sequence[str], value: str | None = None, *,
            option_labels: Sequence[str] | None = None,
        ) -> None:
            options = _select_options(options)
            labels = options if option_labels is None else _select_options(option_labels)
            if len(labels) != len(options):
                raise ValueError("option labels must match supplied options")
            if value is not None and value not in options:
                raise ValueError("value must be a supplied option")
            previous = self.combo_box.blockSignals(True)
            try:
                self._options = options
                self.combo_box.clear()
                for option, label in zip(options, labels):
                    self.combo_box.addItem(label, option)
                self.set_value(value)
            finally:
                self.combo_box.blockSignals(previous)

        @property
        def value(self) -> str | None:
            index = self.combo_box.currentIndex()
            return self.combo_box.itemData(index, Qt.ItemDataRole.UserRole) if index >= 0 else None

        def set_value(self, value: str | None) -> None:
            """Apply only an explicit caller-supplied option selection."""

            if value is None:
                self.combo_box.setCurrentIndex(-1)
                return
            if not isinstance(value, str) or value not in self._options:
                raise ValueError("value must be None or one of the supplied options")
            self.combo_box.setCurrentIndex(self._options.index(value))


    class CredentialInput(_LabeledInput):
        """Password-echo text field with hold-to-reveal transient visibility."""

        _CONTROL_SELECTOR = 'QLineEdit[arcgravSemanticComponent="input-control"]'

        def __init__(
            self,
            label: str,
            value: str = "",
            *,
            placeholder: str | None = None,
            accessory_text: str | None = None,
            validation_message: str | None = None,
            show_label: bool = True,
            registry: InputRegistry = DEFAULT_INPUT_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            if not isinstance(value, str):
                raise ValueError("value must be a string")
            placeholder = _optional_visible_text(
                placeholder, name="placeholder"
            )
            super().__init__(
                label,
                "credential",
                accessory_text=accessory_text,
                validation_message=validation_message,
                show_label=show_label,
                registry=registry,
                theme=theme,
                typography=typography,
                metrics=metrics,
                parent=parent,
            )

            self.line_edit = QLineEdit(self)
            self.line_edit.setObjectName("semanticCredentialInput")
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.line_edit.setText(value)
            if placeholder is not None:
                self.line_edit.setPlaceholderText(placeholder)
            self._attach_control(self.line_edit)

            self.reveal_button = QToolButton(self)
            self.reveal_button.setObjectName("semanticCredentialRevealButton")
            self.reveal_button.setProperty(
                "arcgravSemanticComponent",
                "credential-reveal-button",
            )
            self.reveal_button.setProperty(
                "authoritySemantics",
                "presentation-only",
            )
            self.reveal_button.setProperty("semanticRole", "credential-visibility")
            self.reveal_button.setText("Show")
            self.reveal_button.setAccessibleName(
                f"Hold to reveal {self.label}"
            )
            self.reveal_button.setFont(_font(self._typography))
            self.reveal_button.setMinimumHeight(self._presentation.control_height_px)
            self.reveal_button.setStyleSheet(
                _auxiliary_button_stylesheet(
                    'QToolButton[arcgravSemanticComponent="credential-reveal-button"]',
                    self._presentation,
                    metrics=self._metrics,
                )
            )
            self.reveal_button.pressed.connect(self._begin_transient_reveal)
            self.reveal_button.released.connect(self._end_transient_reveal)
            self._control_row.insertWidget(1, self.reveal_button)

        @property
        def value(self) -> str:
            return self.line_edit.text()

        @property
        def obscured(self) -> bool:
            return self.line_edit.echoMode() == QLineEdit.EchoMode.Password

        def set_value(self, value: str) -> None:
            """Replace the transient field value without persisting it elsewhere."""

            if not isinstance(value, str):
                raise ValueError("value must be a string")
            self.line_edit.setText(value)

        def _begin_transient_reveal(self) -> None:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.reveal_button.setText("Hide")

        def _end_transient_reveal(self) -> None:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.reveal_button.setText("Show")


    class _IntegerSpinBox(QSpinBox):
        """Keep native stepping/hit targets with deterministic semantic arrows."""

        def paintEvent(self, event) -> None:
            super().paintEvent(event)
            option = QStyleOptionSpinBox()
            self.initStyleOption(option)
            painter = QPainter(self)
            steps = self.stepEnabled()
            for control, role, flag in (
                (QStyle.SubControl.SC_SpinBoxUp, "collapse", self.StepEnabledFlag.StepUpEnabled),
                (QStyle.SubControl.SC_SpinBoxDown, "expand", self.StepEnabledFlag.StepDownEnabled),
            ):
                rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, self)
                mode = QIcon.Mode.Normal if self.isEnabled() and steps & flag else QIcon.Mode.Disabled
                semantic_icon(role, size=12).paint(painter, rect, Qt.AlignmentFlag.AlignCenter, mode)
            painter.end()


    class IntegerInput(_LabeledInput):
        """Integer incrementor using the same semantic chrome as other inputs."""

        _CONTROL_SELECTOR = 'QSpinBox[arcgravSemanticComponent="input-control"]'

        def __init__(self, label: str, value: int, *, minimum: int, maximum: int,
                     parent: QWidget | None = None) -> None:
            if any(type(v) is not int for v in (value, minimum, maximum)):
                raise ValueError("integer input requires integer values")
            if not minimum <= value <= maximum:
                raise ValueError("value must be within the supplied integer range")
            super().__init__(label, "numeric", accessory_text=None,
                validation_message=None, show_label=True,
                registry=DEFAULT_INPUT_STYLES, theme=DEFAULT_LIGHT_THEME,
                typography=DEFAULT_TYPOGRAPHY, metrics=DEFAULT_LAYOUT_METRICS,
                parent=parent)
            self.spin_box = _IntegerSpinBox(self)
            self.spin_box.setObjectName("semanticIntegerInput")
            self.spin_box.setRange(minimum, maximum)
            self.spin_box.setValue(value)
            self._attach_control(self.spin_box)
            selector = self._CONTROL_SELECTOR
            self.spin_box.setStyleSheet(self.spin_box.styleSheet() +
                f"{selector} {{padding-right: 20px;}}"
                f"{selector}::up-button, {selector}::down-button {{width: 18px; border: none; background: transparent;}}"
                f"{selector}::up-arrow, {selector}::down-arrow {{image: none;}}")


    class NumericInput(_LabeledInput):
        """Typed numeric control with explicit caller-owned range and value."""

        _CONTROL_SELECTOR = 'QDoubleSpinBox[arcgravSemanticComponent="input-control"]'

        def __init__(
            self,
            label: str,
            value: float | None,
            *,
            minimum: float,
            maximum: float,
            step: float = 1.0,
            decimals: int = 0,
            accessory_text: str | None = None,
            validation_message: str | None = None,
            show_label: bool = True,
            registry: InputRegistry = DEFAULT_INPUT_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            minimum = self._finite_number(minimum, name="minimum")
            maximum = self._finite_number(maximum, name="maximum")
            step = self._finite_number(step, name="step")
            normalized_value = (
                None
                if value is None
                else self._finite_number(value, name="value")
            )
            if minimum > maximum:
                raise ValueError("minimum must be less than or equal to maximum")
            if step <= 0:
                raise ValueError("step must be greater than zero")
            if not isinstance(decimals, int) or isinstance(decimals, bool) or decimals < 0:
                raise ValueError("decimals must be a non-negative integer")
            if (
                normalized_value is not None
                and not minimum <= normalized_value <= maximum
            ):
                raise ValueError("value must be within the supplied numeric range")

            self._minimum = minimum
            self._maximum = maximum
            self._unset_value: float | None = None
            super().__init__(
                label,
                "numeric",
                accessory_text=accessory_text,
                validation_message=validation_message,
                show_label=show_label,
                registry=registry,
                theme=theme,
                typography=typography,
                metrics=metrics,
                parent=parent,
            )

            self.spin_box = QDoubleSpinBox(self)
            self.spin_box.setObjectName("semanticNumericInput")
            self.spin_box.setDecimals(decimals)
            if normalized_value is None:
                display_quantum = 10.0 ** (-decimals)
                sentinel = minimum - max(step, display_quantum)
                if not isfinite(sentinel) or sentinel >= minimum:
                    sentinel = nextafter(minimum, -inf)
                if not isfinite(sentinel) or sentinel >= minimum:
                    raise ValueError(
                        "minimum does not permit unresolved numeric presentation"
                    )
                self._unset_value = sentinel
                self.spin_box.setRange(sentinel, maximum)
                self.spin_box.setSpecialValueText("Not set")
                self.spin_box.setValue(sentinel)
            else:
                self.spin_box.setRange(minimum, maximum)
                self.spin_box.setValue(normalized_value)
            self.spin_box.setSingleStep(step)
            self._attach_control(self.spin_box)

        @staticmethod
        def _finite_number(value: float, *, name: str) -> float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            normalized = float(value)
            if not isfinite(normalized):
                raise ValueError(f"{name} must be a finite number")
            return normalized

        @property
        def value(self) -> float | None:
            value = self.spin_box.value()
            if self._unset_value is not None and value < self._minimum:
                return None
            return value

        @property
        def minimum(self) -> float:
            return self._minimum

        @property
        def maximum(self) -> float:
            return self._maximum

        def set_value(self, value: float | None) -> None:
            """Apply an explicit numeric value without silently clamping it."""

            if value is None:
                if self._unset_value is None:
                    raise ValueError("this numeric input does not permit an unset value")
                self.spin_box.setValue(self._unset_value)
                return
            normalized = self._finite_number(value, name="value")
            if not self._minimum <= normalized <= self._maximum:
                raise ValueError("value must be within the supplied numeric range")
            self.spin_box.setValue(normalized)


else:

    class SelectInput:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for SelectInput")


    class CredentialInput:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for CredentialInput")


    class IntegerInput:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for IntegerInput")


    class NumericInput:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for NumericInput")


__all__ = [
    "CredentialInput",
    "NumericInput",
    "IntegerInput",
    "PYSIDE6_AVAILABLE",
    "SelectInput",
]
