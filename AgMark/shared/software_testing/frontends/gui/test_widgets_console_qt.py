"""Conformance tests for the concrete PySide6 bottom-console widget surface."""

from __future__ import annotations

import os
import time
from threading import Thread
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.design_system.console import resolved_console_presentation
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, semantic_icon
from AgMark.gui.widgets.console import (
    BottomConsoleState,
    BottomConsoleWidget,
    CONSOLE_TABS,
    LAST_EXPANDED_HEIGHT_KEY,
    PYSIDE6_AVAILABLE,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QPlainTextEdit


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class BottomConsoleWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.preferences: dict[str, int] = {"console/stream_live_input": 1, "console/stream_live_output": 1}
        self.widget = BottomConsoleWidget(preferences=self.preferences)
        self.addCleanup(self.widget.deleteLater)
        self.widget.set_expanded(True)

    def _wait_for_live_drain(self):
        deadline = time.monotonic() + 2
        while self.widget._pending_live and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.widget._pending_live, "queued live updates did not drain")

    def test_stream_toggle_drops_queued_updates_and_persists_across_widgets(self):
        self.widget.bind_generation('stream-generation')
        self.widget.queue_live_view('stream-generation', 'observation', output_text='queued before toggle')
        self.widget.set_stream_live_view(False)
        self.widget.queue_live_view('stream-generation', 'observation', output_text='disabled')
        QApplication.processEvents()
        self.assertEqual({}, self.widget._pending_live)
        self.assertFalse(self.widget._live_timer.isActive())
        self.assertFalse(self.widget.set_live_view('stream-generation', 'observation', output_text='terminal off'))
        other = BottomConsoleWidget(preferences=self.preferences)
        self.addCleanup(other.deleteLater)
        self.assertFalse(other.stream_output_checkbox.isChecked())
        self.widget.set_stream_live_view(True)
        self.widget.queue_live_view('stream-generation', 'late', output_text='old revision', stream_revision=0)
        self.assertEqual({}, self.widget._pending_live)
        self.widget.bind_generation('next-stream-generation')
        self.widget.queue_live_view('stream-generation', 'old', output_text='stale')
        self.widget.queue_live_view('next-stream-generation', 'new', output_text='resumed')
        self.widget._flush_live_view()
        self.assertIn('resumed', self.widget.state.visible_text)
        self.assertNotIn('stale', self.widget.state.visible_text)
        self.assertEqual(1, self.preferences['console/stream_live_output'])

    def test_independent_channels_filter_pending_and_final_snapshots(self):
        self.widget.bind_generation("channels")
        self.widget.queue_live_view("channels", "one", input_text="exact prompt", treatment_name="Treatment A")
        self.widget.queue_live_view("channels", "one", output_text="partial")
        revision = self.widget.live_view_control.snapshot()[1]
        self.widget.stream_input_checkbox.setChecked(False)
        self.assertEqual(revision, self.widget.live_view_control.snapshot()[1])
        self.widget._flush_live_view()
        self.assertEqual("Treatment A - Output:\npartial", self.widget.state.visible_text)
        self.widget.stream_input_checkbox.setChecked(True)
        self.widget.stream_output_checkbox.setChecked(False)
        self.assertEqual("Treatment A - Input:\nexact prompt", self.widget.state.visible_text)
        self.widget.queue_live_view("channels", "one", output_text="last partial")
        self.widget.set_live_view("channels", "one", output_text="exact final")
        self.widget.stream_output_checkbox.setChecked(True)
        expected = "Treatment A - Input:\nexact prompt\n\nTreatment A - Output:\nexact final"
        self.assertEqual(expected, self.widget.state.visible_text)
        self.widget.set_stream_live_view(False)
        self.assertEqual("", self.widget.state.visible_text)
        self.widget.set_stream_live_view(True)
        self.assertEqual(expected, self.widget.state.visible_text)
        self.widget.bind_generation("next")
        self.widget.set_live_view("next", "one", output_text="new", treatment_name="Treatment B")
        self.assertNotIn("Treatment A", self.widget.state.visible_text)
        self.assertIn("Treatment B - Output:\nnew", self.widget.state.visible_text)

    def test_legacy_preference_does_not_enable_channels_and_new_preferences_are_independent(self):
        preferences = {"console/stream_live_view": 1}
        console = BottomConsoleWidget(preferences=preferences)
        self.addCleanup(console.close)
        self.assertFalse(console.stream_input_checkbox.isChecked())
        self.assertFalse(console.stream_output_checkbox.isChecked())
        console.stream_input_checkbox.setChecked(True)
        restored = BottomConsoleWidget(preferences=preferences)
        self.addCleanup(restored.close)
        self.assertTrue(restored.stream_input_checkbox.isChecked())
        self.assertFalse(restored.stream_output_checkbox.isChecked())

    def test_toggle_left_and_stream_control_immediately_before_clear(self) -> None:
        header_layout = self.widget.collapse_button.parentWidget().layout()
        self.assertIs(header_layout.itemAt(0).widget(), self.widget.collapse_button)
        self.assertIs(header_layout.itemAt(1).widget(), self.widget.console_title_label)
        self.assertIs(header_layout.itemAt(header_layout.count() - 2).widget(), self.widget.stream_live_view_group)
        self.assertIs(header_layout.itemAt(header_layout.count() - 1).widget(), self.widget.clear_button)
        for _ in range(3):
            self.widget.collapse_button.click()
            self.assertEqual(self.widget.collapse_button.accessibleName(), "Expand console")
            self.assertEqual(self.widget.collapse_button.property("semanticIconRole"), "collapse")
            self.widget.collapse_button.click()
            self.assertEqual(self.widget.collapse_button.accessibleName(), "Collapse console")
            self.assertEqual(self.widget.collapse_button.property("semanticIconRole"), "expand")

    def test_reference_header_tabs_and_presentation_semantics(self) -> None:
        self.assertEqual(self.widget.tab_labels, CONSOLE_TABS)
        self.assertEqual(self.widget.authority_semantics, "presentation-only")
        self.assertEqual(self.widget.clear_button.text(), "Clear")
        self.assertFalse(self.widget.clear_button.icon().isNull())
        self.assertEqual(
            self.widget.clear_button.property("semanticIconRole"),
            "clear",
        )
        self.assertFalse(self.widget.collapse_button.icon().isNull())
        self.assertEqual(
            self.widget.collapse_button.property("semanticIconRole"),
            "expand",
        )
        self.assertEqual(self.widget.collapse_button.accessibleName(), "Collapse console")
        self.assertEqual(self.widget.tab_bar.currentIndex(), 0)

    def test_console_chrome_uses_semantic_surfaces_and_exact_icon_family(self) -> None:
        theme = DEFAULT_LIGHT_THEME
        header = self.widget.clear_button.parentWidget()
        self.assertIsNotNone(header)
        assert header is not None

        self.assertEqual(
            header.property("arcgravSemanticComponent"),
            "console-header",
        )
        self.assertEqual(self.widget.console_title_label.text(), "Console")
        self.assertEqual(
            self.widget.console_title_label.property("arcgravSemanticComponent"),
            "console-title",
        )
        self.assertEqual(
            self.widget.clear_button.property("arcgravSemanticComponent"),
            "console-clear-button",
        )
        self.assertEqual(
            self.widget.collapse_button.property("arcgravSemanticComponent"),
            "console-collapse-button",
        )
        self.assertEqual(self.widget.clear_button.text(), "Clear")
        self.assertEqual(self.widget.collapse_button.text(), "")

        self.assertIn(theme.color("surface-panel"), header.styleSheet())
        self.assertIn(theme.color("border-default"), header.styleSheet())
        self.assertIn(theme.color("focus-ring"), self.widget.clear_button.styleSheet())
        self.assertIn(
            'arcgravSemanticComponent="console-clear-button"',
            self.widget.clear_button.styleSheet(),
        )
        self.assertIn(
            'arcgravSemanticComponent="console-collapse-button"',
            self.widget.collapse_button.styleSheet(),
        )

        expected_clear = semantic_icon("clear", theme=theme).pixmap(18, 18).toImage()
        actual_clear = self.widget.clear_button.icon().pixmap(18, 18).toImage()
        self.assertEqual(actual_clear, expected_clear)

        expected_collapse = semantic_icon("expand", theme=theme).pixmap(18, 18).toImage()
        actual_collapse = self.widget.collapse_button.icon().pixmap(18, 18).toImage()
        self.assertEqual(actual_collapse, expected_collapse)

        tab_style = self.widget.tab_bar.styleSheet()
        self.assertIn(
            'arcgravSemanticComponent="console-tab-bar"',
            tab_style,
        )
        self.assertIn(theme.color("console-background"), tab_style)
        self.assertIn(theme.color("console-text"), tab_style)
        self.assertIn(theme.color("accent-primary"), tab_style)
        self.assertNotIn("#semanticConsole", tab_style)

    def test_console_views_are_read_only_selectable_non_wrapping_surfaces(self) -> None:
        for label in CONSOLE_TABS:
            with self.subTest(label=label):
                view = self.widget.console_view(label)
                self.assertTrue(view.isReadOnly())
                self.assertEqual(
                    view.lineWrapMode(),
                    QPlainTextEdit.LineWrapMode.NoWrap,
                )
                flags = view.textInteractionFlags()
                self.assertTrue(flags & Qt.TextInteractionFlag.TextSelectableByMouse)
                self.assertTrue(flags & Qt.TextInteractionFlag.TextSelectableByKeyboard)
                self.assertGreater(view.line_number_area_width(), 0)
                self.assertEqual(view.authority_semantics, "presentation-only")
                self.assertEqual(
                    view.property("arcgravSemanticComponent"),
                    "console-text-view",
                )
                style = view.styleSheet()
                self.assertIn(DEFAULT_LIGHT_THEME.color("console-background"), style)
                self.assertIn(DEFAULT_LIGHT_THEME.color("console-muted"), style)
                self.assertIn(DEFAULT_LIGHT_THEME.color("console-info"), style)
                self.assertIn("QScrollBar:vertical", style)
                self.assertIn("QScrollBar:horizontal", style)
                self.assertIn("QScrollBar::handle:vertical", style)
                self.assertIn("QScrollBar::handle:horizontal", style)

    def test_long_content_scrollbars_remain_local_to_console_viewport(self) -> None:
        self.widget.resize(720, 260)
        self.widget.show()
        self._application.processEvents()

        header = self.widget.clear_button.parentWidget()
        self.assertIsNotNone(header)
        assert header is not None
        baseline_widget_size = self.widget.size()
        baseline_header_geometry = header.geometry()
        baseline_tab_geometry = self.widget.tab_bar.geometry()

        self.widget.bind_generation("generation-overflow")
        long_line = "[12:00:00]   [INFO]   | " + ("x" * 1600)
        payload = "\n".join(f"{long_line}{index}" for index in range(180))
        self.assertTrue(
            self.widget.set_live_view("generation-overflow", "one", "prompt", payload)
        )
        self._application.processEvents()

        view = self.widget.console_view("Live Output")
        self.assertEqual(
            view.sizeAdjustPolicy(),
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored,
        )
        self.assertEqual(
            view.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            view.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        horizontal = view.horizontalScrollBar()
        vertical = view.verticalScrollBar()
        self.assertGreater(horizontal.maximum(), 0)
        self.assertGreater(vertical.maximum(), 0)

        self.assertEqual(self.widget.size(), baseline_widget_size)
        self.assertEqual(header.geometry(), baseline_header_geometry)
        self.assertEqual(self.widget.tab_bar.geometry(), baseline_tab_geometry)

        view_geometry = view.geometry()
        horizontal.setValue(horizontal.maximum())
        vertical.setValue(vertical.maximum())
        self._application.processEvents()

        self.assertEqual(view.geometry(), view_geometry)
        self.assertEqual(self.widget.size(), baseline_widget_size)
        self.assertEqual(header.geometry(), baseline_header_geometry)
        self.assertEqual(self.widget.tab_bar.geometry(), baseline_tab_geometry)
        self.assertEqual(
            self.widget.state.active_generation_id,
            "generation-overflow",
        )

    def _formatted_color_at(self, label: str, text: str, needle: str) -> str | None:
        view = self.widget.console_view(label)
        view.set_source_text(text)
        self._application.processEvents()
        position = text.index(needle)
        block = view.document().findBlock(position)
        relative = position - block.position()
        for span in block.layout().formats():
            if span.start <= relative < span.start + span.length:
                return span.format.foreground().color().name().upper()
        return None

    def test_default_semantic_rendering_preserves_source_characters(self) -> None:
        presentation = resolved_console_presentation()

        live = "[12:00:00]   [INFO]   | ready\n"
        self.assertEqual(
            self._formatted_color_at("Diagnostics", live, "[12:00:00]"),
            presentation.muted,
        )
        self.assertEqual(
            self._formatted_color_at("Diagnostics", live, "[INFO]"),
            presentation.info,
        )
        self.assertEqual(self.widget.console_view("Diagnostics").toPlainText(), live)

        progress = "[12:00:01]   [PROGRESS]   | 2/4\n"
        self.assertEqual(
            self._formatted_color_at("Diagnostics", progress, "[PROGRESS]"),
            presentation.progress,
        )

        diagnostic = "[2026-09-21T12:00:00Z]   WARNING   redacted value\n"
        self.assertEqual(
            self._formatted_color_at("Diagnostics", diagnostic, "WARNING"),
            presentation.warning,
        )
        self.assertEqual(
            self.widget.console_view("Diagnostics").toPlainText(),
            diagnostic,
        )

        raw = '{"answer":"ok","count":42}'
        self.assertEqual(
            self._formatted_color_at("Live View", raw, '"answer"'),
            presentation.warning,
        )
        self.assertEqual(
            self._formatted_color_at("Live View", raw, '"ok"'),
            presentation.progress,
        )
        self.assertEqual(
            self._formatted_color_at("Live View", raw, "42"),
            presentation.info,
        )
        self.assertEqual(self.widget.console_view("Live View").toPlainText(), raw)

        environment = "[startup]   WARNING   executable unavailable\n"
        self.assertEqual(
            self._formatted_color_at("Environment", environment, "WARNING"),
            presentation.warning,
        )
        self.assertEqual(
            self.widget.console_view("Environment").toPlainText(),
            environment,
        )

    def test_worker_queue_marshals_updates_before_widget_mutation(self) -> None:
        def produce() -> None:
            self.widget.queue_bind_generation("generation-worker")
            self.widget.queue_live_output("generation-worker", "progress\n")
            self.widget.queue_live_view("generation-worker", "one", input_text="raw prompt")
            for count in range(2000):
                self.widget.queue_live_view("generation-worker", "one", output_text=str(count))
            self.widget.queue_diagnostic("generation-worker", "[redacted]\n")
            self.widget.queue_environment("repository ready\n")

        worker = Thread(target=produce)
        worker.start()
        worker.join()
        self.assertIsNone(self.widget.state.active_generation_id)
        self.assertEqual(len(self.widget._pending_live), 1)
        self._wait_for_live_drain()
        self.assertEqual(self.widget.state.active_generation_id, "generation-worker")
        self.assertEqual(self.widget.console_view("Live View").toPlainText(), "Input:\nraw prompt\n\nOutput:\n1999")
        self.widget.set_active_tab("Diagnostics")
        self.assertEqual(self.widget.console_view("Diagnostics").toPlainText(), "progress\n[redacted]\n")
        self.widget.set_active_tab("Environment")
        self.assertEqual(self.widget.console_view("Environment").toPlainText(), "repository ready\n")

    def test_environment_is_available_before_generation_and_survives_binding(self) -> None:
        self.assertIsNone(self.widget.state.active_generation_id)

        self.widget.set_environment("[startup]   INFO   repository ready\n")
        self.widget.set_active_tab("Environment")
        self.assertEqual(
            self.widget.console_view("Environment").toPlainText(),
            "[startup]   INFO   repository ready\n",
        )

        self.widget.bind_generation("generation-a")
        self.assertEqual(
            self.widget.console_view("Environment").toPlainText(),
            "[startup]   INFO   repository ready\n",
        )

        self.widget.clear_visible()
        self.assertEqual(self.widget.console_view("Environment").toPlainText(), "")
        self.widget.set_environment("[startup]   INFO   refreshed\n")
        self.assertEqual(
            self.widget.console_view("Environment").toPlainText(),
            "[startup]   INFO   refreshed\n",
        )

    def test_generation_bound_updates_reject_stale_events_at_widget_boundary(self) -> None:
        self.widget.bind_generation("generation-a")
        self.widget.queue_live_view("generation-a", "one", "old prompt", "old partial")
        self.widget.bind_generation("generation-b")
        self.widget.queue_live_view("generation-a", "one", output_text="stale")
        self.widget.queue_live_view("generation-b", "two", "new prompt", "new partial")
        self._wait_for_live_drain()
        self.assertEqual(self.widget.console_view("Live View").toPlainText(), "Input:\nnew prompt\n\nOutput:\nnew partial")
        self.assertFalse(self.widget.set_live_view("generation-a", "one", output_text="stale"))
        self.assertFalse(self.widget.append_diagnostic("generation-a", "stale"))

    def test_final_snapshot_supersedes_queued_partial_without_duplicate(self) -> None:
        self.widget.bind_generation("generation-a")
        self.widget.queue_live_view("generation-a", "one", "prompt", "partial")
        self.widget.set_live_view("generation-a", "one", output_text="final")
        self._wait_for_live_drain()
        self.assertEqual(self.widget.console_view("Live View").toPlainText(), "Input:\nprompt\n\nOutput:\nfinal")

    def test_raw_response_compatibility_retains_projection_with_local_clear(self) -> None:
        self.widget.bind_generation("generation-a")
        exact = '{"answer":"verbatim  value"}'
        self.assertTrue(self.widget.set_raw_response("generation-a", exact))
        view = self.widget.console_view("Live View")
        self.assertEqual(view.toPlainText(), "Input:\nInput unavailable.\n\nOutput:\n" + exact)
        self.assertEqual(self.widget.state.retained_raw_response, exact)
        self.widget.clear_visible()
        self.assertEqual(view.toPlainText(), "")
        self.assertEqual(self.widget.state.retained_raw_response, exact)

    def test_copy_preserves_unicode_spaces_and_original_line_endings(self) -> None:
        self.widget.bind_generation("generation-a")
        prompt = "  raw\r\n雪🙂\t\rnext\n"
        output = "answer\r\n  kept  "
        self.widget.set_live_view("generation-a", "one", prompt, output)
        view = self.widget.console_view("Live View")
        expected = "Input:\n" + prompt + "\n\nOutput:\n" + output
        view.selectAll()
        view.copy()
        self.assertEqual(QApplication.clipboard().text(), expected)
        cursor = view.textCursor()
        # Select the emoji using Qt's UTF-16 positions after the CRLF boundary.
        displayed = view.toPlainText()
        begin = len(displayed[:displayed.index("🙂")].encode("utf-16-le")) // 2
        cursor.setPosition(begin)
        cursor.setPosition(begin + 2, QTextCursor.MoveMode.KeepAnchor)
        view.setTextCursor(cursor)
        view.copy()
        self.assertEqual(QApplication.clipboard().text(), "🙂")
        self.widget.set_live_view("generation-a", "one", output_text=output + "🙂")
        view.selectAll()
        view.copy()
        self.assertEqual(QApplication.clipboard().text(), expected + "🙂")

    def test_scroll_and_selection_survive_streaming_updates(self) -> None:
        self.widget.resize(720, 260)
        self.widget.show()
        self.widget.bind_generation("generation-a")
        output = "\n".join("line " + str(i) for i in range(120))
        self.widget.set_live_view("generation-a", "one", "prompt", output)
        self._application.processEvents()
        view = self.widget.console_view("Live View")
        bar = view.verticalScrollBar()
        bar.setValue(0)
        cursor = view.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        view.setTextCursor(cursor)
        self.widget.set_live_view("generation-a", "one", output_text=output + "\nmore")
        self.assertEqual(bar.value(), 0)
        self.assertEqual(view.textCursor().selectedText(), "Input")
        cursor.clearSelection()
        view.setTextCursor(cursor)
        bar.setValue(bar.maximum())
        self.widget.set_live_view("generation-a", "one", output_text=output + "\nmore\nlast")
        self.assertEqual(bar.value(), bar.maximum())

    def test_queue_ignores_close_and_deleted_widget_updates(self) -> None:
        self.widget.bind_generation("generation-a")
        self.widget.queue_live_view("generation-a", "one", "prompt", "partial")
        self.widget.close()
        self.widget.queue_live_view("generation-a", "one", output_text="later")
        self.widget.queue_diagnostic("generation-a", "later")
        QTest.qWait(40)
        self.assertFalse(self.widget._pending_live)
        self.assertEqual(self.widget.state.visible_text, "")
        self._cleanups.clear()
        self.widget.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        # The Python object can outlive its QObject while a worker is ending.
        self.widget.queue_live_view("generation-a", "one", output_text="late")

    def test_queued_generation_changes_cannot_restore_old_binding(self) -> None:
        self.widget.queue_bind_generation("generation-a")
        self.widget.queue_live_view("generation-a", "one", "old", "old")
        self.widget.queue_bind_generation("generation-b")
        self.widget.queue_live_view("generation-b", "two", "new", "new")
        self._wait_for_live_drain()
        self.assertEqual(self.widget.state.active_generation_id, "generation-b")
        self.assertEqual(self.widget.state.visible_text, "Input:\nnew\n\nOutput:\nnew")

    def test_many_invocations_drain_in_bounded_frames_without_loss(self) -> None:
        self.widget.bind_generation("generation-a")
        for index in range(70):
            self.widget.queue_live_view("generation-a", str(index), str(index), str(index))
        self.widget._flush_live_view()
        self.assertEqual(self.widget.state.visible_text.count("Input:"), 32)
        self.assertEqual(len(self.widget._pending_live), 38)
        self._wait_for_live_drain()
        self.assertEqual(self.widget.state.visible_text.count("Input:"), 70)
        self.assertFalse(self.widget._pending_live)

    def test_deleted_without_close_does_not_raise_into_worker(self) -> None:
        widget = BottomConsoleWidget(preferences={})
        widget.bind_generation("generation-a")
        widget.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        failures: list[Exception] = []

        def produce() -> None:
            try:
                widget.queue_live_view("generation-a", "one", "prompt", "late")
                widget.queue_diagnostic("generation-a", "late")
            except Exception as exc:
                failures.append(exc)

        worker = Thread(target=produce)
        worker.start()
        worker.join()
        self.assertEqual(failures, [])

    def test_collapse_expand_and_splitter_height_remain_presentation_state(self) -> None:
        self.widget.bind_generation("generation-a")
        self.widget.record_splitter_height(333)
        self.assertEqual(self.preferences[LAST_EXPANDED_HEIGHT_KEY], 333)
        self.assertEqual(self.widget.state.active_generation_id, "generation-a")

        self.widget.set_expanded(False)
        self.assertFalse(self.widget.expanded)
        self.assertEqual(
            self.widget.collapse_button.property("semanticIconRole"),
            "collapse",
        )
        self.assertEqual(
            self.widget.collapse_button.icon().pixmap(18, 18).toImage(),
            semantic_icon("collapse", theme=DEFAULT_LIGHT_THEME).pixmap(18, 18).toImage(),
        )
        self.assertEqual(self.widget.collapse_button.text(), "")
        self.assertEqual(self.widget.collapse_button.accessibleName(), "Expand console")
        self.assertEqual(self.widget.state.active_generation_id, "generation-a")

        restored: list[int] = []
        self.widget.expandedHeightRequested.connect(restored.append)
        self.widget.set_expanded(True)
        self.assertTrue(self.widget.expanded)
        self.assertEqual(
            self.widget.collapse_button.property("semanticIconRole"),
            "expand",
        )
        self.assertEqual(restored, [333])
        self.assertEqual(self.widget.state.active_generation_id, "generation-a")

        restored_state = BottomConsoleState(preferences=self.preferences)
        self.assertEqual(restored_state.last_nonzero_expanded_height, 333)

    def test_tab_selection_changes_only_local_presentation_target(self) -> None:
        self.widget.bind_generation("generation-a")
        for label in CONSOLE_TABS:
            self.widget.set_active_tab(label)
            self.assertEqual(self.widget.state.active_tab, label)
            self.assertEqual(self.widget.state.active_generation_id, "generation-a")


if __name__ == "__main__":
    unittest.main()
