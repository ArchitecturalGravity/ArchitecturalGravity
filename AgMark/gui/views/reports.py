"""Single report page consuming exact caller-owned content, state and actions."""
from __future__ import annotations

from dataclasses import dataclass
from AgMark.gui.widgets.actions import ArtifactActionButton, Operation
from AgMark.gui.widgets.containers import PYSIDE6_AVAILABLE, CardWidget
from AgMark.gui.design_system.typography import DEFAULT_TYPOGRAPHY
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")


@dataclass(frozen=True, slots=True)
class ReportActionProjection:
    operation: Operation
    available: bool
    unavailable_reason: str | None = None

    def __post_init__(self):
        if not callable(self.operation) or type(self.available) is not bool:
            raise ValueError("report action requires a callable and explicit availability")
        if self.unavailable_reason is not None:
            _text(self.unavailable_reason, "unavailable_reason")
            if self.available:
                raise ValueError("unavailable_reason requires available=False")


def _unavailable():
    return ReportActionProjection(lambda: None, False, "No generated report and export operation supplied.")


@dataclass(frozen=True, slots=True)
class ReportsProjection:
    run_id: str
    report_id: str | None = None
    description: str = "Reports are validated and retained automatically when the run finishes. Open or export the exact retained report."
    readable_content: str = ""
    generation_state: str = "pending"
    completeness: str = "unavailable"
    generated_at: str = "Unavailable"
    verification_state: str = "pending"
    limitations: str = ""
    empty_state: str | None = None
    export_action: ReportActionProjection | None = None
    export_feedback: str = ""
    completion_diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        _text(self.run_id, "run_id")
        if self.report_id is not None:
            _text(self.report_id, "report_id")
        for name in ("export_action",):
            action = getattr(self, name)
            if action is not None and not isinstance(action, ReportActionProjection):
                raise ValueError(f"{name} must be a ReportActionProjection")
        for name in ("description", "generation_state", "completeness", "generated_at", "verification_state"):
            _text(getattr(self, name), name)
        if self.readable_content and self.report_id is None:
            raise ValueError("readable content requires exact report identity")
        if not self.readable_content and self.empty_state is None:
            raise ValueError("missing report content requires an explicit empty state")
        if self.empty_state is not None:
            _text(self.empty_state, "empty_state")
        if self.export_action is not None and self.export_action.available and not self.readable_content:
            raise ValueError("export requires supplied readable content")


try:
    if not PYSIDE6_AVAILABLE:
        raise ImportError
    from PySide6.QtCore import QThread, QTimer, Qt, Signal
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
except ImportError:
    PYSIDE6_AVAILABLE = False


