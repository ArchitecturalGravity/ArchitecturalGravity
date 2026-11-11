"""Long Current Run identifiers remain readable and copyable on narrow desktops."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.shell.window import PYSIDE6_AVAILABLE

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication
    from AgMark.gui.widgets.wrapping_text import WrappingText
    from AgMark.shared.software_testing.frontends.gui import test_shell_runtime_replacement_rendered_qt as fixtures


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is unavailable")
class CurrentRunWrappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        fixtures.apply_application_theme(cls.application)

    def settle(self):
        for _ in range(20):
            self.application.processEvents()

    def test_identifier_wraps_without_changing_clipboard_text(self):
        text = "sha256:" + "abcdef0123456789" * 4 + "<literal>&value"
        widget = WrappingText(text)
        self.addCleanup(widget.deleteLater)
        widget.resize(100, widget.heightForWidth(100))
        widget.show()
        self.settle()
        self.assertGreater(widget.height(), widget.fontMetrics().height() * 3)
        self.assertLessEqual(widget.document().size().height(), widget.viewport().height())
        widget.selectAll()
        widget.copy()
        self.assertEqual(self.application.clipboard().text(), text)
        self.assertEqual(widget.text(), text)
        widget.resize(400, widget.heightForWidth(400))
        self.settle()
        self.assertLess(widget.minimumHeight(), widget.heightForWidth(100))

    def test_summary_values_fit_after_repeated_narrow_and_wide_resizes(self):
        fixture = fixtures.RenderedShellRuntimeReplacementTests()
        window = fixture._window()
        self.addCleanup(fixture.doCleanups)
        fingerprint = "sha256:" + "a" * 64
        filename = "a_long_treatment_filename_without_spaces.txt"
        window.set_current_run_projection(fixtures.CurrentRunProjection(
            run_identity="run-wrapping", state_label="Prepared", state_tone="active",
            timestamp="2026-09-26T00:00:00Z",
            execution_boundary=fixtures.ExecutionBoundaryProjection(
                benchmark="authority_resolution_benchmark_v2.0.0",
                runner="deterministic_mock_model_v1.0.0", model="model-a",
                cases="arcgrav.authority-resolution.case-set.core@1.0.0",
                boundary_fingerprint=fingerprint),
            run_plan=fixtures.RunPlanProjection(
                treatments="1", cases="24", execution="Canonical plan: " + fingerprint,
                evaluation="Registered scorer", outputs="retained evidence",
                treatment_files=(filename, "arb-xml", "arb-yaml", "arb-markdown", "arb-common-prose")),
        ))
        refreshes = []
        window.current_run_scroll._refresh_timer.timeout.connect(lambda: refreshes.append(None))
        for width, height, columns in (
            (1180, 812, 3), (1440, 812, 3), (900, 812, 2), (700, 812, 1),
            (900, 500, 1), (900, 812, 2), (1440, 812, 3), (1180, 812, 3),
        ):
            window.resize(width, height)
            self.settle()
            settled_refresh_count = len(refreshes)
            self.settle()
            self.assertEqual(len(refreshes), settled_refresh_count,
                             f"summary reflow did not settle at {width}x{height}")
            self.assertEqual(window.current_run_region._columns, columns)
            self.assertEqual(window.current_run_scroll.horizontalScrollBar().maximum(), 0)
            required = window.current_run_region.layout().totalHeightForWidth(
                window.current_run_scroll.viewport().width())
            budget = window.workspace.height() - 240 - window.workspace_tabs.tabBar().sizeHint().height()
            if required <= budget:
                self.assertEqual(window.current_run_scroll.verticalScrollBar().maximum(), 0)
            cards = window.current_run_region.cards
            for card in cards:
                self.assertGreaterEqual(card.width(), card.minimumWidth())
            if columns == 1:
                self.assertLess(cards[0].geometry().bottom(), cards[1].geometry().top())
                self.assertLess(cards[1].geometry().bottom(), cards[2].geometry().top())
            readers = [value for _, value in window.execution_boundary_rows + window.run_plan_rows]
            readers.extend(window.treatment_file_labels)
            readers.append(window.current_run_timestamp_label)
            for reader in readers:
                with self.subTest(width=width, text=reader.text()):
                    self.assertGreaterEqual(reader.width(), 1)
                    self.assertLessEqual(reader.document().size().height(), reader.viewport().height())
                    self.assertLessEqual(reader.document().idealWidth(), reader.viewport().width() + 1)
            self.assertNotIn("Boundary fingerprint:", [label.text() for label, _ in window.execution_boundary_rows])
            self.assertEqual(window.treatment_file_labels[0].text(), filename)

        window.resize(1180, 500)
        self.settle()
        self.assertGreater(window.current_run_scroll.verticalScrollBar().maximum(), 0)
        self.assertGreater(window.current_run_scroll.height(), 0)
        self.assertGreater(window.workspace_tabs.height(), 0)
        window.resize(1180, 812)
        self.settle()
        self.assertEqual(window.current_run_scroll.verticalScrollBar().maximum(), 0)
