"""Concrete PySide6 conformance tests for reusable text-tab navigation."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.tabs import PYSIDE6_AVAILABLE, TabWidget

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication, QWidget


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class TabWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_preserves_caller_labels_selection_and_text_tab_presentation(self) -> None:
        first = QWidget()
        second = QWidget()
        tabs = TabWidget(
            (("Plan", first), ("Results", second)),
            selected_index=1,
        )
        self.addCleanup(tabs.deleteLater)

        self.assertEqual(tabs.labels, ("Plan", "Results"))
        self.assertEqual(tabs.selected_index, 1)
        self.assertEqual(tabs.selected_label, "Results")
        self.assertEqual(tabs.tabText(0), "Plan")
        self.assertEqual(tabs.tabText(1), "Results")
        self.assertFalse(tabs.tabBar().drawBase())
        self.assertFalse(tabs.tabBar().expanding())
        self.assertIn("border-bottom", tabs.styleSheet())
        self.assertIn("#005FFD", tabs.styleSheet())
        self.assertEqual(tabs.authority_semantics, "presentation-only")
        self.assertEqual(tabs.property("activationSemantics"), "presentation-only")

    def test_selection_changes_only_from_explicit_index_not_visible_text(self) -> None:
        first = QWidget()
        second = QWidget()
        tabs = TabWidget(
            (("accepted", first), ("blocked", second)),
            selected_index=0,
        )
        self.addCleanup(tabs.deleteLater)

        self.assertEqual(tabs.selected_label, "accepted")
        tabs.set_selected_index(1)
        self.assertEqual(tabs.selected_label, "blocked")
        self.assertEqual(tabs.authority_semantics, "presentation-only")

    def test_invalid_tab_contract_fails_closed(self) -> None:
        content = QWidget()
        self.addCleanup(content.deleteLater)

        with self.assertRaisesRegex(ValueError, "at least one"):
            TabWidget((), selected_index=0)

        with self.assertRaisesRegex(ValueError, "tab label"):
            TabWidget((("   ", content),), selected_index=0)

        with self.assertRaisesRegex(ValueError, "QWidget"):
            TabWidget((("Plan", object()),), selected_index=0)

        with self.assertRaisesRegex(ValueError, "integer"):
            TabWidget((("Plan", content),), selected_index=True)

        with self.assertRaisesRegex(ValueError, "supplied tab"):
            TabWidget((("Plan", content),), selected_index=1)


if __name__ == "__main__":
    unittest.main()
