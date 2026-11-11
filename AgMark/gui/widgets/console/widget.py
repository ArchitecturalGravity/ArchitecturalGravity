"""Concrete bottom-console widget composition."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import MutableMapping

from .state import (
    BottomConsoleState,
    CONSOLE_TABS,
    LAST_EXPANDED_HEIGHT_KEY,
    RAW_RESPONSE_UNAVAILABLE,
    _require_generation_id,
    _require_invocation_id,
    _require_height,
    _require_tab,
)

# Optional concrete Python desktop surface. Keeping these imports below the
# toolkit-independent state boundary lets centralized non-GUI tests import this
# module even when PySide6 is not installed.
from AgMark.gui.design_system.buttons import resolved_button
from AgMark.gui.design_system.console import resolved_console_presentation
from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS, LayoutMetrics
from AgMark.gui.design_system.surfaces import resolved_surface
from AgMark.gui.design_system.tabs import resolved_tab
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    Theme,
    semantic_icon,
)
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)

try:
    from PySide6.QtCore import QRect, QSize, QSettings, Qt, QTimer, Signal
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QPainter,
        QSyntaxHighlighter,
        QTextCharFormat,
        QTextCursor,
    )
    from PySide6.QtWidgets import (
        QCheckBox,
        QAbstractScrollArea,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QStackedWidget,
        QTabBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True

if PYSIDE6_AVAILABLE:
    from .preferences import _QtSettingsPreferences
    from .text_view import ConsoleTextView


    class BottomConsoleWidget(QWidget):
        """Concrete presentation-only bottom console for the Python desktop GUI.

        Direct mutation methods are GUI-thread entry points. Worker-originated console
        events use the queue_* methods, which marshal through queued Qt signals before
        state or widget mutation.
        """

        expandedChanged = Signal(bool)
        activeTabChanged = Signal(str)
        expandedHeightRequested = Signal(int)
        _queuedBindGeneration = Signal(str)
        _queuedLiveOutput = Signal(str, str)
        _queuedDiagnostic = Signal(str, str)
        _queuedEnvironment = Signal(str)
        _queuedRawResponse = Signal(str, object)
        _queuedLiveViewReady = Signal()

        def __init__(
            self,
            *,
            state: BottomConsoleState | None = None,
            preferences: MutableMapping[str, int] | None = None,
            settings: QSettings | None = None,
            default_expanded_height: int = 260,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            if state is not None and (preferences is not None or settings is not None):
                raise ValueError("state cannot be combined with preferences or settings")
            if preferences is not None and settings is not None:
                raise ValueError("provide preferences or settings, not both")

            if state is None:
                if settings is not None:
                    preferences = _QtSettingsPreferences(settings)  # type: ignore[assignment]
                self._state = BottomConsoleState(
                    preferences=preferences,
                    default_expanded_height=default_expanded_height,
                )
            else:
                self._state = state

            from AgMark.shared.adapters.execution.live_view import LiveViewControl
            self._stream_preferences = preferences
            input_enabled = bool(preferences.get("console/stream_live_input", 0)) if preferences is not None else False
            output_enabled = bool(preferences.get("console/stream_live_output", 0)) if preferences is not None else False
            self.live_view_control = LiveViewControl(input_enabled or output_enabled)
            self._state.set_live_view_channels(input_enabled=input_enabled, output_enabled=output_enabled)

            self._views: dict[str, ConsoleTextView] = {}
            self._theme = theme
            self._queue_lock = Lock()
            self._queue_generation = self._state.active_generation_id
            self._closed = False
            self._live_drain_scheduled = False
            self._pending_live: OrderedDict[str, tuple[str | None, str | None, str | None]] = OrderedDict()
            self._live_timer = QTimer(self)
            self._live_timer.setSingleShot(True)
            self._live_timer.setInterval(16)
            self._live_timer.timeout.connect(self._flush_live_view)

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            header = QWidget(self)
            header.setProperty("arcgravSemanticComponent", "console-header")
            header_surface = resolved_surface(
                "panel",
                theme=theme,
                metrics=metrics,
            )
            header.setStyleSheet(
                'QWidget[arcgravSemanticComponent="console-header"] {'
                f"background-color: {header_surface.background};"
                f"border-bottom: {header_surface.border_width_px}px solid "
                f"{header_surface.border};"
                "}"
            )
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(
                metrics.metric("space-sm"),
                metrics.metric("space-xs"),
                metrics.metric("space-sm"),
                metrics.metric("space-xs"),
            )
            header_layout.setSpacing(metrics.metric("space-sm"))

            self.console_title_label = QLabel("Console", header)
            self.console_title_label.setProperty(
                "arcgravSemanticComponent",
                "console-title",
            )
            self.console_title_label.setAccessibleName("Console")
            title_style = typography.style("card-heading")
            title_font = QFontDatabase.systemFont(
                QFontDatabase.SystemFont.GeneralFont
            )
            title_font.setPixelSize(title_style.size_px)
            title_font.setWeight(QFont.Weight(title_style.weight))
            self.console_title_label.setFont(title_font)
            self.console_title_label.setStyleSheet(
                'QLabel[arcgravSemanticComponent="console-title"] {'
                f"color: {theme.color('text-primary')};"
                "background: transparent;"
                "border: 0px;"
                "}"
            )
            header_layout.addWidget(self.console_title_label)
            header_layout.addStretch(1)

            contextual_action = resolved_button("contextual", theme=theme)
            action_height = (
                metrics.metric("control-height") - metrics.metric("space-sm")
            )
            action_radius = metrics.metric("panel-radius")
            action_border = metrics.metric("border-width")
            action_padding = metrics.metric("space-sm")
            action_hover = theme.color("surface-selected")
            action_focus = theme.color("focus-ring")
            action_style = (
                'QPushButton[arcgravSemanticComponent="console-clear-button"], '
                'QToolButton[arcgravSemanticComponent="console-collapse-button"] {'
                f"background-color: {contextual_action.background};"
                f"border: {action_border}px solid {contextual_action.border};"
                f"border-radius: {action_radius}px;"
                f"color: {contextual_action.text};"
                f"padding: 0px {action_padding}px;"
                "}"
                'QPushButton[arcgravSemanticComponent="console-clear-button"]:hover:enabled, '
                'QToolButton[arcgravSemanticComponent="console-collapse-button"]:hover:enabled {'
                f"background-color: {action_hover};"
                "}"
                'QPushButton[arcgravSemanticComponent="console-clear-button"]:focus, '
                'QToolButton[arcgravSemanticComponent="console-collapse-button"]:focus {'
                f"border-color: {action_focus};"
                "}"
            )

            self.stream_live_view_group = QWidget(header)
            self.stream_live_view_group.setProperty("arcgravSemanticComponent", "console-stream-controls")
            self.stream_live_view_group.setAccessibleName("Stream Live View")
            self.stream_live_view_group.setStyleSheet(
                'QWidget[arcgravSemanticComponent="console-stream-controls"] {'
                f"background-color: {contextual_action.background};"
                f"border: {action_border}px solid {contextual_action.border};"
                f"border-radius: {action_radius}px;"
                f"color: {contextual_action.text};"
                "}"
            )
            stream_layout = QHBoxLayout(self.stream_live_view_group)
            stream_layout.setContentsMargins(action_padding, metrics.metric("space-xs"), action_padding, metrics.metric("space-xs"))
            stream_layout.setSpacing(metrics.metric("space-sm"))
            stream_layout.addWidget(QLabel("Stream Live View:", self.stream_live_view_group))
            self.stream_input_checkbox = QCheckBox("Input", self.stream_live_view_group)
            self.stream_output_checkbox = QCheckBox("Output", self.stream_live_view_group)
            for checkbox, enabled in ((self.stream_input_checkbox, input_enabled), (self.stream_output_checkbox, output_enabled)):
                checkbox.setAccessibleName(f"Stream Live View {checkbox.text()}")
                checkbox.setChecked(enabled)
                checkbox.toggled.connect(self._update_stream_channels)
                stream_layout.addWidget(checkbox)
            header_layout.addWidget(self.stream_live_view_group)
            self.clear_button = QPushButton("Clear", header)
            self.clear_button.setProperty(
                "arcgravSemanticComponent",
                "console-clear-button",
            )
            self.clear_button.setProperty("semanticRole", "contextual")
            self.clear_button.setIcon(semantic_icon("clear", theme=theme))
            self.clear_button.setProperty("semanticIconRole", "clear")
            self.clear_button.setAccessibleName("Clear console view")
            self.clear_button.setFixedHeight(action_height)
            self.clear_button.setStyleSheet(action_style)
            self.clear_button.clicked.connect(self.clear_visible)
            header_layout.addWidget(self.clear_button)

            self.collapse_button = QToolButton(header)
            self.collapse_button.setProperty(
                "arcgravSemanticComponent",
                "console-collapse-button",
            )
            self.collapse_button.setProperty("semanticRole", "contextual")
            self.collapse_button.setIcon(semantic_icon("expand", theme=theme))
            self.collapse_button.setProperty("semanticIconRole", "expand")
            self.collapse_button.setAccessibleName("Collapse console")
            self.collapse_button.setFixedSize(action_height, action_height)
            self.collapse_button.setStyleSheet(action_style)
            self.collapse_button.clicked.connect(self.toggle_expanded)
            header_layout.insertWidget(0, self.collapse_button)
            root.addWidget(header)

            self._content = QWidget(self)
            self._content.setProperty("arcgravSemanticComponent", "console-content")
            self._content.setStyleSheet(
                'QWidget[arcgravSemanticComponent="console-content"] {'
                f"background-color: {theme.color('console-background')};"
                "border: 0px;"
                "}"
            )
            content_layout = QVBoxLayout(self._content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(0)

            self.tab_bar = QTabBar(self._content)
            self.tab_bar.setProperty(
                "arcgravSemanticComponent",
                "console-tab-bar",
            )
            self.tab_bar.setExpanding(False)
            for label in CONSOLE_TABS:
                self.tab_bar.addTab(label)
            selected_tab = resolved_tab(
                "selected",
                theme=theme,
                metrics=metrics,
                typography=typography,
            )
            self.tab_bar.setStyleSheet(
                'QTabBar[arcgravSemanticComponent="console-tab-bar"] {'
                f"background: {theme.color('console-background')};"
                "border: 0px;"
                "}"
                'QTabBar[arcgravSemanticComponent="console-tab-bar"]::tab {'
                f"background: {theme.color('console-background')};"
                f"color: {theme.color('console-muted')};"
                f"padding: {metrics.metric('space-sm')}px {metrics.metric('space-md')}px;"
                "border: 0px;"
                "}"
                'QTabBar[arcgravSemanticComponent="console-tab-bar"]::tab:hover {'
                f"color: {theme.color('console-text')};"
                "}"
                'QTabBar[arcgravSemanticComponent="console-tab-bar"]::tab:selected {'
                f"color: {theme.color('console-text')};"
                f"border-bottom: {selected_tab.underline_width_px}px solid "
                f"{selected_tab.underline_color};"
                "}"
            )
            self.tab_bar.currentChanged.connect(self._on_tab_changed)
            content_layout.addWidget(self.tab_bar)

            self._stack = QStackedWidget(self._content)
            self._stack.setProperty("arcgravSemanticComponent", "console-stack")
            self._stack.setStyleSheet(
                'QStackedWidget[arcgravSemanticComponent="console-stack"] {'
                f"background-color: {theme.color('console-background')};"
                "border: 0px;"
                "}"
            )
            for label in CONSOLE_TABS:
                view = ConsoleTextView(
                    tab=label,
                    theme=theme,
                    typography=typography,
                    metrics=metrics,
                    parent=self._stack,
                )
                view.setAccessibleName(f"{label} console")
                self._views[label] = view
                self._stack.addWidget(view)
            content_layout.addWidget(self._stack)
            root.addWidget(self._content)

            self._on_tab_changed(CONSOLE_TABS.index(self._state.active_tab))
            self._apply_expanded_state(emit_signal=False)

            queued = Qt.ConnectionType.QueuedConnection
            self._queuedBindGeneration.connect(self._bind_queued_generation, queued)
            self._queuedLiveOutput.connect(self.append_live_output, queued)
            self._queuedDiagnostic.connect(self.append_diagnostic, queued)
            self._queuedEnvironment.connect(self.set_environment, queued)
            self._queuedRawResponse.connect(self.set_raw_response, queued)
            self._queuedLiveViewReady.connect(self._schedule_live_view, queued)

        @property
        def state(self) -> BottomConsoleState:
            return self._state

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def expanded(self) -> bool:
            return self._state.expanded

        @property
        def tab_labels(self) -> tuple[str, ...]:
            return tuple(self.tab_bar.tabText(i) for i in range(self.tab_bar.count()))

        def console_view(self, tab: str) -> ConsoleTextView:
            return self._views[_require_tab(tab)]

        def queue_bind_generation(self, generation_id: str) -> None:
            """Queue generation binding onto this widget's GUI event thread."""

            generation = _require_generation_id(generation_id)
            with self._queue_lock:
                if self._closed:
                    return
                if generation != self._queue_generation:
                    self._pending_live.clear()
                    self._queue_generation = generation
            self._safe_emit(self._queuedBindGeneration, generation)

        def set_stream_live_view(self, enabled: bool) -> None:
            """Convenience entry point for callers that enable or disable both channels."""
            self.stream_input_checkbox.setChecked(enabled)
            self.stream_output_checkbox.setChecked(enabled)

        def _update_stream_channels(self) -> None:
            input_enabled = self.stream_input_checkbox.isChecked()
            output_enabled = self.stream_output_checkbox.isChecked()
            enabled = input_enabled or output_enabled
            self.live_view_control.set_enabled(enabled)
            self._state.set_live_view_channels(input_enabled=input_enabled, output_enabled=output_enabled)
            if self._stream_preferences is not None:
                self._stream_preferences["console/stream_live_input"] = int(input_enabled)
                self._stream_preferences["console/stream_live_output"] = int(output_enabled)
            self._render_active_view()
            if not enabled:
                with self._queue_lock:
                    self._pending_live.clear()
                    self._live_drain_scheduled = False
                self._live_timer.stop()

        def queue_live_view(
            self,
            generation_id: str,
            invocation_id: str,
            input_text: str | None = None,
            output_text: str | None = None,
            stream_revision: int | None = None,
            treatment_name: str | None = None,
        ) -> None:
            """Coalesce exact snapshots before posting bounded GUI-thread work.

            Producers never read or mutate Qt widgets. A token burst retains only
            the latest input/output per invocation and posts one wake-up, rather
            than an unbounded queued Qt event for every token.
            """

            generation = _require_generation_id(generation_id)
            invocation = _require_invocation_id(invocation_id)
            if input_text is not None and not isinstance(input_text, str):
                raise TypeError("input_text must be a string or None")
            if output_text is not None and not isinstance(output_text, str):
                raise TypeError("output_text must be a string or None")
            with self._queue_lock:
                if self._closed or not self.live_view_control.snapshot()[0] or generation != self._queue_generation:
                    return
                if stream_revision is not None and stream_revision != self.live_view_control.snapshot()[1]:
                    return
                previous_input, previous_output, previous_treatment = self._pending_live.get(
                    invocation, (None, None, None)
                )
                self._pending_live[invocation] = (
                    previous_input if input_text is None else input_text,
                    previous_output if output_text is None else output_text,
                    previous_treatment if treatment_name is None else treatment_name,
                )
                wake = not self._live_drain_scheduled
                self._live_drain_scheduled = True
            if wake:
                self._safe_emit(self._queuedLiveViewReady)

        def _safe_emit(self, signal, *args) -> None:
            # A late worker completion can race close/deleteLater. Its final
            # presentation update must not raise back into benchmark execution.
            with self._queue_lock:
                if self._closed:
                    return
            try:
                signal.emit(*args)
            except RuntimeError:
                with self._queue_lock:
                    self._closed = True
                    self._pending_live.clear()

        def _schedule_live_view(self) -> None:
            if not self._closed and self.live_view_control.snapshot()[0] and not self._live_timer.isActive():
                self._live_timer.start()

        def _flush_live_view(self) -> None:
            with self._queue_lock:
                if self._closed or not self.live_view_control.snapshot()[0]:
                    return
                generation = self._queue_generation
                if generation != self._state.active_generation_id:
                    self._live_timer.start()
                    return
                # Limit work per frame. Other invocations drain on subsequent
                # frames, leaving input, Close, and navigation events responsive.
                updates = [
                    self._pending_live.popitem(last=False)
                    for _ in range(min(32, len(self._pending_live)))
                ]
                more = bool(self._pending_live)
                self._live_drain_scheduled = more
            accepted = False
            if generation is not None:
                for invocation, (input_text, output_text, treatment_name) in updates:
                    accepted = self._state.set_live_view(
                        generation, invocation, input_text, output_text, treatment_name
                    ) or accepted
            if accepted and self._state.active_tab == "Live View":
                self._render_active_view(follow_output=True)
            if more:
                self._live_timer.start()

        def _bind_queued_generation(self, generation_id: str) -> None:
            with self._queue_lock:
                if self._closed or generation_id != self._queue_generation:
                    return
            self._state.bind_generation(generation_id)
            self._render_active_view()

        def queue_live_output(self, generation_id: str, text: str) -> None:
            """Queue a generation-bound live-output event without mutating widgets."""

            generation = _require_generation_id(generation_id)
            if not isinstance(text, str):
                raise TypeError("console text must be a string")
            self._safe_emit(self._queuedLiveOutput, generation, text)

        def queue_diagnostic(self, generation_id: str, text: str) -> None:
            """Queue a generation-bound diagnostic event without mutating widgets."""

            generation = _require_generation_id(generation_id)
            if not isinstance(text, str):
                raise TypeError("console text must be a string")
            self._safe_emit(self._queuedDiagnostic, generation, text)

        def queue_environment(self, text: str) -> None:
            """Queue a session-scoped Environment refresh onto the GUI event thread."""

            if not isinstance(text, str):
                raise TypeError("console text must be a string")
            self._safe_emit(self._queuedEnvironment, text)

        def queue_raw_response(
            self,
            generation_id: str,
            response: str | None,
        ) -> None:
            """Queue an exact retained-response projection onto the GUI event thread."""

            generation = _require_generation_id(generation_id)
            if response is not None and not isinstance(response, str):
                raise TypeError("raw response must be a string or None")
            self._safe_emit(self._queuedRawResponse, generation, response)

        def bind_generation(self, generation_id: str) -> None:
            generation_id = _require_generation_id(generation_id)
            with self._queue_lock:
                if self._closed:
                    return
                if generation_id != self._queue_generation:
                    self._pending_live.clear()
                self._queue_generation = generation_id
            self._state.bind_generation(generation_id)
            self._render_active_view()

        def detach_generation(self, generation_id: str) -> None:
            """Forget an unstarted generation and invalidate its queued bindings."""
            generation_id = _require_generation_id(generation_id)
            with self._queue_lock:
                if self._queue_generation == generation_id:
                    self._queue_generation = None
                    self._pending_live.clear()
                    self._live_drain_scheduled = False
            if self._state.detach_generation(generation_id):
                self._live_timer.stop()
                self._render_active_view()

        def set_live_view(
            self,
            generation_id: str,
            invocation_id: str,
            input_text: str | None = None,
            output_text: str | None = None,
            treatment_name: str | None = None,
        ) -> bool:
            if self._closed or not self.live_view_control.snapshot()[0]:
                return False
            # A final GUI-thread snapshot supersedes any pending stream snapshot
            # for the same invocation, so a delayed timer cannot roll it back.
            with self._queue_lock:
                if generation_id == self._queue_generation:
                    pending = self._pending_live.pop(invocation_id, (None, None, None))
                    if input_text is None:
                        input_text = pending[0]
                    if output_text is None:
                        output_text = pending[1]
                    if treatment_name is None:
                        treatment_name = pending[2]
            accepted = self._state.set_live_view(
                generation_id, invocation_id, input_text, output_text, treatment_name
            )
            if accepted and self._state.active_tab == "Live View":
                self._render_active_view(follow_output=True)
            return accepted

        def append_live_output(self, generation_id: str, text: str) -> bool:
            return self.append_diagnostic(generation_id, text)

        def append_diagnostic(self, generation_id: str, text: str) -> bool:
            if self._closed:
                return False
            accepted = self._state.append_diagnostic(generation_id, text)
            if accepted and self._state.active_tab == "Diagnostics":
                self._render_active_view(follow_output=True)
            return accepted

        def set_environment(self, text: str) -> None:
            if self._closed:
                return
            self._state.set_environment(text)
            if self._state.active_tab == "Environment":
                self._render_active_view()

        def append_history(self, text: str) -> None:
            """Append a GUI-thread application status without changing navigation."""
            if self._closed:
                return
            self._state.append_history(text)
            if self._state.active_tab == "History":
                self._render_active_view(follow_output=True)

        def set_raw_response(
            self,
            generation_id: str,
            response: str | None,
        ) -> bool:
            if self._closed:
                return False
            accepted = self._state.set_raw_response(generation_id, response)
            if accepted and self._state.active_tab == "Live View":
                self._render_active_view()
            return accepted

        def set_active_tab(self, tab: str) -> None:
            label = _require_tab(tab)
            index = CONSOLE_TABS.index(label)
            self._state.select_tab(label)
            if self.tab_bar.currentIndex() != index:
                self.tab_bar.setCurrentIndex(index)
            else:
                self._stack.setCurrentIndex(index)
                self._render_active_view()

        def clear_visible(self) -> None:
            if self._state.active_tab == "Live View":
                with self._queue_lock:
                    self._pending_live.clear()
            self._state.clear_visible()
            self._render_active_view()

        def toggle_expanded(self) -> None:
            self.set_expanded(not self._state.expanded)

        def set_expanded(self, expanded: bool) -> None:
            if not isinstance(expanded, bool):
                raise TypeError("expanded must be a boolean")
            if expanded:
                restored_height = self._state.expand()
                self._apply_expanded_state()
                self.expandedHeightRequested.emit(restored_height)
            else:
                self._state.collapse()
                self._apply_expanded_state()

        def record_splitter_height(self, height: int) -> None:
            """Record caller-observed splitter height as presentation-only state."""

            self._state.resize(height)
            self._apply_expanded_state()

        def _on_tab_changed(self, index: int) -> None:
            if not 0 <= index < len(CONSOLE_TABS):
                return
            label = CONSOLE_TABS[index]
            self._state.select_tab(label)
            self._stack.setCurrentIndex(index)
            self._render_active_view()
            self.activeTabChanged.emit(label)

        def _render_active_view(self, *, follow_output: bool = False) -> None:
            tab = self._state.active_tab
            self.clear_button.setEnabled(tab != "History")
            self._views[tab].set_source_text(
                self._state.visible_text,
                follow_output=follow_output and tab in {"Live View", "Diagnostics", "History"},
            )

        def closeEvent(self, event) -> None:
            with self._queue_lock:
                self._closed = True
                self._pending_live.clear()
            self._live_timer.stop()
            super().closeEvent(event)

        def _apply_expanded_state(self, *, emit_signal: bool = True) -> None:
            expanded = self._state.expanded
            self._content.setVisible(expanded)
            icon_role = "expand" if expanded else "collapse"
            self.collapse_button.setText("")
            self.collapse_button.setIcon(
                semantic_icon(icon_role, theme=self._theme)
            )
            self.collapse_button.setProperty("semanticIconRole", icon_role)
            self.collapse_button.setAccessibleName(
                "Collapse console" if expanded else "Expand console"
            )
            if emit_signal:
                self.expandedChanged.emit(expanded)

else:

    class BottomConsoleWidget:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for BottomConsoleWidget")
