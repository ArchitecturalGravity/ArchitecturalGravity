"""Reusable presentation-only progress widgets for the ArcGrav desktop GUI."""

from __future__ import annotations

from collections.abc import Sequence

from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS, LayoutMetrics
from AgMark.gui.design_system.progress import (
    DEFAULT_PROGRESS_STYLES,
    ProgressRegistry,
    ResolvedProgressPresentation,
)
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme
from AgMark.gui.design_system.typography import DEFAULT_TYPOGRAPHY, Typography


def _stage_labels(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("stages must be a sequence of visible stage labels")
    labels = tuple(values)
    if not labels:
        raise ValueError("stages must contain at least one stage label")
    if any(not isinstance(value, str) or not value.strip() for value in labels):
        raise ValueError("stage labels must be non-empty visible strings")
    return labels


try:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPaintEvent, QPen
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:

    def _font(typography: Typography, role: str = "body") -> QFont:
        style = typography.style(role)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(style.size_px)
        font.setWeight(QFont.Weight(style.weight))
        return font


    class _Ring(QWidget):
        def __init__(
            self,
            presentation: ResolvedProgressPresentation,
            typography: Typography,
            metrics: LayoutMetrics,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._presentation = presentation
            self._font = _font(typography)
            self._stroke = max(3, metrics.metric("space-xs"))
            diameter = max(72, metrics.metric("control-height") * 2)
            self.setMinimumSize(diameter, diameter)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.setAccessibleName("Progress ring")
            self._sync_accessibility()

        def set_presentation(self, value: ResolvedProgressPresentation) -> None:
            self._presentation = value
            self._sync_accessibility()
            self.update()

        def _sync_accessibility(self) -> None:
            p = self._presentation
            self.setAccessibleDescription(
                f"{p.percent:.1f}% visual progress"
            )

        def paintEvent(self, event: QPaintEvent) -> None:
            del event
            p = self._presentation
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            margin = self._stroke / 2 + 1
            side = min(self.width(), self.height()) - 2 * margin
            rect = QRectF(
                (self.width() - side) / 2,
                (self.height() - side) / 2,
                side,
                side,
            )

            background = QPen(QColor(p.background), self._stroke)
            background.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(background)
            painter.drawArc(rect, 0, 360 * 16)

            if p.current:
                active = QPen(QColor(p.active), self._stroke)
                active.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(active)
                painter.drawArc(rect, 90 * 16, -round(360 * 16 * p.fraction))

            painter.setPen(QColor(p.text))
            painter.setFont(self._font)
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter),
                f"{p.percent:.1f}%",
            )


    class ProgressIndicator(QWidget):
        """Bar, ring, or counter projection of caller-supplied numeric progress."""

        def __init__(
            self,
            current: int,
            total: int,
            *,
            form: str = "bar",
            label: str | None = None,
            registry: ProgressRegistry = DEFAULT_PROGRESS_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            if form not in {"bar", "ring", "counter"}:
                raise ValueError("progress indicator form must be bar, ring, or counter")
            super().__init__(parent)
            self._form = form
            self._registry = registry
            self._theme = theme
            self._metrics = metrics
            self._presentation = registry.resolve(
                current,
                total,
                form=form,
                label=label,
                theme=theme,
            )

            self.setObjectName("semanticProgressIndicator")
            self.setProperty("authoritySemantics", "presentation-only")
            self.setProperty("completionSemantics", "visual-only")
            self.setMinimumWidth(80 if form == "ring" else 120)
            self.setSizePolicy(
                QSizePolicy.Policy.Minimum if form == "ring" else QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(metrics.metric("space-xs"))
            self._label = QLabel(self)
            self._label.setFont(_font(typography))
            layout.addWidget(self._label)

            if form == "bar":
                indicator: QWidget = QProgressBar(self)
                indicator.setObjectName("semanticProgressBar")
                indicator.setProperty("arcgravSemanticComponent", "progress-bar")
                indicator.setMinimumHeight(metrics.metric("control-height"))
                indicator.setFont(_font(typography, "metadata"))
                indicator.setAccessibleName("Progress bar")
            elif form == "ring":
                indicator = _Ring(self._presentation, typography, metrics, self)
            else:
                indicator = QLabel(self)
                indicator.setObjectName("semanticProgressCounter")
                indicator.setProperty("arcgravSemanticComponent", "progress-counter")
                indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
                indicator.setMinimumHeight(metrics.metric("control-height"))
                indicator.setFont(_font(typography))
                indicator.setAccessibleName("Progress counter")
            self._indicator = indicator
            layout.addWidget(indicator)

            self._apply()

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def completion_semantics(self) -> str:
            return "visual-only"

        @property
        def presentation(self) -> ResolvedProgressPresentation:
            return self._presentation

        @property
        def form(self) -> str:
            return self._form

        @property
        def current(self) -> int:
            return self._presentation.current

        @property
        def total(self) -> int:
            return self._presentation.total

        @property
        def visually_complete(self) -> bool:
            return self._presentation.visually_complete

        @property
        def displayed_label(self) -> str | None:
            return self._presentation.label

        @property
        def indicator(self) -> QWidget:
            return self._indicator

        def set_progress(
            self,
            current: int,
            total: int,
            *,
            label: str | None = None,
        ) -> None:
            self._presentation = self._registry.resolve(
                current,
                total,
                form=self._form,
                label=label,
                theme=self._theme,
            )
            self._apply()

        def _apply(self) -> None:
            p = self._presentation
            self._label.setText(p.label or "")
            self._label.setVisible(p.label is not None)

            if self._form == "bar":
                bar = self._indicator
                assert isinstance(bar, QProgressBar)
                bar.setRange(0, p.total)
                bar.setValue(p.current)
                bar.setFormat(f"{p.current} of {p.total} (%p%)")
                radius = self._metrics.metric("panel-radius")
                bar.setStyleSheet(
                    'QProgressBar[arcgravSemanticComponent="progress-bar"] {'
                    f"background-color: {p.background}; color: {p.text}; "
                    f"border: 1px solid {p.background}; border-radius: {radius}px; "
                    "text-align: center;}"
                    'QProgressBar[arcgravSemanticComponent="progress-bar"]::chunk {'
                    f"background-color: {p.active}; border-radius: {radius}px;"
                    "}"
                )
            elif self._form == "ring":
                ring = self._indicator
                assert isinstance(ring, _Ring)
                ring.set_presentation(p)
            else:
                counter = self._indicator
                assert isinstance(counter, QLabel)
                counter.setText(f"{p.current} of {p.total}")
                radius = self._metrics.metric("panel-radius")
                padding = self._metrics.metric("space-sm")
                counter.setStyleSheet(
                    'QLabel[arcgravSemanticComponent="progress-counter"] {'
                    f"background-color: {p.background}; color: {p.text}; "
                    f"border: 1px solid {p.background}; border-radius: {radius}px; "
                    f"padding: {padding}px;"
                    "}"
                )

            self.setAccessibleName(p.label or "Progress")
            self.setAccessibleDescription(f"{p.current} of {p.total}; {p.percent:.0f}% visual progress")
            self.setProperty("visuallyComplete", p.visually_complete)


    class StageStepper(QWidget):
        """Stage-label projection driven only by caller-supplied progress position."""

        def __init__(
            self,
            stages: Sequence[str],
            current: int,
            *,
            orientation: str = "horizontal",
            label: str | None = None,
            registry: ProgressRegistry = DEFAULT_PROGRESS_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            labels = _stage_labels(stages)
            if orientation not in {"horizontal", "vertical"}:
                raise ValueError("stage orientation must be horizontal or vertical")
            super().__init__(parent)
            self._orientation = orientation
            self._registry = registry
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._stages = labels
            self._presentation = registry.resolve(
                current,
                len(labels),
                form="stepper",
                label=label,
                theme=theme,
            )

            self.setObjectName("semanticStageStepper")
            self.setProperty("authoritySemantics", "presentation-only")
            self.setProperty("completionSemantics", "visual-only")
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(metrics.metric("space-xs"))
            self._label = QLabel(self)
            self._label.setFont(_font(typography))
            outer.addWidget(self._label)
            self._steps = QVBoxLayout() if orientation == "vertical" else QHBoxLayout()
            self._steps.setSpacing(metrics.metric("space-xs"))
            outer.addLayout(self._steps)

            self._step_widgets: list[QWidget] = []
            self._cue_labels: list[QLabel] = []
            self._text_labels: list[QLabel] = []
            self._build()
            self._apply()

        @property
        def orientation(self) -> str:
            return self._orientation

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def completion_semantics(self) -> str:
            return "visual-only"

        @property
        def presentation(self) -> ResolvedProgressPresentation:
            return self._presentation

        @property
        def stages(self) -> tuple[str, ...]:
            return self._stages

        @property
        def current(self) -> int:
            return self._presentation.current

        @property
        def visually_complete(self) -> bool:
            return self._presentation.visually_complete

        @property
        def current_stage_label(self) -> str | None:
            return None if self.current >= len(self._stages) else self._stages[self.current]

        @property
        def stage_states(self) -> tuple[str, ...]:
            return tuple(
                "reached"
                if index < self.current
                else "current"
                if index == self.current and self.current < len(self._stages)
                else "pending"
                for index in range(len(self._stages))
            )

        def set_progress(
            self,
            current: int,
            *,
            label: str | None = None,
        ) -> None:
            self._presentation = self._registry.resolve(
                current,
                len(self._stages),
                form="stepper",
                label=label,
                theme=self._theme,
            )
            self._apply()

        def replace(
            self,
            stages: Sequence[str],
            current: int,
            *,
            label: str | None = None,
        ) -> None:
            labels = _stage_labels(stages)
            presentation = self._registry.resolve(
                current,
                len(labels),
                form="stepper",
                label=label,
                theme=self._theme,
            )
            self._stages = labels
            self._presentation = presentation
            self._clear_steps()
            self._build()
            self._apply()

        def _clear_steps(self) -> None:
            while self._steps.count():
                item = self._steps.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._step_widgets.clear()
            self._cue_labels.clear()
            self._text_labels.clear()

        def _build(self) -> None:
            for index, stage in enumerate(self._stages):
                step = QWidget(self)
                row = QHBoxLayout(step) if self._orientation == "vertical" else QVBoxLayout(step)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(self._metrics.metric("space-xs"))
                step.setMinimumHeight(28 if self._orientation == "vertical" else 48)
                step.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                cue = QLabel(str(index + 1), step)
                cue.setObjectName("semanticStageCue")
                cue.setProperty("arcgravSemanticComponent", "stage-cue")
                cue.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cue.setFont(_font(self._typography, "metadata"))
                text = QLabel(stage, step)
                if self._orientation == "vertical":
                    cue.setMinimumSize(40, 28)
                    cue.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
                    text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    text.setWordWrap(True)
                    text.setMinimumWidth(120)
                    text_policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
                    text_policy.setHeightForWidth(True)
                    text.setSizePolicy(text_policy)
                else:
                    text.setAlignment(Qt.AlignmentFlag.AlignCenter)
                text.setFont(_font(self._typography, "metadata"))
                step.setAccessibleName(stage)
                row.addWidget(cue)
                row.addWidget(text, 1 if self._orientation == "vertical" else 0)
                self._steps.addWidget(step)
                self._step_widgets.append(step)
                self._cue_labels.append(cue)
                self._text_labels.append(text)

        def _apply(self) -> None:
            p = self._presentation
            self._label.setText(p.label or "")
            self._label.setVisible(p.label is not None)
            radius = self._metrics.metric("panel-radius")
            padding = self._metrics.metric("space-xs")

            for index, state in enumerate(self.stage_states):
                if state == "reached":
                    background = border = p.active
                    foreground = self._theme.color("surface-panel")
                elif state == "current":
                    background = self._theme.color("surface-panel")
                    foreground = border = p.active
                else:
                    background = self._theme.color("surface-panel")
                    foreground = p.text
                    border = p.background

                step = self._step_widgets[index]
                cue = self._cue_labels[index]
                text = self._text_labels[index]
                cue.setText(
                    f"✓ {index + 1}"
                    if state == "reached"
                    else f"● {index + 1}"
                    if state == "current"
                    else f"○ {index + 1}"
                )
                step.setProperty("progressState", state)
                cue.setStyleSheet(
                    'QLabel[arcgravSemanticComponent="stage-cue"] {'
                    f"background-color: {background}; color: {foreground}; "
                    f"border: 2px solid {border}; border-radius: {radius}px; "
                    f"padding: {padding}px;"
                    "}"
                )
                text.setStyleSheet(f"color: {p.text};")
                step.setAccessibleDescription(
                    f"Stage {index + 1} of {len(self._stages)}; "
                    f"visual progress state: {state}"
                )

            self.setAccessibleName(p.label or "Stage progress")
            self.setAccessibleDescription(f"{p.current} of {p.total}; {p.percent:.0f}% visual progress")
            self.setProperty("visuallyComplete", p.visually_complete)


else:

    class ProgressIndicator:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for ProgressIndicator")


    class StageStepper:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for StageStepper")


__all__ = ["PYSIDE6_AVAILABLE", "ProgressIndicator", "StageStepper"]