if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.responsive import ResponsiveView, apply_minimum, wrap_text
    from AgMark.gui.widgets.report_reader import ReportReader

    class ReportsView(ResponsiveView):
        projectionRequested = Signal(object)

        def __init__(self, projection, *, parent=None):
            super().__init__(parent)
            self.setObjectName("reportsWorkspaceView")
            self.setAccessibleName("Reports workspace")
            self.setProperty("authoritySemantics", "presentation-only")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            top = QHBoxLayout()
            self.add_responsive_layout(top, 800)
            self.heading_holder = QWidget(self)
            apply_minimum(self.heading_holder, 220, 20, False)
            heading = QVBoxLayout(self.heading_holder)
            heading.setContentsMargins(0, 0, 0, 0)
            heading.setSpacing(4)
            self.description_label = QLabel(self)
            self.description_label.setWordWrap(True)
            heading.addWidget(self.description_label)
            wrap_text(self.description_label)
            top.addWidget(self.heading_holder, 1)
            self.actions_holder = QWidget(self)
            self.actions_layout = QHBoxLayout(self.actions_holder)
            self.actions_layout.setContentsMargins(0, 0, 0, 0)
            top.addWidget(self.actions_holder)
            layout.addLayout(top)
            self.status_label = QLabel(self)
            self.status_label.setObjectName("reportStatus")
            self.status_label.setAccessibleName("Report generation, completeness and verification status")
            self.status_label.setTextFormat(Qt.TextFormat.PlainText)
            self.status_label.setWordWrap(True)
            self.status_card = CardWidget("Report status", self.status_label, compact=True, parent=self)
            wrap_text(self.status_label)
            apply_minimum(self.status_card, 520, 112, False)
            layout.addWidget(self.status_card)
            self.completion_diagnostics_label = QLabel(self)
            self.completion_diagnostics_label.setObjectName("reportCompletionDiagnostics")
            self.completion_diagnostics_label.setAccessibleName("Completion stage diagnostics")
            self.completion_diagnostics_label.setTextFormat(Qt.TextFormat.PlainText)
            self.completion_diagnostics_label.setWordWrap(True)
            wrap_text(self.completion_diagnostics_label)
            layout.addWidget(self.completion_diagnostics_label)
            self.export_feedback_label = QLabel(self)
            self.export_feedback_label.setObjectName("reportExportFeedback")
            self.export_feedback_label.setWordWrap(True)
            self.export_feedback_label.setTextFormat(Qt.TextFormat.PlainText)
            wrap_text(self.export_feedback_label)
            apply_minimum(self.export_feedback_label, 320, 36, False)
            layout.addWidget(self.export_feedback_label)
            reader_tools = QHBoxLayout()
            reader_tools.addWidget(QLabel("Jump to section", self))
            self.section_selector = QComboBox(self)
            self.section_selector.setAccessibleName("Report section")
            self.section_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self.section_selector.setMinimumContentsLength(12)
            reader_tools.addWidget(self.section_selector, 1)
            self.expand_button = QPushButton("Open Report", self)
            self.expand_button.clicked.connect(self._expand_report)
            reader_tools.addWidget(self.expand_button)
            layout.addLayout(reader_tools)
            self.content_browser = ReportReader(self)
            self.content_browser.setObjectName("readableReportContent")
            self.content_browser.setAccessibleName("Readable generated report")
            self.content_browser.setOpenLinks(False)
            self.content_browser.setOpenExternalLinks(False)
            body = DEFAULT_TYPOGRAPHY.style("body")
            font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
            font.setPixelSize(body.size_px)
            font.setWeight(QFont.Weight(body.weight))
            self.content_browser.setFont(font)
            self.content_browser.setProperty("surfaceRole", "panel")
            self.content_browser.setProperty("textRole", "body")
            self.content_browser.setStyleSheet(
                "QTextBrowser { background: " + DEFAULT_LIGHT_THEME.color("surface-panel") + "; color: " + DEFAULT_LIGHT_THEME.color("text-primary") + "; border: 1px solid " + DEFAULT_LIGHT_THEME.color("border-default") + "; padding: 10px; }")
            self.section_selector.activated.connect(self._select_section)
            apply_minimum(self.content_browser, 480, 300)
            layout.addWidget(self.content_browser, 1)
            self.projectionRequested.connect(self._apply_projection, Qt.ConnectionType.QueuedConnection)
            self._apply_projection(projection)

        @property
        def projection(self):
            return self._projection

        @property
        def run_id(self):
            return self._projection.run_id

        @property
        def authority_semantics(self):
            return "presentation-only"

        def set_projection(self, projection):
            if not isinstance(projection, ReportsProjection):
                raise ValueError("projection must be ReportsProjection")
            if QThread.currentThread() == self.thread():
                self._apply_projection(projection)
            else:
                self.projectionRequested.emit(projection)

        def _select_section(self, index):
            position = self.section_selector.itemData(index)
            if position is not None:
                self.content_browser.go_to_section(position)

        def _expand_report(self):
            dialog = QDialog(self)
            dialog.setWindowTitle("Generated report")
            dialog.resize(1060, 760)
            layout = QVBoxLayout(dialog)
            reader = ReportReader(dialog)
            reader.setFont(self.content_browser.font())
            reader.setStyleSheet(self.content_browser.styleSheet())
            reader.setAccessibleName("Expanded generated report")
            reader.set_report(self.projection.readable_content)
            layout.addWidget(reader)
            close = QPushButton("Close", dialog)
            close.clicked.connect(dialog.accept)
            layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
            QTimer.singleShot(0, lambda: reader.go_to_section(self.content_browser.textCursor().position()))
            dialog.exec()
            dialog.deleteLater()

        def _button(self, label, action, role):
            action = action or _unavailable()
            button = ArtifactActionButton(label, action.operation, available=action.available, role=role, parent=self.actions_holder)
            button.setAccessibleDescription(action.unavailable_reason or label)
            button.setProperty("callerUnavailableReason", action.unavailable_reason or "")
            button.setMinimumSize(button.minimumSizeHint().width(), 40)
            self.actions_layout.addWidget(button)
            return button

        def _apply_projection(self, projection):
            if not isinstance(projection, ReportsProjection):
                raise ValueError("projection must be ReportsProjection")
            previous = getattr(self, "_projection", None)
            content_changed = previous is None or (
                previous.run_id, previous.report_id, previous.readable_content, previous.empty_state
            ) != (projection.run_id, projection.report_id, projection.readable_content, projection.empty_state)
            self._projection = projection
            while self.actions_layout.count():
                widget = self.actions_layout.takeAt(0).widget()
                if widget:
                    widget.setEnabled(False)
                    widget.hide()
                    widget.deleteLater()
            self.export_button = self._button("Export Report", projection.export_action, "contextual")
            self.actions_holder.setMinimumSize(self.actions_layout.minimumSize())
            self.description_label.setText(projection.description)
            self.status_label.setText("\\n".join((
                f"Report: {projection.report_id or 'Unavailable'} | Run: {projection.run_id}",
                f"Completion: {projection.generation_state} | Completeness: {projection.completeness} | Generated: {projection.generated_at}",
                f"Completion validation: {projection.verification_state}",
                projection.limitations)).replace("\\n", "\n"))
            if content_changed:
                self.content_browser.clear()
                if projection.readable_content:
                    self.content_browser.set_report(projection.readable_content)
                else:
                    self.content_browser.setPlainText(projection.empty_state or "")
                self.section_selector.clear()
                for title, position in getattr(self.content_browser, "major_sections", ()) if projection.readable_content else ():
                    self.section_selector.addItem(title, position)
            self.section_selector.setEnabled(bool(projection.readable_content))
            self.expand_button.setEnabled(bool(projection.readable_content))
            self.completion_diagnostics_label.setText("\n".join(projection.completion_diagnostics))
            self.completion_diagnostics_label.setVisible(bool(projection.completion_diagnostics))
            self.export_feedback_label.setText(projection.export_feedback)
            self.export_feedback_label.setVisible(bool(projection.export_feedback))
else:
    class ReportsView:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for ReportsView")

__all__ = ["PYSIDE6_AVAILABLE", "ReportActionProjection", "ReportsProjection", "ReportsView"]
