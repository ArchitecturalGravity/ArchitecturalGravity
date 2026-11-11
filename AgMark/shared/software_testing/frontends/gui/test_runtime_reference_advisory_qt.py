"""Capture runtime advisories are visible, accessible, refreshable, and nonblocking."""
from dataclasses import replace
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True
    from AgMark.gui.application.projector import SharedApplicationProjector
    from AgMark.gui.shell.projections import CurrentRunProjection
    from AgMark.shared.software_testing.frontends.gui import test_shell_runtime_replacement_rendered_qt as shell_fixture
    from AgMark.shared.software_testing.integration.test_runtime_reference_planning import planning_fixture
    from AgMark.shared.adapters.Codex_CLI import load_registration
    from AgMark.shared.telemetry.runtime_reference import UPDATE_EXTENSION


@unittest.skipUnless(PYSIDE6_AVAILABLE, 'PySide6 is required for actual advisory widget verification')
class RuntimeReferenceAdvisoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        shell_fixture.apply_application_theme(cls.qt)

    def setUp(self):
        self.owner = shell_fixture.RenderedShellRuntimeReplacementTests()
        create_window = shell_fixture.BenchmarkShellWindow
        with patch.object(shell_fixture, 'BenchmarkShellWindow',
                side_effect=lambda **kwargs: create_window(**kwargs,
                    on_accept_plan=lambda: None, on_start_benchmark=lambda: None,
                    on_delete_run=lambda _run_id: None)):
            self.window = self.owner._window()
        self.addCleanup(self.owner.doCleanups)
        self.reference = load_registration()['extensions'][UPDATE_EXTENSION]['reference_runtime_version']

    def projection(self, version='9.9.9', *, metadata=True, mode='native', update=None):
        session, request = planning_fixture(version=version, metadata=metadata, mode=mode, update=update)
        plan = session.build_plan(request)
        execution, run_plan = SharedApplicationProjector._plan_summary(None, plan, request)
        return CurrentRunProjection(run_identity='reference-plan', state_label='Prepared', state_tone='active',
            timestamp='2026-11-04T00:00:00Z', execution_boundary=execution, run_plan=run_plan,
            accept_plan_available=True, start_benchmark_available=True)

    def show_projection(self, projection):
        self.window.set_current_run_projection(projection)
        for _ in range(3):
            self.qt.processEvents()

    def test_mismatch_has_warning_icon_and_accessible_text_without_disabling_actions(self):
        for mode in ('native', 'wsl'):
            with self.subTest(mode=mode):
                projection = self.projection(mode=mode)
                self.show_projection(projection)
                notice = self.window.capture_runtime_advisory
                icon = self.window.capture_runtime_advisory_icon
                text = self.window.capture_runtime_advisory_text
                self.assertTrue(notice.isVisible())
                self.assertEqual('captureRuntimeAdvisory', notice.objectName())
                self.assertEqual('presentation-only', notice.property('authoritySemantics'))
                self.assertEqual('warning', notice.property('statusTone'))
                self.assertEqual('status-warning', icon.property('iconRole'))
                self.assertFalse(icon.pixmap().isNull())
                self.assertIn('mismatch', icon.accessibleName())
                self.assertEqual(text.text(), text.accessibleName())
                self.assertIn('9.9.9', text.text())
                self.assertIn(self.reference, text.text())
                self.assertIn('does not block', text.text())
                self.assertTrue(self.window.accept_plan_button.isEnabled())
                self.assertTrue(self.window.start_benchmark_button.isEnabled())
                details = dict(projection.execution_boundary.runtime_details)
                self.assertEqual('9.9.9', details['Runtime version'])
                self.assert_runtime_details(projection)

    def assert_runtime_details(self, projection):
        rendered = {label.text(): value for label, value in self.window.execution_boundary_rows}
        expected = dict(projection.execution_boundary.runtime_details)
        plan_labels = {label.text() for label in self.window.run_plan_card.findChildren(QLabel)}
        self.assertFalse(any(label.text().endswith('Outputs') for label, _ in self.window.run_plan_rows))
        for name in ('Runtime version', 'Capture'):
            self.assertNotIn(name, plan_labels)
            self.assertNotIn(name, dict(projection.run_plan.execution_details))
            if name not in expected:
                self.assertNotIn(name + ':', rendered)
                continue
            value = rendered[name + ':']
            self.assertEqual(expected[name], value.text())
            self.assertEqual(name, value.accessibleName())
            self.assertTrue(value.isVisible())
            self.assertTrue(self.window.execution_boundary_card.isAncestorOf(value))
            self.assertFalse(self.window.run_plan_card.isAncestorOf(value))
        self.assertNotIn('Selected runtime version:', rendered)
        self.assertNotIn('Capture update reference:', rendered)
        self.assertNotIn('Capture version:', rendered)
        self.assertNotIn('Boundary fingerprint:', rendered)
        self.assertNotIn('Cases:', rendered)
        self.assertNotIn(projection.execution_boundary.boundary_fingerprint,
            [value.text() for value in rendered.values()])

    def test_matching_unknown_and_undeclared_replacements_remove_stale_warning(self):
        cases = (('9.9.9', True, 'warning'), (self.reference, True, None),
                 (None, True, 'neutral'), ('9.9.9', False, None), ('0.166.0-alpha.1', True, None))
        for version, metadata, tone in cases:
            with self.subTest(version=version, metadata=metadata):
                projection = self.projection(version, metadata=metadata)
                self.show_projection(projection)
                self.assert_runtime_details(projection)
                if tone is None:
                    self.assertIsNone(self.window.capture_runtime_advisory)
                    self.assertIsNone(self.window.capture_runtime_advisory_icon)
                else:
                    self.assertEqual(tone, self.window.capture_runtime_advisory.property('statusTone'))
                    self.assertEqual('status-' + tone, self.window.capture_runtime_advisory_icon.property('iconRole'))
                    if tone == 'neutral':
                        self.assertIn('could not be compared', self.window.capture_runtime_advisory_text.text())
                        self.assertNotIn('version mismatch', self.window.capture_runtime_advisory_text.text())
                self.assertTrue(self.window.accept_plan_button.isEnabled())
                self.assertTrue(self.window.start_benchmark_button.isEnabled())

    def test_advisory_does_not_enable_actions_blocked_for_other_reasons(self):
        projection = replace(self.projection(), accept_plan_available=False, start_benchmark_available=False)
        self.show_projection(projection)
        self.assertTrue(self.window.capture_runtime_advisory.isVisible())
        self.assertFalse(self.window.accept_plan_button.isEnabled())
        self.assertFalse(self.window.start_benchmark_button.isEnabled())

    def test_runtime_details_remain_readable_after_repeated_resizes(self):
        projection = self.projection()
        self.show_projection(projection)
        for width in (1440, 1180, 900, 700, 1440):
            with self.subTest(width=width):
                self.window.resize(width, 812)
                for _ in range(20):
                    self.qt.processEvents()
                self.assert_runtime_details(projection)
                for label, value in self.window.execution_boundary_rows:
                    if label.text() in {'Runtime version:', 'Capture:'}:
                        self.assertLessEqual(value.document().size().height(), value.viewport().height())
                        self.assertLessEqual(value.document().idealWidth(), value.viewport().width() + 1)
                capture_label, capture_value = next(row for row in self.window.execution_boundary_rows
                    if row[0].text() == 'Capture:')
                runtime_value = next(value for label, value in self.window.execution_boundary_rows
                    if label.text() == 'Runtime version:')
                capture_bottom = capture_value.mapTo(self.window.execution_boundary_card,
                    QPoint(0, capture_value.height())).y()
                self.assertGreater(capture_label.mapTo(self.window.execution_boundary_card, QPoint(0, 0)).y(),
                    runtime_value.mapTo(self.window.execution_boundary_card, QPoint(0, runtime_value.height())).y())
                self.assertLessEqual(capture_bottom, self.window.execution_boundary_card.height())
                region = self.window.current_run_region
                self.assertLessEqual(region.height(), max(region.layout().totalHeightForWidth(region.width()),
                    self.window.current_run_scroll.viewport().height()))

    def test_capture_version_bullets_remain_selectable_and_copyable(self):
        projection = self.projection()
        self.show_projection(projection)
        label, value = next(row for row in self.window.execution_boundary_rows
            if row[0].text() == 'Capture:')
        self.assertTrue(label.alignment() & Qt.AlignmentFlag.AlignTop)
        self.assertEqual([f'• {self.reference}', '• Mode: Not recorded', '• Cache validation replays'], value.text().splitlines())
        card = self.window.execution_boundary_card
        self.assertGreater(value.mapTo(card, QPoint(0, 0)).y(),
            label.mapTo(card, QPoint(0, label.height())).y())
        self.assertEqual(value.mapTo(card, QPoint(0, 0)).x(), label.mapTo(card, QPoint(0, 0)).x())
        value.selectAll()
        value.copy()
        self.assertEqual(value.text(), self.qt.clipboard().text())

    def test_archived_versions_render_in_boundary_without_actions(self):
        from AgMark.shared.software_testing.frontends.gui.test_runtime_reference_history import RuntimeReferenceHistoryTests
        fixture = RuntimeReferenceHistoryTests()
        self.addCleanup(fixture.doCleanups)
        run, _, _ = fixture.archive()
        projection, _ = run.prepare_presentation()
        self.show_projection(projection)
        self.assert_runtime_details(projection)
        self.assertIsNone(self.window.accept_plan_button)
        self.assertIsNone(self.window.start_benchmark_button)

    def test_presentation_uses_frozen_plan_provenance_and_new_metadata_refreshes(self):
        session, request = planning_fixture()
        old_plan = session.build_plan(request)
        session.accept_plan()
        with patch('AgMark.shared.adapters.Codex_CLI.load_registration', side_effect=AssertionError('history must use frozen plan')):
            old_boundary, old_projection = SharedApplicationProjector._plan_summary(None, old_plan, request)
        update = dict(load_registration()['extensions'][UPDATE_EXTENSION])
        update.update(revision='runtime-neutral-capture-v2', reference_runtime_version='9.9.9')
        new_projection = self.projection(update=update)
        self.assertEqual('warning', old_projection.capture_runtime_advisory_tone)
        self.assertIsNone(new_projection.run_plan.capture_runtime_advisory)
        self.assertIn(self.reference, dict(old_boundary.runtime_details)['Capture'])
        self.assertIn('9.9.9', dict(new_projection.execution_boundary.runtime_details)['Capture'])
